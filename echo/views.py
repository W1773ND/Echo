# -*- coding: utf-8 -*-
import csv
import json
from datetime import datetime, timedelta
from threading import Thread

import requests
from ajaxuploader.views import AjaxFileUploader
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.core.utils import send_sms, get_service_instance, DefaultUploadBackend
from ikwen.accesscontrol.models import Member
from math import ceil

from echo.models import Campaign, SMS, Balance

# from echo.forms import CSVFileForm

sms_normal_count = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
                    'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S',
                    'T', 'U', 'V', 'W', 'X', 'Y', 'Z', u'Ä', u'ä', u'à', u'Å', u'å', u'Æ', u'æ', u'ß', u'Ç', u'è', u'é',
                    u'É', u'ì', u'Ö', u'ö', u'ò', u'Ø', u'ø', u'Ñ', u'ñ', u'Ü', u'ü', u'ù', u'#', u'¤', u'%', u'&',
                    u'(', u')', u'*', u'+', u',', u'–', u'.', u'/', u':', u';', u' <', u'>', u'=', u'§', u'$', u'!',
                    u'?', u'£', u'¿', u'¡', u'@', u'¥', u'Δ', u'Φ', u'Γ', u'Λ', u'Ω', u'Π', u'Ψ', u'Σ', u'Θ', u'Ξ',
                    u'»', u'‘']
sms_double_count = [u'^', u'|', u'€', u'}', u'{', u'[', u'~', u']', u'\\']

ALL_COMMUNITY = "[All Community]"
UPLOAD_DIR = "/uploads/"

config = get_service_instance().config
label = config.company_name.strip()
if len(label) > 15:
    label = label.split(' ')[0][:15]
label = slugify(label)
label = ''.join([tk.capitalize() for tk in label.split('-') if tk])


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


def batch_send(campaign, balance):
    text = campaign.text
    page_count = campaign.page_count
    # fh = None
    # filename = campaign.filename
    # if filename:
    #     path = getattr(settings, 'MEDIA_ROOT') + filename
    #     fh = open(path, 'r')
    #     campaign.recipient_list = fh.readlines()
    for recipient in campaign.recipient_list[campaign.progress:]:
        if len(recipient) == 9:
            recipient = '237' + recipient
        try:
            if not getattr(settings, 'UNIT_TESTING', False):
                if getattr(settings, 'REQUEST_TESTING', False):
                    requests.get('http://google.com')
                else:
                    send_sms(recipient=recipient, text=text, fail_silently=False)
            SMS.objects.create(recipient=recipient, text=text, label=label, campaign=campaign)
        except:
            SMS.objects.create(recipient=recipient, text=text, label=label, campaign=campaign, is_sent=False)
            balance.sms_count += page_count
            balance.save()
        campaign.progress += 1
        campaign.save()
    # if fh:
    #     fh.close()


def restart_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    raw_query = {"$where": "function() {return this.progress < this.total}"}
    campaign_list = list(Campaign.objects.raw_query(raw_query).filter(updated_on__lt=timeout))
    for campaign in campaign_list:
        balance = Balance(service=campaign.service)
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send(campaign, balance)
        else:
            Thread(target=batch_send, args=(campaign, balance)).start()


