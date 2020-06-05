# -*- coding: utf-8 -*-
import json
import logging
import os
import re
import time
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
from django.core.validators import EmailValidator
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
    get_mail_content, get_model_admin_instance, get_item_list, send_push
from ikwen.accesscontrol.models import Member, SUDO, PWAProfile
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.billing.models import Invoice
from ikwen.revival.models import ProfileTag, MemberProfile

from echo.admin import MailCampaignAdmin, PopUpAdmin, PushCampaignAdmin
from echo.models import SMSCampaign, MailCampaign, SMSObject, Balance, Bundle, Refill, SMS, MAIL, PopUp, PushCampaign, \
    PUSH
from echo.utils import count_pages, notify_for_low_messaging_credit

logger = logging.getLogger('ikwen')

ALL_SUBSCRIBER = "[All Subscriber]"
REGISTERED_SUBSCRIBER = "[Registered Subscriber]"
ALL_COMMUNITY = "[All Community]"
SELECTED_PROFILES = "[Selected profiles]"
FILE = "[File]"
INPUT = "[Input]"
PROFILES = "[Profiles]"


def batch_send_push(campaign):
    service = campaign.service
    campaign.keep_running = True
    if len(campaign.recipient_list) == 0:
        recipient_list = []
        if campaign.recipient_src == ALL_SUBSCRIBER:
            subscriber_qs = PWAProfile.objects.all()
            total = subscriber_qs.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for subscriber in subscriber_qs[start:finish]:
                    recipient_list.append(subscriber.push_subscription)
                    if len(recipient_list) == 1:
                        campaign.save(using=UMBRELLA)
        elif campaign.recipient_src == REGISTERED_SUBSCRIBER:
            subscriber_qs = PWAProfile.objects.all()
            total = subscriber_qs.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for subscriber in subscriber_qs[start:finish]:
                    if subscriber.member:
                        recipient_list.append(subscriber.push_subscription)
                    if len(recipient_list) == 1:
                        campaign.save(using=UMBRELLA)
        elif campaign.recipient_src == PROFILES:
            checked_profile_tag_id_list = campaign.profile_tag_list
            member_qs = Member.objects.all()
            total = member_qs.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for member in member_qs[start:finish]:
                    try:
                        profile = MemberProfile.objects.get(member=member)
                    except MemberProfile.DoesNotExist:
                        continue
                    match = set(profile.tag_fk_list) & set(checked_profile_tag_id_list)
                    if len(match) > 0:
                        try:
                            pwa_profile = PWAProfile.objects.get(member=member)
                            recipient_list.append(pwa_profile.push_subscription)
                        except PWAProfile.DoesNotExist:
                            continue
                        if len(recipient_list) == 1:
                            campaign.save(using=UMBRELLA)
        campaign.recipient_list = recipient_list
        campaign.total = len(recipient_list)
        campaign.save(using=UMBRELLA)

    balance = Balance.objects.using('wallets').get(service_id=get_service_instance().id)
    push_count = campaign.total - campaign.progress
    if balance.push_count < push_count:
        try:
            notify_for_low_messaging_credit(service, balance)
        except:
            logger.error("Failed to notify %s for low messaging credit." % service, exc_info=True)
        return

    # TODO: implement equivalent test connection if available for push notifications
    # try:
    #     connection.open()
    # except:
    #     logger.error("Failed to connect to mail server. Please check your internet" % service, exc_info=True)
    #     response = {'error': 'Failed to connect to mail server. Please check your internet'}
    #     return HttpResponse(json.dumps(response))

    for push_subscription in campaign.recipient_list[campaign.progress:]:
        push_subscription = push_subscription.strip()
        title = campaign.subject
        target_page = campaign.cta_url
        media_url = ikwen_settings.CLUSTER_MEDIA_URL + service.project_name_slug + '/'
        image_url = media_url + campaign.image
        body = campaign.content
        if campaign.recipient_src == REGISTERED_SUBSCRIBER:
            try:
                member = PWAProfile.objects.get(push_subscription=push_subscription).member
                body = campaign.content.replace('$client', member.first_name)
            except PWAProfile.DoesNotExist:
                body = campaign.content.replace('$client', "")
        push = send_push(push_subscription, title, body, target_page, image_url)
        if getattr(settings, 'ECHO_TEST', False):
            requests.get('http://www.google.com')
            balance.push_count -= 1
            balance.save()
        else:
            try:
                with transaction.atomic(using='wallets'):
                    if push >= 1:
                        balance.push_count -= push
                        balance.save()
            except:
                pass
        campaign = PushCampaign.objects.using(UMBRELLA).get(pk=campaign.id)
        campaign.progress += push
        if not campaign.keep_running:
            campaign.save(using=UMBRELLA)
            break
        campaign.save(using=UMBRELLA)


