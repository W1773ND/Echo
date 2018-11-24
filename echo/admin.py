# -*- coding: utf-8 -*-

from django.conf import settings
from django.contrib import admin
from echo.models import Bundle

if getattr(settings, 'IS_IKWEN', False):
    admin.site.register(Bundle)
