"""
═══════════════════════════════════════════════════════════════════
Notification Service - Email & Telegram
═══════════════════════════════════════════════════════════════════
"""

import os
import smtplib
import time
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from attendance.tasks import (
    send_attendance_notification_task,
    send_daily_report_task,
    send_registration_notification_task,
    send_unknown_person_alert_task,
)


# ═══════════════════════════════════════════════════════════════════
# EMAIL NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════

class EmailNotificationService:
    """Handle all email notifications"""
    
    @staticmethod
    def is_enabled():
        """Check if email notifications are enabled"""
        return bool(
            getattr(settings, 'EMAIL_NOTIFICATIONS', False) and
            getattr(settings, 'NOTIFICATIONS_ENABLED', False)
        )

    @staticmethod
    def _log_email_error(prefix, error):
        if isinstance(error, smtplib.SMTPAuthenticationError):
            print(
                f"   ❌ {prefix}: SMTP auth failed. "
                "Use Gmail App Password (16 chars), not account password."
            )
            return
        print(f"   ❌ {prefix}: {error}")
    
    @staticmethod
    def send_attendance_notification(student, timestamp=None):
        """Send email when attendance is marked"""
        if not EmailNotificationService.is_enabled():
            return False
        
        if not student.email:
            print(f"   ℹ️ No email for {student.name}")
            return False
        
        try:
            timestamp = timestamp or timezone.now()
            
            subject = f"✅ Attendance Marked - {timestamp.strftime('%d %b %Y')}"
            
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 500px; margin: 0 auto; background: #f8f9fa; padding: 30px; border-radius: 15px;">
                    <h2 style="color: #2ec4b6; margin-bottom: 20px;">✅ Attendance Confirmed</h2>
                    
                    <p>Hello <strong>{student.name}</strong>,</p>
                    
                    <p>Your attendance has been marked successfully.</p>
                    
                    <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <table style="width: 100%;">
                            <tr>
                                <td style="padding: 8px 0; color: #666;">📅 Date:</td>
                                <td style="padding: 8px 0;"><strong>{timestamp.strftime('%d %B %Y')}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">⏰ Time:</td>
                                <td style="padding: 8px 0;"><strong>{timestamp.strftime('%I:%M %p')}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">🆔 Roll Number:</td>
                                <td style="padding: 8px 0;"><strong>{student.roll_number}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">📍 Location:</td>
                                <td style="padding: 8px 0;"><strong>Main Entrance</strong></td>
                            </tr>
                        </table>
                    </div>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        This is an automated message from Smart Attendance System.<br>
                        Please do not reply to this email.
                    </p>
                </div>
            </body>
            </html>
            """
            
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
                html_message=html_message,
                fail_silently=False
            )
            
            print(f"   📧 Email sent to {student.email}")
            return True
            
        except Exception as e:
            EmailNotificationService._log_email_error('Email failed', e)
            return False
    
    @staticmethod
    def send_welcome_email(student, username, password):
        """Send welcome email with login credentials"""
        if not EmailNotificationService.is_enabled():
            return False
        
        if not student.email:
            return False
        
        try:
            subject = "🎉 Welcome to Smart Attendance System"
            
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 500px; margin: 0 auto; background: linear-gradient(135deg, #4361ee 0%, #3f37c9 100%); padding: 30px; border-radius: 15px; color: white;">
                    <h2 style="margin-bottom: 20px;">🎉 Welcome!</h2>
                    
                    <p>Hello <strong>{student.name}</strong>,</p>
                    
                    <p>Your account has been created in the Smart Attendance System.</p>
                </div>
                
                <div style="max-width: 500px; margin: 20px auto; background: #f8f9fa; padding: 30px; border-radius: 15px;">
                    <h3 style="color: #333;">🔐 Your Login Credentials</h3>
                    
                    <div style="background: white; padding: 20px; border-radius: 10px; margin: 15px 0;">
                        <table style="width: 100%;">
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Username:</td>
                                <td style="padding: 10px 0;"><code style="background: #e9ecef; padding: 5px 10px; border-radius: 5px;">{username}</code></td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Password:</td>
                                <td style="padding: 10px 0;"><code style="background: #e9ecef; padding: 5px 10px; border-radius: 5px;">{password}</code></td>
                            </tr>
                        </table>
                    </div>
                    
                    <p style="color: #dc3545; font-size: 14px;">
                        ⚠️ Please keep your credentials safe and do not share with anyone.
                    </p>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        Smart Attendance System<br>
                        The Islamia University of Bahawalpur
                    </p>
                </div>
            </body>
            </html>
            """
            
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
                html_message=html_message,
                fail_silently=False
            )
            
            print(f"   📧 Welcome email sent to {student.email}")
            return True
            
        except Exception as e:
            EmailNotificationService._log_email_error('Welcome email failed', e)
            return False
    
    @staticmethod
    def send_unknown_person_alert(image_path=None):
        """Send alert to admin about unknown person"""
        if not EmailNotificationService.is_enabled():
            return False
        
        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        if not admin_email:
            return False
        
        try:
            timestamp = timezone.now()
            
            subject = "⚠️ Unknown Person Detected - Smart Attendance"
            
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 500px; margin: 0 auto; background: #fff3cd; padding: 30px; border-radius: 15px; border-left: 5px solid #ffc107;">
                    <h2 style="color: #856404; margin-bottom: 20px;">⚠️ Security Alert</h2>
                    
                    <p>An <strong>unknown person</strong> was detected by the attendance system.</p>
                    
                    <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <table style="width: 100%;">
                            <tr>
                                <td style="padding: 8px 0; color: #666;">📅 Date:</td>
                                <td style="padding: 8px 0;"><strong>{timestamp.strftime('%d %B %Y')}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">⏰ Time:</td>
                                <td style="padding: 8px 0;"><strong>{timestamp.strftime('%I:%M:%S %p')}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">📍 Location:</td>
                                <td style="padding: 8px 0;"><strong>Main Entrance</strong></td>
                            </tr>
                        </table>
                    </div>
                    
                    <p>Please check the system logs for more details.</p>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        Smart Attendance System - Security Alert
                    </p>
                </div>
            </body>
            </html>
            """
            
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin_email],
                html_message=html_message,
                fail_silently=False
            )
            
            print(f"   📧 Alert sent to admin")
            return True
            
        except Exception as e:
            EmailNotificationService._log_email_error('Alert email failed', e)
            return False
    
    @staticmethod
    def send_daily_report(date=None):
        """Send daily attendance report to admin"""
        if not EmailNotificationService.is_enabled():
            return False
        
        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        if not admin_email:
            return False
        
        try:
            from attendance.models import Student, Attendance
            
            date = date or timezone.now().date()
            
            # Get stats
            total_students = Student.objects.filter(is_active=True).count()
            present_today = Attendance.objects.filter(
                timestamp__date=date,
                entry_type='success'
            ).values('student').distinct().count()
            absent_today = total_students - present_today
            
            # Get list of present students
            present_list = Attendance.objects.filter(
                timestamp__date=date,
                entry_type='success'
            ).select_related('student').values_list('student__name', flat=True).distinct()
            
            subject = f"📊 Daily Attendance Report - {date.strftime('%d %b %Y')}"
            
            present_names = "<br>".join([f"✅ {name}" for name in present_list])
            if not present_names:
                present_names = "No attendance recorded"
            
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: #f8f9fa; padding: 30px; border-radius: 15px;">
                    <h2 style="color: #4361ee; margin-bottom: 20px;">📊 Daily Attendance Report</h2>
                    <p style="color: #666;">{date.strftime('%A, %d %B %Y')}</p>
                    
                    <div style="display: flex; gap: 15px; margin: 20px 0;">
                        <div style="flex: 1; background: #d4edda; padding: 20px; border-radius: 10px; text-align: center;">
                            <div style="font-size: 2rem; font-weight: bold; color: #155724;">{present_today}</div>
                            <div style="color: #155724;">Present</div>
                        </div>
                        <div style="flex: 1; background: #f8d7da; padding: 20px; border-radius: 10px; text-align: center;">
                            <div style="font-size: 2rem; font-weight: bold; color: #721c24;">{absent_today}</div>
                            <div style="color: #721c24;">Absent</div>
                        </div>
                        <div style="flex: 1; background: #cce5ff; padding: 20px; border-radius: 10px; text-align: center;">
                            <div style="font-size: 2rem; font-weight: bold; color: #004085;">{total_students}</div>
                            <div style="color: #004085;">Total</div>
                        </div>
                    </div>
                    
                    <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h4 style="color: #333; margin-bottom: 15px;">Present Students:</h4>
                        <div style="color: #666; line-height: 1.8;">
                            {present_names}
                        </div>
                    </div>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        Smart Attendance System - Automated Report
                    </p>
                </div>
            </body>
            </html>
            """
            
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin_email],
                html_message=html_message,
                fail_silently=False
            )
            
            print(f"   📧 Daily report sent to admin")
            return True
            
        except Exception as e:
            EmailNotificationService._log_email_error('Daily report failed', e)
            return False


