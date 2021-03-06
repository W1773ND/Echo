# -*- coding: utf-8 -*-

from django.conf import settings
from django.contrib import admin
from echo.models import Bundle


class PushCampaignAdmin(admin.ModelAdmin):
    fields = ('subject', 'content', 'cta_url')


class MailCampaignAdmin(admin.ModelAdmin):
    fields = ('subject', 'pre_header', 'content', 'cta', 'cta_url')


class PopUpAdmin(admin.ModelAdmin):
    fields = ('name', 'catchy', 'text', 'cta_label', 'cta_url', 'lang', 'is_active')


if getattr(settings, 'IS_IKWEN', False):
    admin.site.register(Bundle)