def batch_send_mail(campaign):
    service = campaign.service
    config = service.config
    campaign.keep_running = True
    if len(campaign.recipient_list) == 0:
        recipient_list = []
        if campaign.recipient_src == ALL_COMMUNITY:
            member_queryset = Member.objects.all()
            total = member_queryset.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for member in member_queryset[start:finish]:
                    if EmailValidator(member.email):
                        recipient_list.append(member.email)
                    if len(recipient_list) == 1:
                        campaign.save(using=UMBRELLA)
        elif campaign.recipient_src == PROFILES:
            checked_profile_tag_id_list = campaign.profile_tag_list
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
                        if EmailValidator(member.email):
                            recipient_list.append(member.email)
                        if len(recipient_list) == 1:
                            campaign.save(using=UMBRELLA)
        campaign.recipient_list = recipient_list
        campaign.total = len(recipient_list)
        campaign.save(using=UMBRELLA)

    balance = Balance.objects.using('wallets').get(service_id=get_service_instance().id)
    mail_count = campaign.total - campaign.progress
    if balance.mail_count < mail_count:
        try:
            notify_for_low_messaging_credit(service, balance)
        except:
            logger.error("Failed to notify %s for low messaging credit." % service, exc_info=True)
        return
    connection = mail.get_connection()
    try:
        connection.open()
    except:
        logger.error("Failed to connect to mail server. Please check your internet" % service, exc_info=True)
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
            balance.mail_count -= 1
            balance.save()
        else:
            try:
                with transaction.atomic(using='wallets'):
                    if msg.send():
                        balance.mail_count -= 1
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


