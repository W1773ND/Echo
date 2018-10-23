"""
WSGI config for Echo project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os, sys

sys.path.append('/home/w177/PycharmProjects/Echo/')

from conf import monitor
from django.core.wsgi import get_wsgi_application

monitor.start(interval=1.0)
monitor.track(os.path.join(os.path.dirname(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")

application = get_wsgi_application()
