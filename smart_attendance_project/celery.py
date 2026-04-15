"""Celery configuration for Smart Attendance Project."""

import os

from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_attendance_project.settings')

app = Celery('smart_attendance_project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()