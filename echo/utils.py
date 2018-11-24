# -*- coding: utf-8 -*-
import logging
from threading import Thread

from django.core.mail import EmailMessage
from django.utils.translation import activate, gettext as _
from ikwen.core.models import Service
from ikwen.core.utils import get_mail_content
from ikwen.conf.settings import IKWEN_SERVICE_ID

logger = logging.getLogger('ikwen.crons')

EMAIL = "Email"
SMS = "SMS"
EMAIL_AND_SMS = "Email and SMS"


def notify_for_empty_messaging_credit(service, account):
    """
    Sends mail to Service owner to notify for empty SMS credit
    """
    member = service.member
    if member.language:
        activate(member.language)
    else:
        activate('en')
    if account == EMAIL_AND_SMS:
        subject = _("Your are out of mail and SMS credit.")
    elif account == SMS:
        subject = _("Your are out of SMS credit.")
    else:
        subject = _("Your are out of Email credit.")
    ikwen_service = Service.objects.get(pk=IKWEN_SERVICE_ID)
    html_content = get_mail_content(subject, service=ikwen_service, template_name='echo/mails/empty_messaging_credit.html')
    sender = 'ikwen <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [member.email])
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg, )).start()
