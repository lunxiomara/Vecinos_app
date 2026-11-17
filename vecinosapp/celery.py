import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vecinosapp.settings')

app = Celery('vecinosapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