# ═══════════════════════════════════════════════════════════════════
# TELEGRAM NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════

class TelegramNotificationService:
    """Handle all Telegram notifications"""

    _disabled_until = None
    
    @staticmethod
    def is_enabled():
        """Check if Telegram notifications are enabled"""
        return bool(
            getattr(settings, 'TELEGRAM_NOTIFICATIONS', False) and
            getattr(settings, 'NOTIFICATIONS_ENABLED', False) and
            getattr(settings, 'TELEGRAM_BOT_TOKEN', None) and
            getattr(settings, 'TELEGRAM_CHAT_ID', None)
        )

    @staticmethod
    def _is_in_cooldown():
        if TelegramNotificationService._disabled_until is None:
            return False
        return timezone.now() < TelegramNotificationService._disabled_until

    @staticmethod
    def _start_cooldown(reason):
        cooldown_seconds = int(getattr(settings, 'TELEGRAM_FAIL_COOLDOWN_SECONDS', 300))
        TelegramNotificationService._disabled_until = timezone.now() + timedelta(seconds=cooldown_seconds)
        print(
            "   ⚠️ Telegram temporarily disabled for "
            f"{cooldown_seconds}s due to repeated failures: {reason}"
        )

    @staticmethod
    def _request_with_retry(url, *, data=None, files=None):
        timeout = int(getattr(settings, 'TELEGRAM_REQUEST_TIMEOUT', 10))
        attempts = int(getattr(settings, 'TELEGRAM_RETRY_ATTEMPTS', 3))
        retry_delay = float(getattr(settings, 'TELEGRAM_RETRY_DELAY_SECONDS', 1.0))

        for attempt in range(1, attempts + 1):
            try:
                return requests.post(url, data=data, files=files, timeout=timeout)
            except requests.exceptions.RequestException as exc:
                if attempt == attempts:
                    raise exc
                print(f"   ⚠️ Telegram attempt {attempt}/{attempts} failed: {exc}")
                time.sleep(retry_delay)
    
    @staticmethod
    def send_message(message, parse_mode='HTML'):
        """Send a text message to Telegram"""
        if not TelegramNotificationService.is_enabled():
            return False

        if TelegramNotificationService._is_in_cooldown():
            print("   ⚠️ Telegram skipped (cooldown active)")
            return False
        
        try:
            token = settings.TELEGRAM_BOT_TOKEN
            chat_id = settings.TELEGRAM_CHAT_ID
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = TelegramNotificationService._request_with_retry(url, data=data)
            
            if response.status_code == 200:
                TelegramNotificationService._disabled_until = None
                print(f"   📱 Telegram message sent")
                return True
            else:
                print(f"   ❌ Telegram failed: {response.text}")
                TelegramNotificationService._start_cooldown(response.text)
                return False
                
        except Exception as e:
            print(f"   ❌ Telegram error: {e}")
            TelegramNotificationService._start_cooldown(e)
            return False
    
    @staticmethod
    def send_photo(photo_path, caption=""):
        """Send a photo to Telegram"""
        if not TelegramNotificationService.is_enabled():
            return False

        if TelegramNotificationService._is_in_cooldown():
            print("   ⚠️ Telegram photo skipped (cooldown active)")
            return False
        
        if not os.path.exists(photo_path):
            return False
        
        try:
            token = settings.TELEGRAM_BOT_TOKEN
            chat_id = settings.TELEGRAM_CHAT_ID
            
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            
            with open(photo_path, 'rb') as photo:
                data = {
                    'chat_id': chat_id,
                    'caption': caption,
                    'parse_mode': 'HTML'
                }
                files = {'photo': photo}
                
                response = TelegramNotificationService._request_with_retry(url, data=data, files=files)
            
            if response.status_code == 200:
                TelegramNotificationService._disabled_until = None
                print(f"   📱 Telegram photo sent")
                return True
            else:
                print(f"   ❌ Telegram photo failed: {response.text}")
                TelegramNotificationService._start_cooldown(response.text)
                return False
                
        except Exception as e:
            print(f"   ❌ Telegram photo error: {e}")
            TelegramNotificationService._start_cooldown(e)
            return False
    
    @staticmethod
    def send_attendance_notification(student, timestamp=None):
        """Send Telegram notification when attendance is marked"""
        timestamp = timestamp or timezone.now()
        
        message = f"""
✅ <b>Attendance Marked</b>

👤 <b>Name:</b> {student.name}
🆔 <b>Roll:</b> {student.roll_number}
📅 <b>Date:</b> {timestamp.strftime('%d %b %Y')}
⏰ <b>Time:</b> {timestamp.strftime('%I:%M %p')}
📍 <b>Location:</b> Main Entrance

#attendance #present
"""
        return TelegramNotificationService.send_message(message)
    
    @staticmethod
    def send_unknown_person_alert(photo_path=None):
        """Send alert about unknown person with photo"""
        timestamp = timezone.now()
        
        message = f"""
⚠️ <b>SECURITY ALERT</b>

Unknown person detected!

📅 <b>Date:</b> {timestamp.strftime('%d %b %Y')}
⏰ <b>Time:</b> {timestamp.strftime('%I:%M:%S %p')}
📍 <b>Location:</b> Main Entrance

Please check immediately.

#security #alert #unknown
"""
        
        if photo_path and os.path.exists(photo_path):
            return TelegramNotificationService.send_photo(photo_path, message)
        else:
            return TelegramNotificationService.send_message(message)
    
    @staticmethod
    def send_daily_summary(date=None):
        """Send daily attendance summary"""
        try:
            from attendance.models import Student, Attendance
            
            today = date or timezone.now().date()
            if isinstance(today, str):
                from django.utils.dateparse import parse_date

                parsed_date = parse_date(today)
                today = parsed_date or timezone.now().date()
            
            total = Student.objects.filter(is_active=True).count()
            present = Attendance.objects.filter(
                timestamp__date=today,
                entry_type='success'
            ).values('student').distinct().count()
            absent = total - present
            
            percentage = (present / total * 100) if total > 0 else 0
            
            message = f"""
📊 <b>Daily Attendance Summary</b>

📅 <b>Date:</b> {today.strftime('%d %b %Y')}

✅ <b>Present:</b> {present}
❌ <b>Absent:</b> {absent}
👥 <b>Total:</b> {total}
📈 <b>Percentage:</b> {percentage:.1f}%

#daily #report #attendance
"""
            return TelegramNotificationService.send_message(message)
            
        except Exception as e:
            print(f"   ❌ Daily summary error: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════
# UNIFIED NOTIFICATION SERVICE
# ═══════════════════════════════════════════════════════════════════

class NotificationService:
    """Unified notification service - sends to all enabled channels"""

    @staticmethod
    def _use_celery():
        return getattr(settings, 'CELERY_NOTIFICATIONS_ENABLED', False)

    @staticmethod
    def _queue_task(task, *args):
        try:
            task.delay(*args)
            return True
        except Exception as e:
            print(f"   ⚠️ Celery queue failed: {e}")
            return False
    
    @staticmethod
    def notify_attendance(student, timestamp=None):
        """Notify about attendance via all enabled channels"""
        results = {
            'email': False,
            'telegram': False
        }

        if NotificationService._use_celery() and (EmailNotificationService.is_enabled() or TelegramNotificationService.is_enabled()):
            if NotificationService._queue_task(send_attendance_notification_task, student.id, (timestamp or timezone.now()).isoformat()):
                results['email'] = True
                results['telegram'] = True
                return results
        
        # Email
        if EmailNotificationService.is_enabled():
            results['email'] = EmailNotificationService.send_attendance_notification(student, timestamp)
        
        # Telegram
        if TelegramNotificationService.is_enabled():
            results['telegram'] = TelegramNotificationService.send_attendance_notification(student, timestamp)
        
        return results
    
    @staticmethod
    def notify_unknown_person(photo_path=None):
        """Notify about unknown person via all enabled channels"""
        results = {
            'email': False,
            'telegram': False
        }

        if NotificationService._use_celery() and (EmailNotificationService.is_enabled() or TelegramNotificationService.is_enabled()):
            if NotificationService._queue_task(send_unknown_person_alert_task, photo_path):
                results['email'] = True
                results['telegram'] = True
                return results
        
        # Email
        if EmailNotificationService.is_enabled():
            results['email'] = EmailNotificationService.send_unknown_person_alert(photo_path)
        
        # Telegram
        if TelegramNotificationService.is_enabled():
            results['telegram'] = TelegramNotificationService.send_unknown_person_alert(photo_path)
        
        return results
    
    @staticmethod
    def notify_registration(student, username, password):
        """Notify about new registration"""
        results = {
            'email': False,
            'telegram': False
        }

        if NotificationService._use_celery() and (EmailNotificationService.is_enabled() or TelegramNotificationService.is_enabled()):
            if NotificationService._queue_task(send_registration_notification_task, student.id, username, password):
                results['email'] = True
                results['telegram'] = True
                return results
        
        # Email welcome
        if EmailNotificationService.is_enabled():
            results['email'] = EmailNotificationService.send_welcome_email(student, username, password)
        
        # Telegram notification
        if TelegramNotificationService.is_enabled():
            message = f"""
🎉 <b>New Student Registered</b>

👤 <b>Name:</b> {student.name}
🆔 <b>Roll:</b> {student.roll_number}
🏢 <b>Dept:</b> {student.department or 'N/A'}

#registration #new
"""
            results['telegram'] = TelegramNotificationService.send_message(message)
        
        return results
    
    @staticmethod
    def send_daily_report():
        """Send daily report via all channels"""
        results = {
            'email': False,
            'telegram': False
        }

        if NotificationService._use_celery() and (EmailNotificationService.is_enabled() or TelegramNotificationService.is_enabled()):
            if NotificationService._queue_task(send_daily_report_task, timezone.now().date().isoformat()):
                results['email'] = True
                results['telegram'] = True
                return results
        
        if EmailNotificationService.is_enabled():
            results['email'] = EmailNotificationService.send_daily_report()
        
        if TelegramNotificationService.is_enabled():
            results['telegram'] = TelegramNotificationService.send_daily_summary()
        
        return results