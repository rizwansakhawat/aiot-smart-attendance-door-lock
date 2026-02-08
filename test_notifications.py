"""Test notification services"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_attendance_project.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from attendance.services.notification_service import (
    EmailNotificationService,
    TelegramNotificationService,
    NotificationService
)
from attendance.models import Student

print("\n" + "=" * 50)
print("   NOTIFICATION TEST")
print("=" * 50 + "\n")

# Check status
print("📧 Email Enabled:", EmailNotificationService.is_enabled())
print("📱 Telegram Enabled:", TelegramNotificationService.is_enabled())

# Test Telegram
print("\n--- Testing Telegram ---")
if TelegramNotificationService.is_enabled():
    result = TelegramNotificationService.send_message("🧪 Test message from Smart Attendance System!")
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
else:
    print("   ⚠️ Telegram not configured")

# Test Email
print("\n--- Testing Email ---")
if EmailNotificationService.is_enabled():
    # Get a student
    student = Student.objects.first()
    if student and student.email:
        result = EmailNotificationService.send_attendance_notification(student)
        print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    else:
        print("   ⚠️ No student with email found")
else:
    print("   ⚠️ Email not configured")

# Test Daily Report
print("\n--- Testing Daily Summary ---")
if TelegramNotificationService.is_enabled():
    result = TelegramNotificationService.send_daily_summary()
    print(f"   Telegram: {'✅ Success' if result else '❌ Failed'}")

print("\n" + "=" * 50)
print("   TEST COMPLETE")
print("=" * 50 + "\n")