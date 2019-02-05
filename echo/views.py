# -*- coding: utf-8 -*-
import json
import logging
from threading import Thread

import requests
from ajaxuploader.views import AjaxFileUploader
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.template.defaultfilters import slugify
from django.utils.http import urlquote
from django.views.generic import TemplateView
from django.utils.translation import gettext as _
from ikwen.core.constants import CONFIRMED
from ikwen.core.utils import send_sms, get_service_instance, DefaultUploadBackend, get_sms_label, add_event, \
    get_mail_content
from ikwen.accesscontrol.models import Member, SUDO
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.billing.mtnmomo.views import MTN_MOMO
from math import ceil
from echo.models import Campaign, SMSObject, Balance, Bundle, Refill, SMS

logger = logging.getLogger('ikwen')

ALL_COMMUNITY = "[All Community]"
MESSAGING_CREDIT_REFILL = "MessagingCreditRefill"

sms_normal_count = [' ', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
                    'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S',
                    'T', 'U', 'V', 'W', 'X', 'Y', 'Z', u'Ä', u'ä', u'à', u'Å', u'å', u'Æ', u'æ', u'ß', u'Ç', u'è', u'é',
                    u'É', u'ì', u'Ö', u'ö', u'ò', u'Ø', u'ø', u'Ñ', u'ñ', u'Ü', u'ü', u'ù', u'#', u'¤', u'%', u'&',
                    u'(', u')', u'*', u'+', u',', u'–', u'.', u'/', u':', u';', u'<', u'>', u'=', u'§', u'$', u'!',
                    u'?', u'£', u'¿', u'¡', u'@', u'¥', u'Δ', u'Φ', u'Γ', u'Λ', u'Ω', u'Π', u'Ψ', u'Σ', u'Θ', u'Ξ',
                    u'»', u'‘', "'", '"', '-']
sms_double_count = [u'^', u'|', u'€', u'}', u'{', u'[', u'~', u']', u'\\']


def count_pages(text):
    max_length = 160
    count = 0
    for char in text:
        if max_length >= 153:
            if char in sms_double_count:
                count += 2
            else:
                count += 1
        else:
            count += 1
    for char in text:
        if char not in sms_double_count and char not in sms_normal_count:
            max_length = 70
    if count > max_length:
        if max_length >= 153:
            max_length -= 7
        else:
            max_length -= 4
    page_count = ceil(float(count) / max_length)
    return page_count


def batch_send(campaign):
    text = campaign.text
    page_count = campaign.page_count
    service = campaign.service
    config = service.config
    label = get_sms_label(config)
    balance = Balance.objects.using('wallets').get(service_id=service.id)
    for recipient in campaign.recipient_list[campaign.progress:]:
        if len(recipient) == 9:
            recipient = '237' + recipient
        try:
            if getattr(settings, 'UNIT_TESTING', False):
                requests.get('http://google.com')
            else:
                logger.debug("Sending SMS to %s" % recipient)
                send_sms(recipient=recipient, text=text, fail_silently=False)
            SMSObject.objects.using(UMBRELLA).create(recipient=recipient, text=text, label=label, campaign=campaign)
        except:
            SMSObject.objects.using(UMBRELLA).create(recipient=recipient, text=text, label=label, campaign=campaign,
                                                     is_sent=False)
            balance.sms_count += page_count
            balance.save()
        campaign.progress += 1
        campaign.save()


