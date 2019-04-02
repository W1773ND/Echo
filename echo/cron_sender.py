# -*- coding: utf-8 -*-

import os
import sys
import logging
from datetime import datetime, timedelta
from threading import Thread

sys.path.append("/home/libran/virtualenv/lib/python2.7/site-packages")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen.conf.settings")

from django.conf import settings
from echo.models import SMSCampaign, MailCampaign, SMS, MAIL
from echo.views import batch_send, batch_send_mail

from ikwen.core.log import CRONS_LOGGING
logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


def restart_sms_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    raw_query = {"$where": "function() {return this.progress < this.total}"}
    campaign_list = SMSCampaign.objects.raw_query(raw_query).select_related('service').filter(updated_on__lt=timeout)
    for campaign in campaign_list:
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send(campaign)
        else:
            Thread(target=batch_send, args=(campaign,)).start()


def restart_mail_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    raw_query = {"$where": "function() {return this.progress < this.total}"}
    campaign_list = MailCampaign.objects.raw_query(raw_query).select_related('service').filter(updated_on__lt=timeout)
    for campaign in campaign_list:
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send(campaign)
        else:
            Thread(target=batch_send_mail, args=(campaign,)).start()


if __name__ == '__main__':
    try:
        restart_sms_batch()
        restart_mail_batch()
    except:
        logger.error("Fatal error occured, cyclic revivals not run", exc_info=True)
