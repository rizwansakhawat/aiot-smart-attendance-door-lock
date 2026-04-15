"""Celery tasks for notification delivery."""

from datetime import datetime, time

from celery import shared_task
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


def _load_timestamp(value):
    if not value:
        return timezone.now()

    parsed_datetime = parse_datetime(value)
    if parsed_datetime is not None:
        if timezone.is_naive(parsed_datetime):
            parsed_datetime = timezone.make_aware(parsed_datetime, timezone.get_current_timezone())
        return parsed_datetime

    parsed_date = parse_date(value)
    if parsed_date is not None:
        return timezone.make_aware(datetime.combine(parsed_date, time.min), timezone.get_current_timezone())

    return timezone.now()


@shared_task(name='attendance.send_attendance_notification')
def send_attendance_notification_task(student_id, timestamp_iso=None):
    from attendance.models import Student
    from attendance.services.notification_service import (
        EmailNotificationService,
        TelegramNotificationService,
    )

    student = Student.objects.filter(pk=student_id).first()
    if not student:
        return {'email': False, 'telegram': False}

    timestamp = _load_timestamp(timestamp_iso)
    return {
        'email': EmailNotificationService.send_attendance_notification(student, timestamp),
        'telegram': TelegramNotificationService.send_attendance_notification(student, timestamp),
    }


@shared_task(name='attendance.send_unknown_person_alert')
def send_unknown_person_alert_task(photo_path=None):
    from attendance.services.notification_service import (
        EmailNotificationService,
        TelegramNotificationService,
    )

    return {
        'email': EmailNotificationService.send_unknown_person_alert(photo_path),
        'telegram': TelegramNotificationService.send_unknown_person_alert(photo_path),
    }


@shared_task(name='attendance.send_registration_notification')
def send_registration_notification_task(student_id, username, password):
    from attendance.models import Student
    from attendance.services.notification_service import (
        EmailNotificationService,
        TelegramNotificationService,
    )

    student = Student.objects.filter(pk=student_id).first()
    if not student:
        return {'email': False, 'telegram': False}

    return {
        'email': EmailNotificationService.send_welcome_email(student, username, password),
        'telegram': TelegramNotificationService.send_message(
            f"""
🎉 <b>New Student Registered</b>

👤 <b>Name:</b> {student.name}
🆔 <b>Roll:</b> {student.roll_number}
🏢 <b>Dept:</b> {student.department or 'N/A'}

#registration #new
"""
        ),
    }


@shared_task(name='attendance.send_daily_report')
def send_daily_report_task(date_iso=None):
    from attendance.models import Attendance, Student
    from attendance.services.notification_service import (
        EmailNotificationService,
        TelegramNotificationService,
    )

    report_date = parse_date(date_iso) if date_iso else timezone.now().date()
    if report_date is None:
        report_date = timezone.now().date()

    total_students = Student.objects.filter(is_active=True).count()
    present_today = Attendance.objects.filter(
        timestamp__date=report_date,
        entry_type='success'
    ).values('student').distinct().count()
    absent_today = total_students - present_today

    present_list = Attendance.objects.filter(
        timestamp__date=report_date,
        entry_type='success'
    ).select_related('student').values_list('student__name', flat=True).distinct()

    present_names = '<br>'.join([f'✅ {name}' for name in present_list])
    if not present_names:
        present_names = 'No attendance recorded'

    email_result = EmailNotificationService.send_daily_report(report_date)
    telegram_result = TelegramNotificationService.send_daily_summary(report_date)

    return {
        'email': email_result,
        'telegram': telegram_result,
        'date': report_date.isoformat(),
        'present': present_today,
        'absent': absent_today,
        'total': total_students,
        'students': present_names,
    }