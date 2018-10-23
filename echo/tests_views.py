from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.core.utils import get_service_instance

from echo.models import Campaign



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
        response = self.client.get(reverse('echo:sms_history'))
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
        response = self.client.get(reverse('echo:mail_history'))
        self.assertEqual(response.status_code, 200)

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    # def test_SMSCampaign_start_campaign_with_insufficient_balance(self):
    #     self.client.login(username='arch', password='admin')
    #     service = get_service_instance()
    #     campaign = Campaign.objects.using(echo).get(pk='56eb6d04b37b3379b531e011')
    #     member = campaign.member
    #     type = campaign.type
    #     recipient_list = campaign.recipient_list
    #     text = campaign.text
    #     page_count = campaign.page_count
    #     subject = campaign.subject
    #     slug = campaign.slug
    #     total = campaign.total
    #     progress = campaign.progress
    #     response = self.client.post(reverse('echo:sms_campaign') + '?action=start_campaign',
    #
    #     cr_profile = CROperatorProfile.objects.using(echo).get(service=service)
    #     self.assertEqual(cr_profile.plan, plan)
