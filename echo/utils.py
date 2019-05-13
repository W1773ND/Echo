# -*- coding: utf-8 -*-
import logging
from copy import copy
from datetime import datetime
from math import ceil
from threading import Thread

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.utils.translation import activate, gettext as _
from ikwen.core.models import Service
from ikwen.core.utils import get_mail_content
from ikwen.conf.settings import IKWEN_SERVICE_ID

EMAIL = "Email"
SMS = "SMS"
EMAIL_AND_SMS = "Email and SMS"

LOW_SMS_LIMIT = 100
LOW_MAIL_LIMIT = 500

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


def notify_for_low_messaging_credit(service, balance):
    """
    Sends mail to Service owner to notify for low Messaging credit
    """
    if getattr(settings, 'UNIT_TESTING', False):
        return
    now = datetime.now()
    member = service.member
    if member.language:
        activate(member.language)
    else:
        activate('en')
    if 0 < balance.sms_count < LOW_SMS_LIMIT:
        subject = _("Your are running out of SMS credit.")
        last_notice = copy(balance.last_low_sms_notice)
        account = "SMS"
        credit_left = balance.sms_count
        balance.last_low_sms_notice = now
        refill_url = service.url + reverse('ikwen:service_detail')
    elif 0 < balance.mail_count < LOW_MAIL_LIMIT:
        subject = _("Your are running out of Email credit.")
        last_notice = copy(balance.last_low_mail_notice)
        account = "Email"
        credit_left = balance.mail_count
        balance.last_low_mail_notice = now
        refill_url = service.url + reverse('ikwen:service_detail')
    balance.save()

    if last_notice:
        diff = now - last_notice
        if diff.days < 2:
            return

    ikwen_service = Service.objects.get(pk=IKWEN_SERVICE_ID)
    html_content = get_mail_content(subject, service=ikwen_service, template_name='echo/mails/low_messaging_credit.html',
                                    extra_context={'account': account, 'credit_left': credit_left,
                                                   'website': service, 'refill_url': refill_url})
    sender = 'ikwen <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [member.email])
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg, )).start()


def notify_for_empty_messaging_credit(service, balance):
    """
    Sends mail to Service owner to notify for empty SMS credit
    """
    if getattr(settings, 'UNIT_TESTING', False):
        return
    now = datetime.now()
    member = service.member
    if member.language:
        activate(member.language)
    else:
        activate('en')
    if balance.sms_count == 0 and balance.mail_count == 0:
        subject = _("Your are out of Email and SMS credit.")
        last_notice = copy(max(balance.last_empty_mail_notice, balance.last_empty_sms_notice))
        account = "Email and SMS"
        balance.last_empty_mail_notice = now
        balance.last_empty_sms_notice = now
    elif balance.sms_count == 0:
        subject = _("Your are out of SMS credit.")
        last_notice = copy(balance.last_empty_sms_notice)
        account = "SMS"
        balance.last_empty_sms_notice = now
    else:
        subject = _("Your are out of Email credit.")
        last_notice = copy(balance.last_empty_mail_notice)
        account = "Email"
        balance.last_empty_mail_notice = now
    refill_url = service.url + reverse('ikwen:service_detail')
    balance.save()

    if last_notice:
        diff = now - last_notice
        if diff.days < 2:
            return

    ikwen_service = Service.objects.get(pk=IKWEN_SERVICE_ID)
    html_content = get_mail_content(subject, service=ikwen_service, template_name='echo/mails/empty_messaging_credit.html',
                                    extra_context={'account': account, 'website': service, 'refill_url': refill_url})
    sender = 'ikwen <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [member.email])
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg, )).start()