def batch_send_SMS(campaign):
    text = campaign.text
    page_count = campaign.page_count
    service = campaign.service
    config = service.config
    label = get_sms_label(config)
    balance = Balance.objects.using('wallets').get(service_id=service.id)
    if len(campaign.recipient_list) == 0:
        recipient_list = []
        if campaign.recipient_src == ALL_COMMUNITY:
            member_queryset = Member.objects.all()
            total = member_queryset.count()
            chunks = total / 500 + 1
            for i in range(chunks):
                start = i * 500
                finish = (i + 1) * 500
                for member in member_queryset[start:finish]:
                    recipient_list.append(member.phone)
                    if len(recipient_list) == 1:
                        campaign.save(using=UMBRELLA)
        elif campaign.recipient_src == PROFILES:
            checked_profile_tag_id_list = campaign.profile_tag_list
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
                        recipient_list.append(member.phone)
                        if len(recipient_list) == 1:
                            campaign.save(using=UMBRELLA)
        campaign.recipient_list = recipient_list
    campaign.total = len(campaign.recipient_list)
    campaign.save(using=UMBRELLA)
    sms_count = page_count * (campaign.total - campaign.progress)
    if balance.sms_count < sms_count:
        try:
            notify_for_low_messaging_credit(service, balance)
        except:
            logger.error("Failed to notify %s for low messaging credit." % service, exc_info=True)
        return
    for recipient in campaign.recipient_list[campaign.progress:]:
        if len(recipient) == 9:
            recipient = '237' + recipient
        try:
            if getattr(settings, 'UNIT_TESTING', False) or getattr(settings, 'ECHO_TEST', False):
                requests.get('http://google.com')
                balance.sms_count -= page_count
                balance.save()
            else:
                send_sms(recipient=recipient, text=text, fail_silently=False)
                balance.sms_count -= page_count
                balance.save()
            SMSObject.objects.using(UMBRELLA).create(recipient=recipient, text=text, label=label, campaign=campaign)
        except:
            SMSObject.objects.using(UMBRELLA).create(recipient=recipient, text=text, label=label, campaign=campaign,
                                                     is_sent=False)
        campaign.progress += 1
        campaign.save(using=UMBRELLA)


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
        community_qs = Member.objects.all()
        subscriber_qs = PWAProfile.objects.all()
        registered_subscriber_list = []
        for subscriber in subscriber_qs:
            try:
                if subscriber.member:
                    registered_subscriber_list.append(subscriber)
            except Member.DoesNotExist:
                pass
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        context['balance'] = balance
        context['campaign_list'] = campaign_list
        context['member_count'] = community_qs.count()
        context['subscriber_count'] = subscriber_qs.count()
        context['registered_subscriber_count'] = len(registered_subscriber_list)
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
        recipient_label = ''
        recipient_label_raw = ''
        checked_profile_tag_id_list = []
        campaign_type = SMS if self.model == SMSCampaign else MAIL
        if filename:
            # Should add somme security check about file existence and type here before attempting to read it
            path = getattr(settings, 'MEDIA_ROOT') + DefaultUploadBackend.UPLOAD_DIR + '/' + filename
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
        elif recipient_list == ALL_SUBSCRIBER:
            recipient_label =  recipient_label_raw = recipient_src = recipient_list
            recipient_list = []
            recipient_profile = ""
        elif recipient_list == REGISTERED_SUBSCRIBER:
            recipient_label =  recipient_label_raw = recipient_src = recipient_list
            recipient_list = []
            recipient_profile = ""
        elif recipient_list == ALL_COMMUNITY:
            recipient_label = recipient_label_raw = recipient_src = recipient_list
            recipient_list = []
            recipient_profile = ""
        elif recipient_list == SELECTED_PROFILES:
            recipient_src = PROFILES
            recipient_list = []
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
        return recipient_label, recipient_label_raw, recipient_src, list(set(recipient_list)), \
               list(set(checked_profile_tag_id_list)), recipient_profile

    def get_campaign_progress(self, request):
        campaign_id = request.GET['campaign_id']
        campaign = self.model._default_manager.using(UMBRELLA).get(pk=campaign_id)
        response = {"progress": campaign.progress, "total": campaign.total}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class PushCampaignList(HybridListView):
    template_name = 'echo/pushcampaign_list.html'
    html_results_template_name = 'echo/snippets/pushcampaign_list_results.html'
    model = PushCampaign
    service = get_service_instance(using=UMBRELLA)
    queryset = PushCampaign.objects.using(UMBRELLA).filter(service=service)
    search_field = 'subject'

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'get_campaign_progress':
            return self.get_campaign_progress(request)
        return super(PushCampaignList, self).get(request, *args, **kwargs)

    def get_campaign_progress(self, request):
        campaign_id = request.GET['campaign_id']
        campaign = self.model._default_manager.using(UMBRELLA).get(pk=campaign_id)
        response = {"campaign subject": campaign.subject, "progress": campaign.progress, "total": campaign.total,
                    "campaign": campaign.to_dict()}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class ChangePushCampaign(CampaignBaseView, ChangeObjectBase):
    template_name = "echo/change_pushcampaign.html"
    model = PushCampaign
    model_admin = PushCampaignAdmin
    context_object_name = 'campaign'
    label_field = 'recipient_label'

    def get_context_data(self, **kwargs):
        context = super(ChangePushCampaign, self).get_context_data(**kwargs)
        obj = context['obj']
        if obj:
            obj.terminated = obj.progress > 0 and obj.progress == obj.total
        return context

    def get_object(self, **kwargs):
        object_id = kwargs.get('object_id')  # May be overridden with the one from GET data
        if object_id:
            try:
                return PushCampaign.objects.using(UMBRELLA).get(pk=object_id)
            except PushCampaign.DoesNotExist:
                raise Http404()

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'toggle_campaign':
            return self.toggle_campaign(request, *args, **kwargs)
        if action == 'run_test':
            return self.run_test(request, *args, **kwargs)
        if action == 'clone_campaign':
            return self.clone_campaign(request, *args, **kwargs)
        return super(ChangePushCampaign, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        object_id = kwargs.get('object_id')
        service = get_service_instance(using=UMBRELLA)
        member = request.user
        mbr = Member.objects.using(UMBRELLA).get(pk=member.id)
        if object_id:
            obj = PushCampaign.objects.using(UMBRELLA).get(pk=object_id)
        else:
            obj = self.model()
        model_form = object_admin.get_form(request)
        form = model_form(request.POST, instance=obj)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            content = form.cleaned_data['content']
            cta_url = form.cleaned_data['cta_url']
            recipient_label, recipient_label_raw, recipient_src, recipient_list, checked_profile_tag_id_list, recipient_profile = self.get_recipient_list(
                request)
            slug = slugify(subject)
            if not object_id:
                obj = PushCampaign(service=service, member=mbr)

            obj.subject = subject
            obj.slug = slug
            obj.content = content
            obj.cta_url = cta_url
            obj.recipient_label = recipient_label
            obj.recipient_label_raw = recipient_label_raw
            obj.recipient_src = recipient_src
            obj.profile_tag_list = checked_profile_tag_id_list
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
                next_url = reverse('echo:change_pushcampaign', args=(obj.id,))
            else:
                next_url = self.get_object_list_url(request, obj, *args, **kwargs)
            if object_id:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode(
                    'utf8') + '</strong> ' + _('successfully updated').decode('utf8'))
            else:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode(
                    'utf8') + '</strong> ' + _('successfully created').decode('utf8'))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)

    def start_campaign(self, request, *args, **kwargs):
        campaign_id = kwargs['object_id']
        campaign = PushCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
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
            Thread(target=batch_send_push, args=(campaign,)).start()
            response = {"success": True, "balance": balance.push_count, "campaign": campaign.to_dict()}
        except Exception as e:
            response = {"error": "Error while submitting your campaign. Please try again later."}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def toggle_campaign(self, request, *args, **kwargs):
        campaign_id = kwargs['object_id']
        campaign = PushCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        campaign.keep_running = not campaign.keep_running
        campaign.save()
        response = {"success": True, "campaign": campaign.to_dict()}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def run_test(self, request, *args, **kwargs):
        # TODO: Implement run_test for push notifications
        pass
        # campaign_id = kwargs['object_id']
        # campaign = PushCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        # test_endpoint_list = request.GET['test_endpoint_list'].split(',')
        # test_endpoint_count = len(test_endpoint_list)
        # service = get_service_instance()
        # balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id=service.id)
        # if balance.push_count < test_endpoint_count:
        #     response = {'error': 'Insufficient Push credit'}
        #     return HttpResponse(json.dumps(response))
        #
        # connection = mail.get_connection()
        # try:
        #     connection.open()
        # except:
        #     response = {'error': 'Failed to connect to push server. Please check your internet'}
        #     return HttpResponse(json.dumps(response))
        # config = service.config
        #
        # warning = []
        #
        # for endpoint in test_endpoint_list[:5]:
        #     if balance.push_count == 0:
        #         warning.append('Insufficient Push Credit')
        #         break
        #     endpoint = endpoint.strip()
        #     subject = "Test - " + campaign.subject
        #     message = campaign.content
        #     # try:
        #     #     member = Member.objects.filter(email=email)[0]
        #     #     message = campaign.content.replace('$client', member.first_name)
        #     # except:
        #     #     message = campaign.content.replace('$client', "")
        #     sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
        #     media_url = ikwen_settings.CLUSTER_MEDIA_URL + service.project_name_slug + '/'
        #     product_list = []
        #     if campaign.items_fk_list:
        #         app_label, model_name = campaign.model_name.split('.')
        #         item_model = get_model(app_label, model_name)
        #         product_list = item_model._default_manager.filter(pk__in=campaign.items_fk_list)
        #     try:
        #         currency = Currency.objects.get(is_base=True)
        #     except Currency.DoesNotExist:
        #         currency = None
        #     html_content = get_mail_content(subject, message, template_name='echo/mails/campaign.html',
        #                                     extra_context={'media_url': media_url, 'product_list': product_list,
        #                                                    'campaign': campaign, 'currency': currency})
        #     msg = EmailMessage(subject, html_content, sender, [endpoint])
        #     msg.content_subtype = "html"
        #     try:
        #         with transaction.atomic(using='wallets'):
        #             balance.mail_count -= 1
        #             balance.save()
        #             if not msg.send():
        #                 transaction.rollback(using='wallets')
        #                 warning.append('Push not sent to %s' % endpoint)
        #     except:
        #         pass
        # try:
        #     connection.close()
        # except:
        #     pass
        #
        # response = {'success': True, 'warning': warning}
        # return HttpResponse(json.dumps(response))

    def clone_campaign(self, request):
        campaign_id = request.GET.get('campaign_id')
        campaign = PushCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        campaign.pk = None
        campaign.progress = 0
        campaign.is_started = False
        campaign.keep_running = False
        campaign.save()
        next_url = reverse('echo:change_pushcampaign', args=(campaign.id,))
        return HttpResponseRedirect(next_url)


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
        response = {"campaign subject": campaign.subject, "progress": campaign.progress, "total": campaign.total,
                    "campaign": campaign.to_dict()}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class ChangeMailCampaign(CampaignBaseView, ChangeObjectBase):
    template_name = "echo/change_mailcampaign.html"
    model = MailCampaign
    model_admin = MailCampaignAdmin
    context_object_name = 'campaign'
    label_field = 'recipient_label'

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
        context['items_fk_list'] = ','.join(items_fk_list)
        try:
            context['item_list'] = get_item_list('kako.Product', items_fk_list)
        except:
            pass
        try:
            context['add_products_url'] = reverse(
                'kako:product_list') + '?smart_link=yes&campaign=yes&smart_object_id=' + obj.id
        except:
            pass
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
        if action == 'clone_campaign':
            return self.clone_campaign(request, *args, **kwargs)
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
            recipient_label, recipient_label_raw, recipient_src, recipient_list, checked_profile_tag_id_list, recipient_profile = self.get_recipient_list(
                request)
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
            obj.profile_tag_list = checked_profile_tag_id_list
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
                next_url = reverse('echo:change_mailcampaign', args=(obj.id,))
            else:
                next_url = self.get_object_list_url(request, obj, *args, **kwargs)
            if object_id:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode(
                    'utf8') + '</strong> ' + _('successfully updated').decode('utf8'))
            else:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode(
                    'utf8') + '</strong> ' + _('successfully created').decode('utf8'))
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
            Thread(target=batch_send_mail, args=(campaign,)).start()
            response = {"success": True, "balance": balance.mail_count, "campaign": campaign.to_dict()}
        except Exception as e:
            response = {"error": "Error while submitting your campaign. Please try again later."}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def toggle_campaign(self, request, *args, **kwargs):
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

    def clone_campaign(self, request):
        campaign_id = request.GET.get('campaign_id')
        campaign = MailCampaign.objects.using(UMBRELLA).get(pk=campaign_id)
        campaign.pk = None
        campaign.progress = 0
        campaign.is_started = False
        campaign.keep_running = False
        campaign.save()
        next_url = reverse('echo:change_mailcampaign', args=(campaign.id,))
        return HttpResponseRedirect(next_url)


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
        recipient_label, recipient_label_raw, recipient_src, recipient_list, checked_profile_tag_id_list, recipient_profile = self.get_recipient_list(
            request)
        slug = slugify(subject)
        page_count = count_pages(txt)
        service = get_service_instance(using=UMBRELLA)
        mbr = Member.objects.using(UMBRELLA).get(pk=member.id)
        balance = Balance.objects.using('wallets').get(service_id=get_service_instance().id)
        campaign = SMSCampaign.objects.using(UMBRELLA).create(service=service, member=mbr, subject=subject,
                                                              slug=slug, text=txt,
                                                              recipient_list=recipient_list,
                                                              recipient_src=recipient_src,
                                                              recipient_label=recipient_label,
                                                              page_count=page_count)
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send_SMS(campaign)
            response = {"success": True, "balance": balance.sms_count, "campaign": campaign.to_dict()}
        else:
            try:
                Thread(target=batch_send_SMS, args=(campaign,)).start()
                response = {"success": True, "balance": balance.sms_count, "campaign": campaign.to_dict()}
            except Exception as e:
                response = {"error": "Error while submitting your campaign. Please try again later."}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class SMSHistory(TemplateView):
    template_name = "echo/sms_history.html"