def set_bundle_checkout(request, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_BEFORE_CHECKOUT"
    """
    referrer = request.META.get('HTTP_REFERER')
    if request.user.is_anonymous():
        next_url = reverse('ikwen:sign_in')
        if referrer:
            next_url += '?' + urlquote(referrer)
        return HttpResponseRedirect(next_url)
    service = get_service_instance(using=UMBRELLA)
    bundle_id = request.POST['product_id']
    type = request.POST['type']
    bundle = Bundle.objects.using(UMBRELLA).get(pk=bundle_id)
    amount = bundle.cost
    refill = Refill.objects.using(UMBRELLA).create(service=service, type=type, amount=amount, credit=bundle.credit)
    request.session['amount'] = amount
    request.session['model_name'] = 'echo.Refill'
    request.session['object_id'] = refill.id

    mean = request.GET.get('mean', MTN_MOMO)
    request.session['mean'] = mean
    request.session['notif_url'] = service.url  # Orange Money only
    request.session['cancel_url'] = referrer  # Orange Money only
    request.session['return_url'] = referrer


def confirm_bundle_payment(request, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_AFTER_CHECKOUT"
    """
    service = get_service_instance()
    config = service.config
    refill_id = request.session['object_id']
    
    with transaction.atomic(using='wallets'):
        refill = Refill.objects.using(UMBRELLA).get(pk=refill_id)
        refill.status = CONFIRMED
        refill.save()
        balance = Balance.objects.using('wallets').get(service_id=service.id)
        if refill.type == SMS:
            balance.sms_count += refill.credit
        else:
            balance.mail_count += refill.credit
        balance.save()

    member = request.user
    sudo_group = Group.objects.get(name=SUDO)
    add_event(service, MESSAGING_CREDIT_REFILL, group_id=sudo_group.id, model='echo.Refill', object_id=refill.id)
    if member.email:
        try:
            subject = _("Successful refill of %d %s" % (refill.credit, refill.type))
            html_content = get_mail_content(subject, template_name='echo/mails/successful_refill.html',
                                            extra_context={'member_name': member.first_name, 'refill': refill})
            sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
            msg = EmailMessage(subject, html_content, sender, [member.email])
            msg.content_subtype = "html"
            if member != service.member:
                msg.cc = [service.member.email]
            Thread(target=lambda m: m.send(), args=(msg,)).start()
        except:
            pass
    return HttpResponseRedirect(request.session['return_url'])


class SMSCampaign(TemplateView):
    template_name = "echo/sms_campaign.html"

    def get_context_data(self, **kwargs):
        context = super(SMSCampaign, self).get_context_data(**kwargs)
        campaign_list = Campaign.objects.using(UMBRELLA).all().order_by("-id")[:5]
        for campaign in campaign_list:
            campaign.progress_rate = (campaign.progress / campaign.total) * 100
            campaign.sample_sms = campaign.get_sample_sms()
            campaign.recipients = ', '.join(campaign.recipient_list[:5])
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        context['balance'] = balance
        context['campaign_list'] = campaign_list
        context['member_count'] = Member.objects.all().count()
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'start_campaign':
            return self.start_campaign(request)
        if action == 'get_campaign_progress':
            return self.get_campaign_progress(request)
        return super(SMSCampaign, self).get(request, *args, **kwargs)

    def start_campaign(self, request):
        member = request.user
        subject = request.GET.get('subject')
        slug = slugify(subject)
        txt = request.GET.get('txt')
        filename = request.GET.get('filename')
        recipient_list = request.GET.get('recipients')
        if filename:
            # Should add somme security check about file existence and type here before attempting to read it
            path = getattr(settings, 'MEDIA_ROOT') + '/' + DefaultUploadBackend.UPLOAD_DIR + '/' + filename
            recipient_list = []

            with open(path, 'r') as fh:
                for recipient in fh.readlines():
                    recipient_list.append(recipient)
            fh.close()
            recipient_count = len(recipient_list)
        elif recipient_list == ALL_COMMUNITY:
            recipient_list = []

            # Segmentation fault incoming with big community
            community_member = Member.objects.all()
            # Segmentation fault incoming with big community

            for member in community_member:
                recipient_list.append(member.phone)
            recipient_count = len(recipient_list)
        else:
            recipient_list = recipient_list.strip().split(',')
            recipient_count = len(recipient_list)
        page_count = count_pages(txt)
        sms_count = int(page_count * recipient_count)

        # "transaction.atomic" instruction locks database during all operations inside "with" block
        try:
            balance = Balance.objects.using('wallets').get(service_id=get_service_instance().id)
            if balance.sms_count < sms_count:
                response = {"insufficient_balance": _("Insufficient SMS balance.")}
                return HttpResponse(
                    json.dumps(response),
                    'content-type: text/json'
                )
            with transaction.atomic(using='wallets'):
                balance.sms_count -= sms_count
                balance.save()
                service = get_service_instance(using=UMBRELLA)
                mbr = Member.objects.using(UMBRELLA).get(pk=member.id)
                campaign = Campaign.objects.using(UMBRELLA).create(service=service, member=mbr, subject=subject,
                                                                   type="SMS", slug=slug, recipient_list=recipient_list,
                                                                   text=txt, total=sms_count)
                if getattr(settings, 'UNIT_TESTING', False):
                    batch_send(campaign)
                elif recipient_count < 50:
                    # for small campaign ie minor than 50, send sms directly from application server
                    Thread(target=batch_send, args=(campaign, )).start()
                response = {"success": True, "balance": balance.sms_count, "campaign": campaign.to_dict()}
        except:
            response = {"error": "Error while submiting SMS. Please try again later."}

        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def get_campaign_progress(self, request):
        campaign_id = request.GET['campaign_id']
        campaign = Campaign.objects.using(UMBRELLA).get(pk=campaign_id)
        response = {"progress": campaign.progress, "total": campaign.total}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class SMSHistory(TemplateView):
    template_name = "echo/sms_history.html"


class SMSBundle(TemplateView):
    template_name = "echo/sms_bundle.html"

    def get_context_data(self, **kwargs):
        context = super(SMSBundle, self).get_context_data(**kwargs)
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        bundle_list = Bundle.objects.using(UMBRELLA).filter(type=SMS, is_active=True)
        context['balance'] = balance
        context['bundle_list'] = bundle_list
        return context


class MailCampaign(TemplateView):
    template_name = "echo/mail_campaign.html"


class MailHistory(TemplateView):
    template_name = "echo/mail_history.html"


class MailBundle(TemplateView):
    template_name = "echo/mail_bundle.html"


csv_uploader = AjaxFileUploader(DefaultUploadBackend)
