# -*- coding: utf-8 -*-

from django.conf import settings
from django.contrib import admin
from echo.models import Bundle


class MailCampaignAdmin(admin.ModelAdmin):
    fields = ('subject', 'pre_header', 'content', 'cta', 'cta_url')


if getattr(settings, 'IS_IKWEN', False):
    admin.site.register(Bundle)
