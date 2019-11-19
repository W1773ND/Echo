from django.conf.urls import url, patterns
from django.contrib.auth.decorators import permission_required

from echo.views import SMSCampaignView, SMSHistory, SMSBundle, MailCampaignList, ChangeMailCampaign, MailBundle, csv_uploader

urlpatterns = patterns(
    '',
    url(r'^sms/$', permission_required('echo.ik_manage_messaging')(SMSCampaignView.as_view()), name='sms_campaign'),
    url(r'^smsHistory/$', permission_required('echo.ik_manage_messaging')(SMSHistory.as_view()), name='sms_history'),
    url(r'^smsBundles/$', permission_required('echo.ik_manage_messaging')(SMSBundle.as_view()), name='sms_bundle'),
    url(r'^mailCampaignList/$', permission_required('echo.ik_manage_messaging')(MailCampaignList.as_view()), name='mailcampaign_list'),
    url(r'^mailCampaign/$', permission_required('echo.ik_manage_messaging')(ChangeMailCampaign.as_view()), name='change_mailcampaign'),
    url(r'^mailCampaign/(?P<object_id>[-\w]+)/$', permission_required('echo.ik_manage_messaging')(ChangeMailCampaign.as_view()), name='change_mailcampaign'),
    url(r'^mailBundles/$', permission_required('echo.ik_manage_messaging')(MailBundle.as_view()), name='mail_bundle'),
    url(r'^csv_upload/$', csv_uploader, name='csv_uploader'),
)
