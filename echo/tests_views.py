# -*- coding: utf-8 -*-
import json

import time
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.core.utils import get_service_instance

from conf.settings import WALLETS_DB_ALIAS
from echo.models import Campaign, Balance
from echo.views import restart_batch, count_pages


def wipe_test_data(alias='default'):
    """
    This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
    each test. So the flush is performed manually with this custom tearDown()
    """
    import ikwen.core.models
    import ikwen.accesscontrol.models
    import permission_backend_nonrel.models
    import echo.models

    Group.objects.using(alias).all().delete()
    for name in ('Application', 'Service', 'Config', 'ConsoleEventType', 'ConsoleEvent', 'Country', ):
        model = getattr(ikwen.core.models, name)
        model.objects.using(alias).all().delete()
    for name in ('Member', 'AccessRequest', ):
        model = getattr(ikwen.accesscontrol.models, name)
        model.objects.using(alias).all().delete()
    for name in ('UserPermissionList', 'GroupPermissionList',):
        model = getattr(permission_backend_nonrel.models, name)
        model.objects.using(alias).all().delete()
    for name in ('Campaign', 'SMS', 'Balance', 'Refill', 'Bundle', ):
        model = getattr(echo.models, name)
        model.objects.using(alias).all().delete()


class CampaignTestCase(unittest.TestCase):
    fixture = ['echo_campaign.yaml', 'ikwen_members.yaml', 'setup_data.yaml']

    def setUp(self):
        self.client = Client()
        call_command('loaddata', 'echo_balance.yaml', database=WALLETS_DB_ALIAS)
        for fixture in self.fixture:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_SMSCampaign(self):
        """
        Make sure the url is reachable
        """
        self.client.login(username='arch', password='admin')
        response = self.client.get(reverse('echo:sms_campaign'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_Sms_bundle_page(self):
        """
        Make sure the url is reachable
        """
        self.client.login(username='arch', password='admin')
        response = self.client.get(reverse('echo:sms_bundle'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_Sms_history_page(self):
        """
        Make sure the url is reachable
        """
        self.client.login(username='arch', password='admin')
        response = self.client.get(reverse('echo:sms_hist'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_Mail_campaign_page(self):
        """
        Make sure the url is reachable
        """
        self.client.login(username='arch', password='admin')
        response = self.client.get(reverse('echo:mail_campaign'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_Mail_bundle_page(self):
        """
        Make sure the url is reachable
        """
        self.client.login(username='arch', password='admin')
        response = self.client.get(reverse('echo:mail_bundle'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_Mail_history_page(self):
        """
        Make sure the url is reachable
        """
        self.client.login(username='arch', password='admin')
        response = self.client.get(reverse('echo:mail_hist'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
                       UNIT_TESTING=True)
    def test_SMSCampaign_start_campaign_with_insufficient_balance(self):
        self.client.login(username='arch', password='admin')
        recipient_list = "693655488,658458741,5689784125"
        txt = 'CAMP UniTest'
        subject = 'Unitest campaign'
        response = self.client.get(reverse('echo:sms_campaign'),
                                   {'action': 'start_campaign', 'recipients': recipient_list,
                                    'subject': subject, 'txt': txt})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertEqual(result['error'], 'Insufficient SMS balance.')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
                       UNIT_TESTING=True)
    def test_SMSCampaign_start_campaign__with_csv_file_reading_and__insufficient_balance(self):
        self.client.login(username='arch', password='admin')
        recipient_list = []
        filename = "ikwen_sms_campaign_test.csv"
        txt = 'CAMP1 UniTest'
        subject = 'Unitest campaign 1'
        response = self.client.get(reverse('echo:sms_campaign'),
                                   {'action': 'start_campaign', 'filename': filename, 'recipients': recipient_list,
                                    'subject': subject, 'txt': txt})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertEqual(result['error'], 'Insufficient SMS balance.')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_SMSCampaign_start_campaign_with_sufficient_balance(self):
        self.client.login(username='arch', password='admin')
        recipient_list = "693655488,658458741,5689784125"
        txt = 'CAMP2 UniTest'
        subject = 'Unitest campaign 2'
        response = self.client.get(reverse('echo:sms_campaign'),
                                   {'action': 'start_campaign', 'subject': subject, 'recipients': recipient_list,
                                    'txt': txt})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result['success'])
        campaign = Campaign.objects.get(subject=subject)
        self.assertEqual(campaign.progress, 3)
        balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id='56eb6d04b37b3379b531b102')
        self.assertEqual(balance.sms_count, 7)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_SMSCampaign_start_campaign_with_csv_file_reading_and_sufficient_balance(self):
        self.client.login(username='arch', password='admin')
        recipient_list = []
        filename = "ikwen_sms_campaign_test.csv"
        txt = 'CAMP3 UniTest'
        subject = 'Unitest campaign 3'
        response = self.client.get(reverse('echo:sms_campaign'),
                                   {'action': 'start_campaign', 'filename': filename, 'recipients': recipient_list,
                                    'subject': subject, 'txt': txt})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result['success'])
        campaign = Campaign.objects.get(subject=subject)
        self.assertEqual(campaign.progress, 8)
        self.assertEqual(int(campaign.recipient_list[2]), 693799546)
        balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id='56eb6d04b37b3379b531b102')
        self.assertEqual(balance.sms_count, 2)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_restart_batch(self):
        restart_batch()
        campaign = Campaign.objects.get(service='56eb6d04b37b3379b531b102')
        self.assertGreater(campaign.progress, 0)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_count_pages_with_2_page_and_without_special_character(self):
        text = "sldkhfsldfhklsd flksdh clshc dskhclshdcl kdshcl kshdcl kshlck sdlhkchlskd clkhc " \
               "slkdhklshdc kldshclksd hclksldkhc lkshdcsdklch kdchkdchlkdchkldc hhslkdclkdschkde"
        self.assertEqual(count_pages(text), 2)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_count_pages_with_3_pages_contains_special_character(self):
        text = "'qskdhqklsdql qlscg lqsgclkq hsckmlqshc kqslhcl" \
               "hclqskhclkqsh ck qshlclkqs chlq"
        self.assertEqual(count_pages(text), 2)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_count_pages_with_2_pages_contains_special_character_and_ex_character_count_double(self):
        text = "çsdkskdncsd clksdcnkcn lsdknc lksdcnsdlkcnlsdkcndkcnlksnckndclksndkdç(]"
        self.assertEqual(count_pages(text), 2)






