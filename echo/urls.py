from django.conf.urls import url, patterns
from django.contrib.auth.decorators import permission_required

from echo.collect import confirm_bundle_payment
from echo.views import SMSCampaignView, SMSHistory, SMSBundle, MailCampaignList, ChangeMailCampaign, MailBundle, \
    csv_uploader, PopupList, ChangePopup, PushCampaignList, ChangePushCampaign, PushBundle

urlpatterns = patterns(
    '',
    url(r'^pushCampaignList/$', permission_required('echo.ik_manage_messaging')(PushCampaignList.as_view()), name='pushcampaign_list'),
    url(r'^pushCampaign/$', permission_required('echo.ik_manage_messaging')(ChangePushCampaign.as_view()), name='change_pushcampaign'),
    url(r'^pushCampaign/(?P<object_id>[-\w]+)/$', permission_required('echo.ik_manage_messaging')(ChangePushCampaign.as_view()), name='change_pushcampaign'),
    url(r'^mailCampaignList/$', permission_required('echo.ik_manage_messaging')(MailCampaignList.as_view()), name='mailcampaign_list'),
    url(r'^mailCampaign/$', permission_required('echo.ik_manage_messaging')(ChangeMailCampaign.as_view()), name='change_mailcampaign'),
    url(r'^mailCampaign/(?P<object_id>[-\w]+)/$', permission_required('echo.ik_manage_messaging')(ChangeMailCampaign.as_view()), name='change_mailcampaign'),
    url(r'^sms/$', permission_required('echo.ik_manage_messaging')(SMSCampaignView.as_view()), name='sms_campaign'),
    url(r'^smsHistory/$', permission_required('echo.ik_manage_messaging')(SMSHistory.as_view()), name='sms_history'),
    url(r'^pops-up/$', permission_required('echo.ik_manage_popup')(PopupList.as_view()), name='popup_list'),
    url(r'^pop-up/$', permission_required('echo.ik_manage_popup')(ChangePopup.as_view()), name='change_popup'),
    url(r'^pop-up/(?P<object_id>[-\w]+)/$', permission_required('echo.ik_manage_popup')(ChangePopup.as_view()), name='change_popup'),

    url(r'^pushBundles/$', permission_required('echo.ik_manage_messaging')(PushBundle.as_view()), name='push_bundle'),
    url(r'^mailBundles/$', permission_required('echo.ik_manage_messaging')(MailBundle.as_view()), name='mail_bundle'),
    url(r'^smsBundles/$', permission_required('echo.ik_manage_messaging')(SMSBundle.as_view()), name='sms_bundle'),
    url(r'^confirm_bundle_payment/(?P<tx_id>[-\w]+)/(?P<signature>[-\w]+)$', confirm_bundle_payment, name='confirm_bundle_payment'),

    url(r'^csv_upload/$', csv_uploader, name='csv_uploader'),
)
