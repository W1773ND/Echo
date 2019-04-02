from django.conf.urls import url, patterns
from django.contrib.auth.decorators import permission_required

from echo.views import SMSCampaignView, SMSHistory, SMSBundle, MailCampaignList, ChangeMailCampaign, MailHistory, MailBundle, csv_uploader

urlpatterns = patterns(
    '',
    url(r'^sms/$', permission_required('echo.ik_messaging_campaign')(SMSCampaignView.as_view()), name='sms_campaign'),
    url(r'^smsHistory/$', permission_required('echo.ik_messaging_campaign')(SMSHistory.as_view()), name='sms_history'),
    url(r'^smsBundles/$', permission_required('echo.ik_messaging_campaign')(SMSBundle.as_view()), name='sms_bundle'),
    url(r'^mailCampaignList/$', permission_required('echo.ik_messaging_campaign')(MailCampaignList.as_view()), name='mailcampaign_list'),
    url(r'^mailCampaign/$', permission_required('echo.ik_messaging_campaign')(ChangeMailCampaign.as_view()), name='change_mailcampaign'),
    url(r'^mailCampaign/(?P<object_id>[-\w]+)/$', permission_required('echo.ik_messaging_campaign')(ChangeMailCampaign.as_view()), name='change_mailcampaign'),
    url(r'^mailHistory/$', permission_required('echo.ik_messaging_campaign')(MailHistory.as_view()), name='mail_history'),
    url(r'^mailBundles/$', permission_required('echo.ik_messaging_campaign')(MailBundle.as_view()), name='mail_bundle'),
    url(r'^csv_upload/$', csv_uploader, name='csv_uploader'),
)
