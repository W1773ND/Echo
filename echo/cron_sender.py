# -*- coding: utf-8 -*-

import os
import sys
import logging
from datetime import datetime, timedelta
from threading import Thread

sys.path.append("/home/libran/virtualenv/lib/python2.7/site-packages")

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen.conf.settings")

from django.conf import settings
from echo.models import SMSCampaign, MailCampaign
from echo.views import batch_send, batch_send_mail

from ikwen.core.log import CRONS_LOGGING
logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


def restart_sms_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    raw_query = {"$where": "function() {return this.progress < this.total}"}
    campaign_qs = SMSCampaign.objects.raw_query(raw_query).select_related('service')
    for campaign in campaign_qs:
        if campaign.updated_on >= timeout:
            continue
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send(campaign)
        else:
            Thread(target=batch_send, args=(campaign,)).start()


def restart_mail_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    raw_query = {"$where": "function() {return this.progress < this.total}"}
    campaign_qs = MailCampaign.objects.raw_query(raw_query).select_related('service')
    for campaign in campaign_qs:
        if campaign.keep_running:
            if campaign.updated_on >= timeout:
                continue
            if getattr(settings, 'UNIT_TESTING', False):
                batch_send_mail(campaign)
            else:
                Thread(target=batch_send_mail, args=(campaign,)).start()


if __name__ == '__main__':
    try:
        restart_sms_batch()
        restart_mail_batch()
    except:
        logger.error("Fatal error occurred, cron_sender not run", exc_info=True)
