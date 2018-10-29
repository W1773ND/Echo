from django.conf.urls import url, patterns
from django.contrib.auth.decorators import permission_required

from echo.views import SMSCampaign, SMSHistory, SMSBundle, MailCampaign, MailHistory, MailBundle

urlpatterns = patterns(
    '',
    url(r'^sms/$', permission_required('echo.ik_messaging_campaign')(SMSCampaign.as_view()), name='sms_campaign'),
    url(r'^sms_hist/$', permission_required('echo.ik_messaging_campaign')(SMSHistory.as_view()), name='sms_hist'),
    url(r'^sms_bundle/$', permission_required('echo.ik_messaging_campaign')(SMSBundle.as_view()), name='sms_bundle'),
    url(r'^mail/$', permission_required('echo.ik_messaging_campaign')(MailCampaign.as_view()), name='mail_campaign'),
    url(r'^mail_hist/$', permission_required('echo.ik_messaging_campaign')(MailHistory.as_view()), name='mail_hist'),
    url(r'^mail_bundle/$', permission_required('echo.ik_messaging_campaign')(MailBundle.as_view()), name='mail_bundle'),
)