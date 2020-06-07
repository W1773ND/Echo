# -*- coding: utf-8 -*-

from django.db import models
from django.template.defaultfilters import truncatechars
from django_mongodb_engine.contrib import MongoDBManager
from djangotoolbox.fields import ListField
from django.utils.translation import gettext_lazy as _

from ikwen.core.constants import PENDING, STARTED
from ikwen.core.models import Model, Service
from ikwen.accesscontrol.models import Member

PUSH = 'Push'
MAIL = 'Mail'
SMS = 'SMS'
TYPE_CHOICES = (
    (PUSH, 'Push'),
    (MAIL, 'Mail'),
    (SMS, 'SMS')
)
EN = 'en'
FR = 'fr'
LANG_CHOICES = (
    (EN, 'English'),
    (FR, u'Français'),
)
MESSAGING_CREDIT_REFILL = "MessagingCreditRefill"


class Campaign(Model):
    service = models.ForeignKey(Service, related_name='+')
    member = models.ForeignKey(Member, related_name='+')
    recipient_src = models.CharField(max_length=240, blank=True, null=True)
    recipient_profile = models.CharField(max_length=240, blank=True, null=True)
    profile_tag_list = ListField(blank=True, null=True)
    recipient_list = ListField(blank=True, null=True)
    recipient_label = models.CharField(max_length=240)
    recipient_label_raw = models.CharField(max_length=240)
    subject = models.CharField(max_length=240, blank=True, null=True)
    slug = models.SlugField(max_length=240, blank=True, null=True)
    total = models.IntegerField(default=0)
    progress = models.IntegerField(default=0)
    is_started = models.BooleanField(default=False)
    type = models.CharField(max_length=10, blank=True, null=True)

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


class PushCampaign(Campaign):
    UPLOAD_TO = 'push_campaigns'
    image = models.ImageField(upload_to=UPLOAD_TO, blank=True, null=True,
                              help_text=_("Should be at least 1350px width and landscape orientation"))
    content = models.TextField(blank=True, null=True)
    cta = models.CharField(max_length=40, blank=True, null=True)
    cta_url = models.URLField(max_length=250, blank=True, null=True)
    keep_running = models.BooleanField(default=False)

    def get_sample(self):
        """
        Gets the first Push of this campaign. Might be the only one in case on a single send
        """
        try:
            return self.pushobject_set.all()[0]
        except:
            pass


class MailCampaign(Campaign):
    UPLOAD_TO = 'mail_campaigns'
    pre_header = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to=UPLOAD_TO, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    items_fk_list = ListField(blank=True, null=True)
    cta = models.CharField(max_length=40, blank=True, null=True)
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


class SMSCampaign(Campaign):
    text = models.TextField(blank=True, null=True)
    page_count = models.IntegerField(default=0)

    def get_sample(self):
        """
        Gets the first SMS of this campaign. Might be the only one in case on a single send
        """
        try:
            return self.smsobject_set.all()[0]
        except:
            pass


class PushObject(Model):
    campaign = models.ForeignKey(PushCampaign, blank=True, null=True,
                                 related_name='+')
    sender = models.CharField(max_length=15)
    recipient = models.CharField(max_length=150, db_index=True)
    subject = models.CharField(max_length=150, db_index=True)
    is_sent = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.recipient, self.subject)


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


class SMSObject(Model):
    campaign = models.ForeignKey(SMSCampaign, blank=True, null=True)
    label = models.CharField(max_length=15)
    recipient = models.CharField(max_length=15, db_index=True)
    text = models.TextField()
    is_sent = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.label, self.text)


class PopUp(Model):
    UPLOAD_TO = 'popup/'
    lang = models.CharField(max_length=10, choices=LANG_CHOICES, default=EN, verbose_name="Language")
    name = models.CharField(max_length=150)
    catchy = models.CharField(max_length=250, blank=True, null=True)
    text = models.TextField(blank=True, null=True)
    cta_label = models.CharField(max_length=40, blank=True, null=True, verbose_name="Call-to-action")
    cta_url = models.URLField(max_length=250, blank=True, null=True)
    image = models.ImageField(blank=True, null=True, upload_to=UPLOAD_TO,
                              help_text=_("600 x 600px ; will appear on background"))
    is_active = models.BooleanField(default=False)
    order_of_appearance = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = "Pop-up"

    def __unicode__(self):
        return self.name + ' | ' + self.lang

    def get_obj_details(self):
        return self.catchy

    def get_image_url(self):
        if self.image:
            return self.image.url
        else:
            return None


class Balance(Model):
    service_id = models.CharField(max_length=24, unique=True)
    sms_count = models.IntegerField(default=0)
    mail_count = models.IntegerField(default=0)
    push_count = models.IntegerField(default=0)
    last_low_push_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                help_text=_("Last time the person was informed of low Push credit"))
    last_low_mail_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                help_text=_("Last time the person was informed of low Email credit"))
    last_low_sms_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                               help_text=_("Last time the person was informed of low SMS credit"))
    last_empty_push_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                  help_text=_("Last time the person was informed of empty Push credit"))
    last_empty_mail_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                  help_text=_("Last time the person was informed of empty Email credit"))
    last_empty_sms_notice = models.DateTimeField(blank=True, null=True, db_index=True,
                                                 help_text=_("Last time the person was informed of empty SMS credit"))


class Refill(Model):
    service = models.ForeignKey(Service, related_name='+')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.IntegerField()
    credit = models.IntegerField()
    status = models.CharField(max_length=15, default=STARTED)

    def __unicode__(self):
        return u'%s' % self.type


class Bundle(Model):
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    name = models.CharField(max_length=20)
    cost = models.IntegerField()
    credit = models.IntegerField()
    unit_cost = models.FloatField(blank=True, null=True)
    image = models.ImageField(upload_to='echo_bundles', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __unicode__(self):
        return u'%s %s' % (self.type, self.name)
