# -*- coding: utf-8 -*-

import os
import sys
import logging

sys.path.append("/home/libran/virtualenv/lib/python2.7/site-packages")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen.conf.settings")

from echo.models import Balance

logger = logging.getLogger('ikwen.crons')


FREE_BALANCE = 200


def reset_email_balance():
    Balance.objects.using('wallets').update(mail_count=FREE_BALANCE)


if __name__ == '__main__':
    try:
        reset_email_balance()
    except:
        logger.error("Fatal error occurred, cron_sender not run", exc_info=True)
