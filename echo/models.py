# -*- coding: utf-8 -*-

from django.db import models
from django.template.defaultfilters import truncatechars
from django_mongodb_engine.contrib import MongoDBManager
from djangotoolbox.fields import ListField
from ikwen.core.constants import PENDING
from ikwen.core.models import Model, Service
from ikwen.accesscontrol.models import Member

MAIL = 'Mail'
SMS = 'SMS'
TYPE_CHOICES = (
    (MAIL, 'Mail'),
    (SMS, 'SMS')
)


class Campaign(Model):
    service = models.ForeignKey(Service, related_name='+')
    member = models.ForeignKey(Member, related_name='+')
    recipient_list = ListField()
    recipient_label = models.CharField(max_length=200, blank=True, null=True)
    subject = models.CharField(max_length=200, blank=True, null=True)
    slug = models.SlugField(max_length=240)
    total = models.IntegerField(default=0)
    progress = models.IntegerField(default=0)
    is_started = models.BooleanField(default=False)

    objects = MongoDBManager()

    class Meta:
        abstract = True

    def to_dict(self):
        var = super(Campaign, self).to_dict()
        recipient_list = ', '.join(self.recipient_list[:5])
        var['recipient_list'] = truncatechars(recipient_list, 30)
        return var

    def __unicode__(self):
        return self.subject


class SMSCampaign(Campaign):
    text = models.TextField()
    page_count = models.IntegerField(default=0)

    def get_sample(self):
        """
        Gets the first SMS of this campaign. Might be the only one in case on a single send
        """
        try:
            return self.smsobject_set.all()[0]
        except:
            pass


class MailCampaign(Campaign):
    UPLOAD_TO = 'mail_campaigns'

    pre_header = models.TextField()
    image = models.ImageField(upload_to=UPLOAD_TO)
    content = models.TextField()
    items_fk_list = ListField()
    cta = models.CharField(max_length=15, blank=True, null=True)
    cta_url = models.URLField(max_length=250, blank=True, null=True)
    keep_running = models.BooleanField(default=False)

    def get_sample(self):
        """
        Gets the first Mail of this campaign. Might be the only one in case on a single send
        """
        try:
            return self.emailobject_set.all()[0]
        except:
            pass

    # def get_obj_details(self):


class SMSObject(Model):
    campaign = models.ForeignKey(SMSCampaign, blank=True, null=True)
    label = models.CharField(max_length=15)
    recipient = models.CharField(max_length=15, db_index=True)
    text = models.TextField()
    is_sent = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.label, self.text)


class EmailObject(Model):
    campaign = models.ForeignKey(MailCampaign, blank=True, null=True,
                                 related_name='+')
    sender = models.CharField(max_length=15)
    recipient = models.CharField(max_length=150, db_index=True)
    subject = models.CharField(max_length=150, db_index=True)
    pre_header = models.CharField(max_length=150, db_index=True)
    is_sent = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.recipient, self.subject)


class Balance(Model):
    service_id = models.CharField(max_length=24, unique=True)
    sms_count = models.IntegerField(default=0)
    mail_count = models.IntegerField(default=0)
    last_low_sms_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                               help_text="Last time the person was informed of low SMS credit")
    last_low_mail_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                help_text="Last time the person was informed of low Email credit")
    last_empty_sms_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                 help_text="Last time the person was informed of empty SMS credit")
    last_empty_mail_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                  help_text="Last time the person was informed of empty Email credit")


class Refill(Model):
    service = models.ForeignKey(Service, related_name='+')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.IntegerField()
    credit = models.IntegerField()
    status = models.CharField(max_length=15, default=PENDING)

    def __unicode__(self):
        return u'%s' % self.type


class Bundle(Model):
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    name = models.CharField(max_length=20)
    cost = models.IntegerField()
    credit = models.IntegerField()
    image = models.ImageField(upload_to='echo_bundles', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.type, self.name)
