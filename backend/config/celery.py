"""إعداد Celery — مهام خلفية (مسير الرواتب، تصدير الحضور)."""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('hr')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
