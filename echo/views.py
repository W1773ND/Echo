# -*- coding: utf-8 -*-
import json
import logging
import os
import re
from threading import Thread

import requests
from ajaxuploader.views import AjaxFileUploader
from currencies.models import Currency
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files import File
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import get_model
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template
from django.utils.http import urlquote
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.conf import settings as ikwen_settings
from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.core.constants import CONFIRMED
from ikwen.core.models import Service
from ikwen.core.views import ChangeObjectBase, HybridListView
from ikwen.core.utils import send_sms, get_service_instance, DefaultUploadBackend, get_sms_label, add_event, \
    get_mail_content, get_model_admin_instance, get_item_list
from ikwen.accesscontrol.models import Member, SUDO
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen.revival.models import ProfileTag, MemberProfile

from echo.admin import MailCampaignAdmin
from echo.models import SMSCampaign, MailCampaign, SMSObject, Balance, Bundle, Refill, SMS, MAIL
from echo.utils import count_pages

logger = logging.getLogger('ikwen')

ALL_COMMUNITY = "[All Community]"
MESSAGING_CREDIT_REFILL = "MessagingCreditRefill"
SELECTED_PROFILES = "[Selected profiles]"
FILE = "File"
INPUT = "Input"
PROFILES = "Profiles"


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
            if getattr(settings, 'UNIT_TESTING', False) or getattr(settings, 'ECHO_TEST', False):
                requests.get('http://google.com')
            else:
                send_sms(recipient=recipient, text=text, fail_silently=False)
            SMSObject.objects.using(UMBRELLA).create(recipient=recipient, text=text, label=label, campaign=campaign)
        except:
            SMSObject.objects.using(UMBRELLA).create(recipient=recipient, text=text, label=label, campaign=campaign,
                                                     is_sent=False)
            balance.sms_count += page_count
            balance.save()
        campaign.progress += 1
        campaign.save()


def batch_send_mail(campaign):
    service = campaign.service
    config = service.config
    balance = Balance.objects.using('wallets').get(service_id=service.id)
    campaign.keep_running = True
    campaign.save(using=UMBRELLA)

    connection = mail.get_connection()
    try:
        connection.open()
    except:
        response = {'error': 'Failed to connect to mail server. Please check your internet'}
        return HttpResponse(json.dumps(response))

    for email in campaign.recipient_list[campaign.progress:]:
        email = email.strip()
        subject = campaign.subject
        try:
            member = Member.objects.filter(email=email)[0]
            message = campaign.content.replace('$client', member.first_name)
        except:
            message = campaign.content.replace('$client', "")
        sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
        media_url = ikwen_settings.CLUSTER_MEDIA_URL + service.project_name_slug + '/'
        product_list = []
        if campaign.items_fk_list:
            app_label, model_name = campaign.model_name.split('.')
            item_model = get_model(app_label, model_name)
            product_list = item_model._default_manager.filter(pk__in=campaign.items_fk_list)
        try:
            currency = Currency.objects.get(is_base=True)
        except Currency.DoesNotExist:
            currency = None
        html_content = get_mail_content(subject, message, template_name='echo/mails/campaign.html',
                                        extra_context={'media_url': media_url, 'product_list': product_list,
                                                       'campaign': campaign, 'currency': currency})
        msg = EmailMessage(subject, html_content, sender, [email])
        msg.content_subtype = "html"
        if getattr(settings, 'ECHO_TEST', False):
            requests.get('http://www.google.com')
        else:
            try:
                with transaction.atomic(using='wallets'):
                    if not msg.send():
                        balance.mail_count += 1
                        balance.save()
            except:
                pass
        campaign = MailCampaign.objects.using(UMBRELLA).get(pk=campaign.id)
        campaign.progress += 1
        if not campaign.keep_running:
            campaign.save(using=UMBRELLA)
            break
        campaign.save(using=UMBRELLA)

    try:
        connection.close()
    except:
        pass


