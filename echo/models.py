# -*- coding: utf-8 -*-
import os

from django.db import models
from django_mongodb_engine.contrib import MongoDBManager
from djangotoolbox.fields import ListField
from ikwen.core.models import Model, Service
from ikwen.core.utils import get_service_instance
from ikwen.accesscontrol.models import Member

MAIL = 'Mail'
SMS = 'SMS'
TYPE_CHOICES = (
    (MAIL,  'Mail'),
    (SMS, 'SMS')
)


# class CSVFile(Model):
#     filename = models.CharField(max_length=200)
#     file = models.FileField(upload_to='Contacts files')
#     uploaded_at = models.DateField(auto_now_add=True)


class Campaign(Model):
    service = models.ForeignKey(Service, default=get_service_instance)
    member = models.ForeignKey(Member)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    recipient_list = ListField()
    text = models.TextField()
    page_count = models.IntegerField(default=0)
    subject = models.CharField(max_length=200)
    slug = models.SlugField(max_length=240)
    total = models.IntegerField(default=0)
    progress = models.IntegerField(default=0)

    objects = MongoDBManager()

    def __unicode__(self):
        return u'%s %s' % (self.type, self.subject)


class SMS(Model):
    campaign = models.ForeignKey(Campaign)
    label = models.CharField(max_length=15)
    recipient = models.CharField(max_length=15, db_index=True)
    text = models.TextField()
    is_sent = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.label, self.text)


class Balance(Model):
    service_id = models.CharField(max_length=24, unique=True)
    sms_count = models.IntegerField(default=0)
    mail_count = models.IntegerField(default=0)


class Refill(Model):
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.IntegerField()
    credit = models.IntegerField()

    def __unicode__(self):
        return u'%s' % self.type


class Bundle(Model):
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    name = models.CharField(max_length=20)
    cost = models.IntegerField()
    credit = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.type, self.name)