# class MailHistory(TemplateView):
#     template_name = "echo/mail_history.html"


class PushBundle(TemplateView):
    template_name = "echo/push_bundle.html"

    def get_context_data(self, **kwargs):
        context = super(PushBundle, self).get_context_data(**kwargs)
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        bundle_list = Bundle.objects.using(UMBRELLA).filter(type=PUSH, is_active=True)
        context['balance'] = balance
        context['bundle_list'] = bundle_list
        return context


class MailBundle(TemplateView):
    template_name = "echo/mail_bundle.html"

    def get_context_data(self, **kwargs):
        context = super(MailBundle, self).get_context_data(**kwargs)
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        bundle_list = Bundle.objects.using(UMBRELLA).filter(type=MAIL, is_active=True)
        context['balance'] = balance
        context['bundle_list'] = bundle_list
        return context


class SMSBundle(TemplateView):
    template_name = "echo/sms_bundle.html"

    def get_context_data(self, **kwargs):
        context = super(SMSBundle, self).get_context_data(**kwargs)
        balance, update = Balance.objects.using('wallets').get_or_create(service_id=get_service_instance().id)
        bundle_list = Bundle.objects.using(UMBRELLA).filter(type=SMS, is_active=True)
        context['balance'] = balance
        context['bundle_list'] = bundle_list
        return context


