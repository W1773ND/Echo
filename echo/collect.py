# -*- coding: utf-8 -*-
import logging
import string
from datetime import datetime, timedelta
import random
from threading import Thread

import requests
from currencies.models import Currency
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse

from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.utils.http import urlquote
from django.utils.translation import gettext as _, get_language, activate

from echo.utils import LOW_MAIL_LIMIT, notify_for_low_messaging_credit, notify_for_empty_messaging_credit
from ikwen.conf.settings import WALLETS_DB_ALIAS, IKWEN_SERVICE_ID
from ikwen.core.constants import CONFIRMED, STARTED, COMPLETE
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import SUDO, Member
from ikwen.billing.models import Invoice, Payment, PAYMENT_CONFIRMATION, InvoiceEntry, Product, InvoiceItem, Donation, \
    SupportBundle, SupportCode, MoMoTransaction, IkwenInvoiceItem
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen.billing.utils import get_invoicing_config_instance, get_days_count, get_payment_confirmation_message, \
    share_payment_and_set_stats, get_next_invoice_number,notify_event
from ikwen.core.models import Service, Config
from ikwen.core.utils import add_database_to_settings, get_service_instance, add_event, get_mail_content, XEmailMessage
from echo.models import Balance, Refill, SMS, MAIL, Bundle, MESSAGING_CREDIT_REFILL

logger = logging.getLogger('ikwen')


def set_bundle_checkout(request, *args, **kwargs):
    if getattr(settings, 'DEBUG', False):
        service = get_service_instance()
        config = service.config
    else:
        service = Service.objects.using(UMBRELLA).get(pk=IKWEN_SERVICE_ID)
        config = Config.objects.using(UMBRELLA).get(service=service)
    bundle_id = request.POST['product_id']
    if bundle_id != '':
        bundle = Bundle.objects.using(UMBRELLA).get(pk=bundle_id)
        refill = Refill.objects.create(service=service, type=bundle.type, amount=bundle.cost, credit=bundle.credit)
    else:
        custom_bundle_value = int(request.POST['custom_bundle_value'])
        bundle_type = request.POST['bundle_type']
        bundle_list = list(Bundle.objects.using(UMBRELLA).filter(type=bundle_type, is_active=True).order_by('-credit'))
        bundle_unit_cost = bundle_list[-1].unit_cost
        for bundle in bundle_list:
            if custom_bundle_value >= bundle.credit:
                bundle_unit_cost = bundle.unit_cost
                break
        cost = int(custom_bundle_value * bundle_unit_cost)
        refill = Refill.objects.create(service=service, type=bundle_type, amount=cost, credit=custom_bundle_value)
    buyer = request.user.username
    amount = refill.amount
    model_name = 'echo.Refill'
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
    mean = request.GET.get('mean', MTN_MOMO)
    MoMoTransaction.objects.using(WALLETS_DB_ALIAS).filter(object_id=bundle_id).delete()
    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS) \
        .create(service_id=service.id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A',
                model=model_name, object_id=refill.id, wallet=mean, username=buyer, is_running=True, task_id=signature)
    notification_url = service.url + reverse('echo:confirm_bundle_payment', args=(tx.id, signature))
    if refill.type == SMS:
        cancel_url = service.url + reverse('echo:sms_bundle')
        return_url = service.url + reverse('echo:sms_bundle')
    else:
        cancel_url = service.url + reverse('echo:mail_bundle')
        return_url = service.url + reverse('echo:mail_bundle', )
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'https://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', 'ikwen'),
        'amount': amount,
        'merchant_name': config.company_name,
        'notification_url': notification_url,
        'return_url': return_url,
        'cancel_url': cancel_url,
        'user_id': buyer,
    }
    try:
        r = requests.get(endpoint, params, verify=False)
        resp = r.json()
        token = resp.get('token')
        if token:
            next_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
        else:
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed." % service.project_name, exc_info=True)
        messages.error(request, "Error occurs, please try again later")
        next_url = cancel_url
    return HttpResponseRedirect(next_url)


def confirm_bundle_payment(request, *args, **kwargs):
    status = request.GET['status']
    message = request.GET['message']
    operator_tx_id = request.GET['operator_tx_id']
    phone = request.GET['phone']
    tx_id = kwargs['tx_id']

    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
    if not getattr(settings, 'DEBUG', False):
        tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
        expiry = tx.created_on + timedelta(seconds=tx_timeout)
        if datetime.now() > expiry:
            return HttpResponse("Transaction %s timed out." % tx_id)

    tx.status = status
    tx.message = message
    tx.processor_tx_id = operator_tx_id
    tx.phone = phone
    tx.is_running = False
    tx.save()
    if status != MoMoTransaction.SUCCESS:
        return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))
    signature = tx.task_id
    callback_signature = kwargs.get('signature')
    no_check_signature = request.GET.get('ncs')
    if getattr(settings, 'DEBUG', False):
        if not no_check_signature:
            if callback_signature != signature:
                return HttpResponse('Invalid transaction signature')
    else:
        if callback_signature != signature:
            return HttpResponse('Invalid transaction signature')

    number = get_next_invoice_number()
    now = datetime.now().date()
    refill = Refill.objects.get(pk=tx.object_id)
    label = "%s %s" % (refill.credit, refill.type)
    item = IkwenInvoiceItem(label=label, amount=tx.amount)
    entry = InvoiceEntry(item=item)
    member = Member.objects.using(UMBRELLA).get(username=tx.username)
    service = get_service_instance()
    balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id=service.id)
    if refill.status == STARTED:
        if refill.type == SMS:
            balance.sms_count += refill.credit
            balance_count = balance.sms_count
        else:
            balance.mail_count += refill.credit
            balance_count = balance.mail_count
        refill.status = COMPLETE
        refill.save()
        balance.save(using=WALLETS_DB_ALIAS)
    # sudo_group = Group.objects.get(name=SUDO)
    # ikwen_sudo_group = Group.objects.using(UMBRELLA).get(name=SUDO)
    # if getattr(settings, 'UNIT_TESTING', False):
    #     ikwen_service = Service.objects.get(pk=getattr(settings, 'IKWEN_SERVICE_ID'))
    # else:
    #     ikwen_service = Service.objects.get(pk=IKWEN_SERVICE_ID)
    # add_event(ikwen_service, MESSAGING_CREDIT_REFILL, group_id=sudo_group.id, model='echo.Refill', object_id=refill.id)
    # add_event(ikwen_service, MESSAGING_CREDIT_REFILL, group_id=ikwen_sudo_group.id, model='echo.Refill',
    #           object_id=refill.id)

    if member.email:
        try:
            lang = member.language
            activate(lang)
            subject = _("Successful refill of %d %s" % (refill.credit, refill.type))
            html_content = get_mail_content(subject, template_name='echo/mails/successful_refill.html',
                                            extra_context={'member_name': member.first_name, 'refill': refill,
                                                           'balance_count': balance_count})
            sender = 'ikwen <no-reply@ikwen.com>'
            msg = XEmailMessage(subject, html_content, sender, [member.email], bcc=['support@ikwen.com', 'contact@ikwen.com'])
            msg.content_subtype = "html"
            if member != service.member:
                msg.cc = [service.member.email]
            Thread(target=lambda m: m.send(), args=(msg,)).start()
        except:
            pass
    return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))
