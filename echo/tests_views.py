import json

import time
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.core.utils import get_service_instance

from echo.models import Campaign, Balance
from echo.views import restart_batch, batch_send



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
        for fixture in self.fixture:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()
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

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_SMSCampaign_start_campaign_with_insufficient_balance(self):
        self.client.login(username='arch', password='admin')
        recipient_list = "693655488,658458741,5689784125"
        txt = 'CAMP1 UniTest'
        subject = 'Unitest campaign 1'
        response = self.client.get(reverse('echo:sms_campaign'),
                                   {'action': 'start_campaign', 'subject': subject, 'recipients': recipient_list,
                                    'txt': txt})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertEqual(result['error'], 'Insufficient SMS balance.')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_SMSCampaign_start_campaign_with_sufficient_balance(self):
        self.client.login(username='arch', password='admin')
        recipient_list = "693655488,658458741,5689784125"
        txt = 'CAMP1 UniTest'
        subject = 'Unitest campaign 1'
        response = self.client.get(reverse('echo:sms_campaign'),
                                   {'action': 'start_campaign', 'subject': subject, 'recipients': recipient_list,
                                    'txt': txt})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)
        self.assertTrue(result['success'])
        campaign = Campaign.objects.get(subject=subject)
        self.assertEqual(campaign.progress, 3)
        balance = Balance.objects.get(service='56eb6d04b37b3379b531b102')
        self.assertEqual(balance.sms_count, 7)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       UNIT_TESTING=True)
    def test_restart_batch(self):
        restart_batch()
        campaign = Campaign.objects.get(service='56eb6d04b37b3379b531b102')
        self.assertGreater(campaign.progress, 0)