def set_bundle_checkout(request, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_BEFORE_CHECKOUT"
    """
    referrer = request.META.get('HTTP_REFERER')
    if request.user.is_anonymous():
        next_url = reverse('ikwen:sign_in')
        if referrer:
            next_url += '?next=' + urlquote(referrer)
        return HttpResponseRedirect(next_url)
    service = get_service_instance(using=UMBRELLA)
    bundle_id = request.POST['product_id']
    bundle = Bundle.objects.using(UMBRELLA).get(pk=bundle_id)
    amount = bundle.cost
    refill = Refill.objects.using(UMBRELLA).create(service=service, type=bundle.type, amount=amount, credit=bundle.credit)
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
    if getattr(settings, 'UNIT_TESTING', False):
        ikwen_service = Service.objects.get(pk=getattr(settings, 'IKWEN_SERVICE_ID'))
    else:
        ikwen_service = Service.objects.get(pk=ikwen_settings.IKWEN_SERVICE_ID)
    refill_id = request.session['object_id']
    
    with transaction.atomic(using='wallets'):
        refill = Refill.objects.using(UMBRELLA).get(pk=refill_id)
        refill.status = CONFIRMED
        refill.save()
        balance = Balance.objects.using('wallets').get(service_id=service.id)
        if refill.type == SMS:
            balance.sms_count += refill.credit
            balance_count = balance.sms_count
        else:
            balance.mail_count += refill.credit
            balance_count = balance.mail_count
        balance.save()

    member = request.user
    sudo_group = Group.objects.get(name=SUDO)
    ikwen_sudo_group = Group.objects.using(UMBRELLA).get(name=SUDO)
    add_event(ikwen_service, MESSAGING_CREDIT_REFILL, group_id=sudo_group.id, model='echo.Refill', object_id=refill.id)
    add_event(ikwen_service, MESSAGING_CREDIT_REFILL, group_id=ikwen_sudo_group.id, model='echo.Refill', object_id=refill.id)
    if member.email:
        try:
            subject = _("Successful refill of %d %s" % (refill.credit, refill.type))
            html_content = get_mail_content(subject, template_name='echo/mails/successful_refill.html',
                                            extra_context={'member_name': member.first_name, 'refill': refill,
                                                           'balance_count': balance_count})
            sender = 'ikwen <no-reply@ikwen.com>'
            msg = EmailMessage(subject, html_content, sender, [member.email])
            msg.content_subtype = "html"
            if member != service.member:
                msg.cc = [service.member.email]
            Thread(target=lambda m: m.send(), args=(msg,)).start()
        except:
            pass
    return HttpResponseRedirect(request.session['return_url'])


class CampaignBaseView(TemplateView):
    model = None

    def get_context_data(self, **kwargs):
        context = super(CampaignBaseView, self).get_context_data(**kwargs)
        service = get_service_instance(UMBRELLA)
        campaign_list = self.model._default_manager.using(UMBRELLA).filter(service=service).order_by("-id")[:5]
        for campaign in campaign_list:
            if campaign.total > 0:
                campaign.progress_rate = (campaign.progress / campaign.total) * 100
                campaign.sample = campaign.get_sample()
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        context['balance'] = balance
        context['campaign_list'] = campaign_list
        context['member_count'] = Member.objects.all().count()
        context['profiletag_list'] = ProfileTag.objects.filter(is_active=True, is_auto=False)
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'start_campaign':
            return self.start_campaign(request, *args, **kwargs)
        if action == 'get_campaign_progress':
            return self.get_campaign_progress(request)
        return super(CampaignBaseView, self).get(request, *args, **kwargs)

    def get_recipient_list(self, request):
        filename = request.GET.get('filename', request.POST.get('filename'))
        recipient_list = request.GET.get('recipients', request.POST.get('recipients'))
        profiles_checked = request.GET.get('profiles', request.POST.get('profiles'))
        campaign_type = SMS if self.model == SMSCampaign else MAIL
        if filename:
            # Should add somme security check about file existence and type here before attempting to read it
            path = getattr(settings, 'MEDIA_ROOT') + '/' + DefaultUploadBackend.UPLOAD_DIR + '/' + filename
            recipient_list = []
            recipient_label = filename
            # recipient_label_raw = recipient_label.split('.')[0]
            recipient_label_raw = recipient_label
            recipient_src = FILE
            recipient_profile = ""

            with open(path, 'r') as fh:
                for recipient in fh.readlines():
                    recipient_list.append(recipient)
            fh.close()
        elif recipient_list == ALL_COMMUNITY:
            recipient_list = []
            recipient_label = ALL_COMMUNITY
            recipient_label_raw = recipient_label
            recipient_src = INPUT
            recipient_profile = ""
            member_queryset = Member.objects.all()
            total = member_queryset.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for member in member_queryset[start:finish]:
                    if campaign_type == SMS and member.phone:
                        recipient_list.append(member.phone)
                    elif campaign_type == MAIL and member.email:
                        recipient_list.append(member.email)
        elif recipient_list == SELECTED_PROFILES:
            recipient_list = []
            recipient_src = PROFILES
            recipient_profile = profiles_checked
            checked_profile_tag_id_list = profiles_checked.split(',')
            if campaign_type == SMS:
                recipient_label = []
                for profile_id in checked_profile_tag_id_list:
                    try:
                        profile_tag = ProfileTag.objects.get(pk=profile_id)
                        recipient_label.append(profile_tag.name)
                    except ProfileTag.DoesNotExist:
                        continue
                recipient_label = ', '.join(recipient_label)
            elif campaign_type == MAIL:
                recipient_label = SELECTED_PROFILES
                recipient_label_raw = []
                for profile_id in checked_profile_tag_id_list:
                    try:
                        profile_tag = ProfileTag.objects.get(pk=profile_id)
                        recipient_label_raw.append(profile_tag.name)
                    except ProfileTag.DoesNotExist:
                        continue
                recipient_label_raw = ', '.join(recipient_label_raw)

            member_queryset = Member.objects.all()
            total = member_queryset.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for member in member_queryset[start:finish]:
                    try:
                        profile = MemberProfile.objects.get(member=member)
                    except MemberProfile.DoesNotExist:
                        continue
                    match = set(profile.tag_fk_list) & set(checked_profile_tag_id_list)
                    if len(match) > 0:
                        if campaign_type == SMS and member.phone:
                            recipient_list.append(member.phone)
                        elif campaign_type == MAIL and member.email:
                            recipient_list.append(member.email)
        elif recipient_list == '':
            recipient_label = recipient_list
            recipient_label_raw = recipient_label
            recipient_src = INPUT
            recipient_profile = ""

        else:
            # recipient_list = recipient_list.strip().split(',')
            recipient_list = re.split(';|,', recipient_list.strip())
            recipient_label = ';'.join(recipient_list)
            recipient_label_raw = recipient_label
            recipient_src = INPUT
            recipient_profile = ""
        return recipient_label, recipient_label_raw, recipient_src, list(set(recipient_list)), recipient_profile

    def get_campaign_progress(self, request):
        campaign_id = request.GET['campaign_id']
        campaign = self.model._default_manager.using(UMBRELLA).get(pk=campaign_id)
        response = {"progress": campaign.progress, "total": campaign.total}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class SMSCampaignView(CampaignBaseView):
    template_name = "echo/sms_campaign.html"
    model = SMSCampaign

    def get_context_data(self, **kwargs):
        context = super(SMSCampaignView, self).get_context_data(**kwargs)
        context['verbose_name_plural'] = "echo-sms"
        context['csv_model'] = "ikwen_SMS_campaign_csv_model"
        return context

    def start_campaign(self, request, *args, **kwargs):
        member = request.user
        subject = request.GET.get('subject')
        txt = request.GET.get('txt')
        recipient_label, recipient_label_raw, recipient_src, recipient_list, recipient_profile = self.get_recipient_list(request)
        recipient_count = len(recipient_list)
        slug = slugify(subject)
        page_count = count_pages(txt)
        sms_count = int(page_count * recipient_count)

        # "transaction.atomic" instruction locks database during all operations inside "with" block
        try:
            balance = Balance.objects.using('wallets').get(service_id=get_service_instance().id)
            if balance.sms_count < sms_count:
                response = {"error": _("Insufficient SMS balance.")}
                return HttpResponse(
                    json.dumps(response),
                    'content-type: text/json'
                )
            with transaction.atomic(using='wallets'):
                balance.sms_count -= sms_count
                balance.save()
                service = get_service_instance(using=UMBRELLA)
                mbr = Member.objects.using(UMBRELLA).get(pk=member.id)
                campaign = SMSCampaign.objects.using(UMBRELLA).create(service=service, member=mbr, subject=subject,
                                                                      slug=slug, text=txt, total=recipient_count,
                                                                      recipient_list=recipient_list, recipient_label=recipient_label,
                                                                      page_count=page_count)

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


class MailCampaignList(HybridListView):
    template_name = 'echo/mailcampaign_list.html'
    html_results_template_name = 'echo/snippets/mailcampaign_list_results.html'
    model = MailCampaign
    service = get_service_instance(using=UMBRELLA)
    queryset = MailCampaign.objects.using(UMBRELLA).filter(service=service)
    search_field = 'subject'

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'get_campaign_progress':
            return self.get_campaign_progress(request)
        return super(MailCampaignList, self).get(request, *args, **kwargs)

    def get_campaign_progress(self, request):
        campaign_id = request.GET['campaign_id']
        campaign = self.model._default_manager.using(UMBRELLA).get(pk=campaign_id)
        response = {"campaign subject": campaign.subject, "progress": campaign.progress, "total": campaign.total, "campaign": campaign.to_dict()}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class ChangeMailCampaign(CampaignBaseView, ChangeObjectBase):
    template_name = "echo/change_mailcampaign.html"
    model = MailCampaign
    model_admin = MailCampaignAdmin
    context_object_name = 'campaign'

    def get_context_data(self, **kwargs):
        context = super(ChangeMailCampaign, self).get_context_data(**kwargs)
        obj = context['obj']
        context['csv_model'] = "ikwen_MAIL_campaign_csv_model"
        if obj:
            obj.terminated = obj.progress > 0 and obj.progress == obj.total
        items_fk_list = []
        if self.request.GET.get('items_fk_list'):
            items_fk_list = self.request.GET.get('items_fk_list').split(',')
            obj.items_fk_list = items_fk_list
            obj.save(using=UMBRELLA)
            context['set_cyclic'] = True
        context['items_fk_list'] = ','.join(items_fk_list)
        context['item_list'] = get_item_list('kako.Product', items_fk_list)
        return context

    def get_object(self, **kwargs):
        object_id = kwargs.get('object_id')  # May be overridden with the one from GET data
        if object_id:
            try:
                return MailCampaign.objects.using(UMBRELLA).get(pk=object_id)
            except MailCampaign.DoesNotExist:
                raise Http404()

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'toggle_campaign':
            return self.toggle_campaign(request, *args, **kwargs)
        if action == 'run_test':
            return self.run_test(request, *args, **kwargs)
        return super(ChangeMailCampaign, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        object_id = kwargs.get('object_id')
        service = get_service_instance(using=UMBRELLA)
        member = request.user
        mbr = Member.objects.using(UMBRELLA).get(pk=member.id)
        if object_id:
            obj = MailCampaign.objects.using(UMBRELLA).get(pk=object_id)
        else:
            obj = self.model()
        model_form = object_admin.get_form(request)
        form = model_form(request.POST, instance=obj)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            pre_header = form.cleaned_data['pre_header']
            content = form.cleaned_data['content']
            cta = form.cleaned_data['cta']
            cta_url = form.cleaned_data['cta_url']
            recipient_label, recipient_label_raw, recipient_src, recipient_list, recipient_profile = self.get_recipient_list(request)
            slug = slugify(subject)
            if not object_id:
                obj = MailCampaign(service=service, member=mbr)

            obj.subject = subject
            obj.slug = slug
            obj.pre_header = pre_header
            obj.content = content
            obj.cta = cta
            obj.cta_url = cta_url
            obj.recipient_label = recipient_label
            obj.recipient_label_raw = recipient_label_raw
            obj.recipient_src = recipient_src
            obj.recipient_profile = recipient_profile
            obj.recipient_list = recipient_list
            obj.total = len(recipient_list)
            obj.save(using=UMBRELLA)

            image_url = request.POST.get('image_url')
            if image_url:
                s = get_service_instance()
                image_field_name = request.POST.get('image_field_name', 'image')
                image_field = obj.__getattribute__(image_field_name)
                if not image_field.name or image_url != image_field.url:
                    filename = image_url.split('/')[-1]
                    media_root = getattr(settings, 'MEDIA_ROOT')
                    media_url = getattr(settings, 'MEDIA_URL')
                    path = image_url.replace(media_url, '')
                    try:
                        with open(media_root + path, 'r') as f:
                            content = File(f)
                            destination = media_root + obj.UPLOAD_TO + "/" + s.project_name_slug + '_' + filename
                            image_field.save(destination, content)
                        os.unlink(media_root + path)
                    except IOError as e:
                        if getattr(settings, 'DEBUG', False):
                            raise e
                        return {'error': 'File failed to upload. May be invalid or corrupted image file'}
            if request.POST.get('keep_editing'):
                next_url = reverse('echo:change_mailcampaign', args=(obj.id, ))
            else:
                next_url = self.get_object_list_url(request, obj, *args, **kwargs)
            if object_id:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode('utf8') + '</strong> ' + _('successfully updated').decode('utf8'))
            else:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode('utf8') + '</strong> ' + _('successfully created').decode('utf8'))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)

    def start_campaign(self, request, *args, **kwargs):
        campaign_id = kwargs['object_id']
        campaign = MailCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        if campaign.is_started and not campaign.keep_running:
            response = {"error": "Campaign already started"}
            return HttpResponse(
                json.dumps(response),
                'content-type: text/json')
        balance = Balance.objects.using('wallets').get(service_id=get_service_instance().id)
        campaign.keep_running = True
        campaign.is_started = True
        campaign.save()
        # "transaction.atomic" instruction locks database during all operations inside "with" block
        try:
            if balance.mail_count < campaign.total:
                response = {"insufficient_balance": _("Insufficient Email balance.")}
                return HttpResponse(
                    json.dumps(response),
                    'content-type: text/json'
                )
            with transaction.atomic(using='wallets'):
                balance.mail_count -= campaign.total
                balance.save()
                if getattr(settings, 'UNIT_TESTING', False):
                    batch_send_mail(campaign)
                elif campaign.total < 50:
                    # for small campaign ie minor than 50, send sms directly from application server
                    Thread(target=batch_send_mail, args=(campaign, )).start()
                response = {"success": True, "balance": balance.mail_count, "campaign": campaign.to_dict()}
        except Exception as e:
            response = {"error": "Error while submitting your campaign. Please try again later."}

        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def toggle_campaign(self,  request, *args, **kwargs):
        campaign_id = kwargs['object_id']
        campaign = MailCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        campaign.keep_running = not campaign.keep_running
        campaign.save()
        response = {"success": True, "campaign": campaign.to_dict()}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def run_test(self, request, *args, **kwargs):
        campaign_id = kwargs['object_id']
        campaign = MailCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        test_email_list = request.GET['test_email_list'].split(',')
        test_email_count = len(test_email_list)
        service = get_service_instance()
        balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id=service.id)
        if balance.mail_count < test_email_count:
            response = {'error': 'Insufficient Email and SMS credit'}
            return HttpResponse(json.dumps(response))

        connection = mail.get_connection()
        try:
            connection.open()
        except:
            response = {'error': 'Failed to connect to mail server. Please check your internet'}
            return HttpResponse(json.dumps(response))
        config = service.config

        warning = []
        for email in test_email_list[:5]:
            if balance.mail_count == 0:
                warning.append('Insufficient email Credit')
                break
            email = email.strip()
            subject = "Test - " + campaign.subject
            try:
                member = Member.objects.filter(email=email)[0]
                message = campaign.content.replace('$client', member.first_name)
            except:
                message = campaign.content.replace('$client', "")
            sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
            media_url = ikwen_settings.CLUSTER_MEDIA_URL + service.project_name_slug + '/'
            product_list = []
            if campaign.items_fk_list:
                app_label, model_name = campaign.model_name.split('.')
                item_model = get_model(app_label, model_name)
                product_list = item_model._default_manager.filter(pk__in=campaign.items_fk_list)
            try:
                currency = Currency.objects.get(is_base=True)
            except Currency.DoesNotExist:
                currency = None
            html_content = get_mail_content(subject, message, template_name='echo/mails/campaign.html',
                                            extra_context={'media_url': media_url, 'product_list': product_list,
                                                           'campaign': campaign, 'currency': currency})
            msg = EmailMessage(subject, html_content, sender, [email])
            msg.content_subtype = "html"
            try:
                with transaction.atomic(using='wallets'):
                    balance.mail_count -= 1
                    balance.save()
                    if not msg.send():
                        transaction.rollback(using='wallets')
                        warning.append('Mail not sent to %s' % email)
            except:
                pass
        try:
            connection.close()
        except:
            pass

        response = {'success': True, 'warning': warning}
        return HttpResponse(json.dumps(response))


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


# class MailHistory(TemplateView):
#     template_name = "echo/mail_history.html"


class MailBundle(TemplateView):
    template_name = "echo/mail_bundle.html"

    def get_context_data(self, **kwargs):
        context = super(MailBundle, self).get_context_data(**kwargs)
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        bundle_list = Bundle.objects.using(UMBRELLA).filter(type=MAIL, is_active=True)
        context['balance'] = balance
        context['bundle_list'] = bundle_list
        return context


csv_uploader = AjaxFileUploader(DefaultUploadBackend)


def render_credit_refill_event(event, request):
    from ikwen.conf import settings as ikwen_settings
    ikwen_service = Service.objects.using(UMBRELLA).get(pk=ikwen_settings.IKWEN_SERVICE_ID)
    currency_symbol = ikwen_service.config.currency_symbol
    try:
        refill = Refill.objects.using(UMBRELLA).get(pk=event.object_id)
    except Refill.DoesNotExist:
        return ''
    service_deployed = invoice.service
    member = service_deployed.member
    if request.GET['member_id'] != member.id:
        data = {'title': 'New service deployed',
                'details': service_deployed.details,
                'member': member,
                'service_deployed': True}
        template_name = 'billing/events/notice.html'
    else:
        template_name = 'core/events/service_deployed.html'
        data = {'obj': invoice,
                'project_name': service_deployed.project_name,
                'service_url': service_deployed.url,
                'due_date': invoice.due_date,
                'show_pay_now': invoice.status != Invoice.PAID}
    data.update({'currency_symbol': currency_symbol,
                 'details_url': IKWEN_BASE_URL + reverse('billing:invoice_detail', args=(invoice.id,)),
                 'amount': invoice.amount,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
    c = Context(data)
    html_template = get_template(template_name)
    return html_template.render(c)
