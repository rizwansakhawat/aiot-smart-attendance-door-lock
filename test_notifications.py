"""Test notification delivery through Celery tasks."""

import os
import sys

import django
from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.conf import settings
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_attendance_project.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from attendance.models import Student
from attendance.services.notification_service import EmailNotificationService, TelegramNotificationService
from attendance.tasks import send_attendance_notification_task, send_daily_report_task


def wait_for_task(async_result, timeout_seconds):
    """Wait for a Celery task and print its final state/result."""
    try:
        output = async_result.get(timeout=timeout_seconds)
        print(f"   State: {async_result.state}")
        print(f"   Output: {output}")
        return True
    except CeleryTimeoutError:
        print(
            "   Timeout while waiting for task result. "
            "Worker may still be processing (for example, retries/network delays)."
        )
        print(f"   Current state: {async_result.state}")
        return False
    except Exception as exc:
        print(f"   Task failed: {exc}")
        print(f"   Current state: {async_result.state}")
        return False


print("\n" + "=" * 60)
print("   CELERY NOTIFICATION TEST")
print("=" * 60 + "\n")

print("Celery notifications enabled:", getattr(settings, 'CELERY_NOTIFICATIONS_ENABLED', False))
print("Celery broker:", getattr(settings, 'CELERY_BROKER_URL', 'N/A'))
print("Email enabled:", EmailNotificationService.is_enabled())
print("Telegram enabled:", TelegramNotificationService.is_enabled())

wait_mode = '--no-wait' not in sys.argv
timeout_seconds = int(os.getenv('CELERY_TEST_TIMEOUT', '20'))
telegram_attempts = int(getattr(settings, 'TELEGRAM_RETRY_ATTEMPTS', 3))
telegram_timeout = int(getattr(settings, 'TELEGRAM_REQUEST_TIMEOUT', 10))
telegram_retry_delay = float(getattr(settings, 'TELEGRAM_RETRY_DELAY_SECONDS', 1.0))
estimated_telegram_seconds = (telegram_attempts * telegram_timeout) + ((telegram_attempts - 1) * telegram_retry_delay)
print(f"Wait for task completion: {wait_mode} (timeout={timeout_seconds}s)")
print(f"Estimated Telegram worst-case time per send: ~{estimated_telegram_seconds:.1f}s")

student = Student.objects.filter(email__isnull=False).exclude(email='').first()

print("\n--- Test 1: Attendance Notification via Celery ---")
if student:
    attendance_task = send_attendance_notification_task.delay(student.id, timezone.now().isoformat())
    print(f"   Task ID: {attendance_task.id}")
    print(f"   Initial state: {attendance_task.state}")
    if wait_mode:
        wait_for_task(attendance_task, timeout_seconds)
else:
    print("   Skipped: no student with email found")

print("\n--- Test 2: Daily Report via Celery ---")
daily_task = send_daily_report_task.delay(timezone.now().date().isoformat())
print(f"   Task ID: {daily_task.id}")
print(f"   Initial state: {daily_task.state}")
if wait_mode:
    wait_for_task(daily_task, timeout_seconds)

print("\n" + "=" * 60)
print("   TEST COMPLETE")
print("=" * 60 + "\n")