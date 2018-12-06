# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime, timedelta
from threading import Thread

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen.conf.settings")

from django.conf import settings
from echo.models import Campaign
from echo.views import batch_send

from ikwen.core.log import CRONS_LOGGING
logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


def restart_batch():
    timeout = datetime.now() - timedelta(minutes=5)
    raw_query = {"$where": "function() {return this.progress < this.total}"}
    campaign_list = list(Campaign.objects.raw_query(raw_query).select_related('service').filter(updated_on__lt=timeout))
    for campaign in campaign_list:
        if getattr(settings, 'UNIT_TESTING', False):
            batch_send(campaign)
        else:
            Thread(target=batch_send, args=(campaign,)).start()


if __name__ == '__main__':
    try:
        restart_batch()
    except:
        logger.error("Fatal error occured, cyclic revivals not run", exc_info=True)
