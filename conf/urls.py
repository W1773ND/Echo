from django.conf.urls import patterns, include, url

from django.contrib import admin

from ikwen.core.views import DefaultHome

admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^$', DefaultHome.as_view(), name='home'),
    url(r'^laakam/', include(admin.site.urls)),
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^echo/', include('echo.urls', namespace='echo')),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^coupon_detail/', include('ikwen.rewarding.urls', namespace='rewarding')),
    # url(r'^cashout/', include('ikwen.cashout.urls', namespace='cashout')),
    # url(r'^retail/', include('ikwen.partnership.urls', namespace='partnership')),
    url(r'^theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^kakocase/', include('ikwen_kakocase.kakocase.urls', namespace='kakocase')),
    # url(r'^shavida/', include('ikwen_shavida.shavida.urls', namespace='shavida')),
    url(r'^webnode/', include('ikwen_webnode.webnode.urls', namespace='webnode')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),
    url(r'^kako/', include('ikwen_kakocase.kako.urls', namespace='kako')),
    url(r'^revival/', include('ikwen.revival.urls', namespace='revival')),
    # url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
)
