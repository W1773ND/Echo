# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta
from threading import Thread

import requests
from django.conf import settings
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.core.utils import send_sms, get_service_instance
from math import ceil

from echo.models import Campaign, SMS, Balance

sms_normal_count = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
                    'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S',
                    'T', 'U', 'V', 'W', 'X', 'Y', 'Z', u'Ä', u'ä', u'à', u'Å', u'å', u'Æ', u'æ', u'ß', u'Ç', u'è', u'é',
                    u'É', u'ì', u'Ö', u'ö', u'ò', u'Ø', u'ø', u'Ñ', u'ñ', u'Ü', u'ü', u'ù', u'#', u'¤', u'%', u'&',
                    u'(', u')', u'*', u'+', u',', u'–', u'.', u'/', u':', u';', u' <', u'>', u'=', u'§', u'$', u'!',
                    u'?', u'£', u'¿', u'¡', u'@', u'¥', u'Δ', u'Φ', u'Γ', u'Λ', u'Ω', u'Π', u'Ψ', u'Σ', u'Θ', u'Ξ',
                    u'»', u'‘']
sms_double_count = [u'^', u'|', u'€', u'}', u'{', u'[', u'~', u']', u'\\']

config = get_service_instance().config
label = config.company_name.strip()
if len(label) > 15:
    label = label.split(' ')[0][:15]
label = slugify(label)
label = ''.join([tk.capitalize() for tk in label.split('-') if tk])


def batch_send(campaign, balance):
    fh = None
    text = campaign.text
    filename = campaign.filename
    page_count = campaign.page_count
    if filename:
        path = getattr(settings, 'MEDIA_ROOT') + filename
        fh = open(path, 'r')
        campaign.recipient_list = fh.readlines()
    for recipient in campaign.recipient_list[campaign.progress:]:
        if len(recipient) == 9:
            recipient = '237' + recipient
    for recipient in campaign.recipient_list[campaign.progress:]:
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
    if fh:
        fh.close()


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


def restart_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    campaign_list = Campaign.objects.filter(progress__lt=F('total'), updated_on__lt=timeout)
    for campaign in campaign_list:
        balance = Balance(service=campaign.service)
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

        balance = Balance.objects.get(service=get_service_instance())
        # criteria = request.GET.get('criteria')
        subject = request.GET.get('subject')
        slug = slugify(subject)
        txt = request.GET.get('txt')
        filename = request.GET.get('filename')
        recipient_list = []
        if filename:
            path = getattr(settings, 'MEDIA_ROOT') + filename
            fh = open(path, 'r')
            recipient_count = len(fh.readlines())
            fh.close()
        else:
            recipient_list = request.GET.get('recipients').strip().split(',')
            recipient_count = len(recipient_list)
        page_count = count_pages(txt)
        sms_count = page_count * recipient_count
        if balance.sms_count < sms_count:
            response = {"error": _("Insufficient SMS balance.")}
            return HttpResponse(
                json.dumps(response),
                'content-type: text/json'
            )
        balance.sms_count -= sms_count
        balance.save()
        campaign = Campaign.objects.create(member=member, subject=subject, type="SMS", slug=slug,
                                           recipient_list=recipient_list, total=len(recipient_list))
        # campaign = Campaign.objects.create(member=member, subject=subject, type="SMS", slug=slug, total=recipient_count)
        # sms = SMS.objects.create(label=label, recipient=recipient_list, text=txt, campaign=campaign)
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
