from django.conf.urls import url, patterns
from django.contrib.auth.decorators import permission_required

from echo.views import SMSCampaign, SMSHistory, MailCampaign, MailHistory, SMSBundle

urlpatterns = patterns(
    '',
    url(r'^sms/$', permission_required('echo.ik_messaging_campaign')(SMSCampaign.as_view()), name='sms_campaign'),
    url(r'^mail/$', permission_required('echo.ik_messaging_campaign')(MailCampaign.as_view()), name='mail_campaign'),
    url(r'^sms_history/$', permission_required('echo.ik_messaging_campaign')(SMSHistory.as_view()), name='sms_history'),
    url(r'^sms_bundle/$', permission_required('echo.ik_messaging_campaign')(SMSBundle.as_view()), name='sms_bundle'),
)