class PopupList(HybridListView):
    model = PopUp
    search_field = 'name'
    ordering = ('order_of_appearance',)


class ChangePopup(ChangeObjectBase):
    model = PopUp
    model_admin = PopUpAdmin


csv_uploader = AjaxFileUploader(DefaultUploadBackend)


# def render_credit_refill_event(event, request):
#     from ikwen.conf import settings as ikwen_settings
#     ikwen_service = Service.objects.using(UMBRELLA).get(pk=ikwen_settings.IKWEN_SERVICE_ID)
#     currency_symbol = ikwen_service.config.currency_symbol
#     try:
#         refill = Refill.objects.using(UMBRELLA).get(pk=event.object_id)
#     except Refill.DoesNotExist:
#         return ''
#     service_deployed = invoice.service
#     member = service_deployed.member
#     if request.GET['member_id'] != member.id:
#         data = {'title': 'New service deployed',
#                 'details': service_deployed.details,
#                 'member': member,
#                 'service_deployed': True}
#         template_name = 'billing/events/notice.html'
#     else:
#         template_name = 'core/events/service_deployed.html'
#         data = {'obj': invoice,
#                 'project_name': service_deployed.project_name,
#                 'service_url': service_deployed.url,
#                 'due_date': invoice.due_date,
#                 'show_pay_now': invoice.status != Invoice.PAID}
#     data.update({'currency_symbol': currency_symbol,
#                  'details_url': IKWEN_BASE_URL + reverse('billing:invoice_detail', args=(invoice.id,)),
#                  'amount': invoice.amount,
#                  'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
#     c = Context(data)
#     html_template = get_template(template_name)
#     return html_template.render(c)
