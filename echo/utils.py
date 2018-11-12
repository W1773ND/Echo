# -*- coding: utf-8 -*-
import logging
from django.core.mail import EmailMessage
from django.utils.translation import activate, gettext as _
from ikwen.core.utils import get_mail_content

logger = logging.getLogger('ikwen.crons')


def notify_for_empty_mail_credit(service):
    """
    Sends mail to Service owner to notify for empty mail credit
    """
    member = service.member
    if member.language:
        activate(member.language)
    else:
        activate('en')
    subject = _("Your just run out of e-mail credit.")
    html_content = get_mail_content(subject, template_name='echo/mails/empty_email_credit.html')
    sender = 'ikwen <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [member.email])
    msg.content_subtype = "html"
    msg.send()


def notify_for_empty_sms_credit(service):
    """
    Sends mail to Service owner to notify for empty SMS credit
    """
    member = service.member
    if member.language:
        activate(member.language)
    else:
        activate('en')
    subject = _("Your just run out of SMS credit.")
    html_content = get_mail_content(subject, template_name='echo/mails/empty_sms_credit.html')
    sender = 'ikwen <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [member.email])
    msg.content_subtype = "html"
    msg.send()


def notify_for_empty_mail_and_sms_credit(service):
    """
    Sends mail to Service owner to notify for empty mail and SMS credit
    """
    member = service.member
    if member.language:
        activate(member.language)
    else:
        activate('en')
    subject = _("Your mail and SMS credits are empty.")
    html_content = get_mail_content(subject, template_name='echo/mails/empty_mail_and_sms_credit.html')
    sender = 'ikwen <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [member.email])
    msg.content_subtype = "html"
    msg.send()
