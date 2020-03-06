"""
WSGI config for Echo project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os
import sys

path = '/home/w177/MEGAsync/PycharmProjects/Echo/'
if path not in sys.path:
    sys.path.append(path)

from conf import monitor
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")

application = get_wsgi_application()

monitor.start(interval=1.0)
monitor.track(os.path.join(os.path.dirname(__file__)))
