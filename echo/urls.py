from django.conf.urls import url, patterns
from django.contrib.auth.decorators import permission_required

from echo.views import SMSCampaign, SMSHistory, SMSBundle, MailCampaign, MailHistory, MailBundle, csv_uploader

urlpatterns = patterns(
    '',
    url(r'^sms/$', permission_required('echo.ik_messaging_campaign')(SMSCampaign.as_view()), name='sms_campaign'),
    url(r'^smsHistory/$', permission_required('echo.ik_messaging_campaign')(SMSHistory.as_view()), name='sms_history'),
    url(r'^smsBundles/$', permission_required('echo.ik_messaging_campaign')(SMSBundle.as_view()), name='sms_bundle'),
    url(r'^mail/$', permission_required('echo.ik_messaging_campaign')(MailCampaign.as_view()), name='mail_campaign'),
    url(r'^mailHistory/$', permission_required('echo.ik_messaging_campaign')(MailHistory.as_view()), name='mail_hist'),
    url(r'^mailBundles/$', permission_required('echo.ik_messaging_campaign')(MailBundle.as_view()), name='mail_bundle'),
    url(r'^csv_upload/$', csv_uploader, name='csv_uploader'),
)