class SMSCampaign(TemplateView):
    template_name = "echo/sms_campaign.html"

    def get_context_data(self, **kwargs):
        context = super(SMSCampaign, self).get_context_data(**kwargs)
        campaign_list = Campaign.objects.all().order_by("-id")[:5]
        for campaign in campaign_list:
            campaign.progress_rate = (campaign.progress / campaign.total) * 100
        balance, update = Balance.objects.get_or_create(service=get_service_instance())
        context['balance'] = balance
        context['campaign_list'] = campaign_list
        context['member_count'] = Member.objects.all().count()
        return context

    def get(self, request, *args, **kwargs):
        # csv_file = CSVFile.objects.all().order_by("-id")[:1]
        action = request.GET.get('action')
        if action == 'start_campaign':
            return self.start_campaign(request)
        if action == 'get_campaign_progress':
            return self.get_campaign_progress(request)
        # if action == 'view_contact_file':
        ##     return render(self.request, 'echo/sms_campaign.html', {'file': csv_file}) ##
        #     return self.view_contact_file(request)
        return super(SMSCampaign, self).get(request, *args, **kwargs)

    # def post(self, request):
    #     csv_file = CSVFileForm(self.request.POST, self.request.FILES)
    #     if csv_file.is_valid():
    #         csv_file.save()
    #         response = {"is_valid": True}
    #     else:
    #         response = {"is_valid": False}
    #     return HttpResponse(
    #         json.dumps(response),
    #         'content-type: text/json'
    #     )

    def start_campaign(self, request):
        member = request.user

        subject = request.GET.get('subject')
        slug = slugify(subject)
        txt = request.GET.get('txt')
        filename = request.GET.get('filename')
        recipient_list = request.GET.get('recipients')
        if filename:

            # Should add somme security check about file existence and type here before attempting to read it

            path = getattr(settings, 'MEDIA_ROOT') + UPLOAD_DIR + filename
            recipient_list = []

            with open(path, 'r') as fh:
                for recipient in fh.readlines():
                    recipient_list.append(recipient)
            fh.close()
            recipient_count = len(recipient_list)
        elif recipient_list == ALL_COMMUNITY:
            recipient_list = []
            community_member = Member.objects.all()
            for member in community_member:
                recipient_list.append(member.phone)
            recipient_count = len(recipient_list)
        else:
            recipient_list = recipient_list.strip().split(',')
            recipient_count = len(recipient_list)
        page_count = count_pages(txt)
        sms_count = page_count * recipient_count

        # if getattr(settings, 'UNIT_TESTING', False):
        with transaction.atomic():
            balance = Balance.objects.get(service=get_service_instance())
            if balance.sms_count < sms_count:
                response = {"error": _("Insufficient SMS balance.")}
                return HttpResponse(
                    json.dumps(response),
                    'content-type: text/json'
                )
            balance.sms_count -= sms_count
            balance.save()
        # else:
        #     # "transaction.atomic" instruction locks database during all operations inside "with" block
        #     with transaction.atomic():
        #         balance = Balance.objects.using('wallets').get(service=get_service_instance())
        #         if balance.sms_count < sms_count:
        #             response = {"error": _("Insufficient SMS balance.")}
        #             return HttpResponse(
        #                 json.dumps(response),
        #                 'content-type: text/json'
        #             )
        #         balance.sms_count -= sms_count
        #         balance.save()
        campaign = Campaign.objects.create(member=member, subject=subject, type="SMS", slug=slug,
                                           recipient_list=recipient_list, total=sms_count)
        # campaign = Campaign.objects.create(member=member, subject=subject, type="SMS", slug=slug,
        #                                    total=recipient_count)
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send(campaign, balance)
        else:
            Thread(target=batch_send, args=(campaign, balance)).start()
        response = {"success": True, "campaign": campaign.to_dict()}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )

    def get_campaign_progress(self, request):
        campaign_id = request.GET['campaign_id']
        campaign = Campaign.objects.get(pk=campaign_id)
        response = {"progress": campaign.progress, "total": campaign.total}
        return HttpResponse(
            json.dumps(response),
            'content-type: text/json'
        )


class SMSHistory(TemplateView):
    template_name = "echo/sms_history.html"


class SMSBundle(TemplateView):
    template_name = "echo/sms_bundle.html"


class MailCampaign(TemplateView):
    template_name = "echo/mail_campaign.html"


class MailHistory(TemplateView):
    template_name = "echo/mail_history.html"


class MailBundle(TemplateView):
    template_name = "echo/mail_bundle.html"


csv_uploader = AjaxFileUploader(DefaultUploadBackend)
