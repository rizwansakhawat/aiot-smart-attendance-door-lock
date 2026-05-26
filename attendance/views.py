"""
Views for Smart Attendance System
=================================
Handles web pages and API endpoints with User Authentication
"""

import json
import base64
import cv2
import numpy as np
import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from .models import Student, Attendance, SystemLog, Department, NotificationState, Section
from .services.face_recognition_service import (
    get_face_recognition_service,
)

# Camera Index
CAMERA_INDEX = 0
# Notification Service
try:
    from attendance.services.notification_service import NotificationService
    NOTIFICATIONS_AVAILABLE = True
except:
    NOTIFICATIONS_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def is_admin(user):
    """Check if user is admin/staff"""
    return user.is_staff or user.is_superuser


def get_student_for_user(user):
    """Get student profile for logged-in user"""
    try:
        return Student.objects.get(user=user)
    except Student.DoesNotExist:
        return None


def _get_user_alert_queryset(user):
    """Alerts visible to a user for notification modal."""
    alerts_qs = SystemLog.objects.filter(log_type__in=['warning', 'error'])
    if user.is_staff or user.is_superuser:
        return alerts_qs

    student_profile = getattr(user, 'student_profile', None)
    alert_terms = [user.username]
    if student_profile and student_profile.name:
        alert_terms.append(student_profile.name)

    alert_filter = Q()
    for term in alert_terms:
        if term:
            alert_filter |= Q(message__icontains=term)

    return alerts_qs.filter(alert_filter)


def _can_access_notification(user, notification_type, object_id):
    """Ensure users can only mutate notification states they are allowed to see."""
    if notification_type == 'alert':
        return _get_user_alert_queryset(user).filter(pk=object_id).exists()

    if notification_type == 'entry':
        attendance_qs = Attendance.objects.all() if is_admin(user) else Attendance.objects.filter(student__user=user)
        return attendance_qs.filter(pk=object_id).exists()

    return False


def _parse_notification_key(raw_key):
    """Parse `alert-123` / `entry-456` style key."""
    if not isinstance(raw_key, str) or '-' not in raw_key:
        return None, None

    notification_type, object_id_str = raw_key.split('-', 1)
    if notification_type not in {'alert', 'entry'}:
        return None, None

    try:
        object_id = int(object_id_str)
    except (TypeError, ValueError):
        return None, None

    if object_id <= 0:
        return None, None

    return notification_type, object_id


# ═══════════════════════════════════════════════════════════════════
# AUTHENTICATION VIEWS
# ═══════════════════════════════════════════════════════════════════

def login_view(request):
    """
    Login page for all users
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        if not username or not password:
            messages.error(request, 'Please enter both username and password')
            return render(request, 'attendance/login.html')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_active:
                login(request, user)
                
                # Log successful login
                SystemLog.objects.create(
                    log_type='success',
                    message=f"User '{username}' logged in successfully"
                )
                
                messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                
                # Redirect based on user type
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Your account is disabled. Please contact admin.')
        else:
            # Log failed login
            SystemLog.objects.create(
                log_type='warning',
                message=f"Failed login attempt for username: {username}"
            )
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'attendance/login.html')


def logout_view(request):
    """
    Logout user
    """
    if request.user.is_authenticated:
        username = request.user.username
        logout(request)
        
        SystemLog.objects.create(
            log_type='info',
            message=f"User '{username}' logged out"
        )
        
        messages.success(request, 'You have been logged out successfully.')
    
    return redirect('login')


# ═══════════════════════════════════════════════════════════════════
# USER PROFILE VIEWS
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def user_profile(request):
    """
    View user profile - Shows profile information
    """
    user = request.user
    student = get_student_for_user(user)
    
    # Get attendance statistics
    attendance_stats = {}
    if student:
        today = timezone.localdate()
        all_attendance = Attendance.objects.filter(
            student=student,
            entry_type='success'
        )
        
        # Total attendance days
        attendance_stats['total_days'] = all_attendance.values('timestamp__date').distinct().count()
        
        # This month's attendance
        first_of_month = today.replace(day=1)
        attendance_stats['month_attendance'] = all_attendance.filter(
            timestamp__date__gte=first_of_month
        ).values('timestamp__date').distinct().count()
        
        # Last access
        attendance_stats['last_access'] = all_attendance.first()
    
    context = {
        'user': user,
        'student': student,
        'attendance_stats': attendance_stats,
        'is_admin': is_admin(user),
    }
    
    return render(request, 'attendance/profile.html', context)


@login_required(login_url='login')
def update_profile(request):
    """
    Update user profile - Allows users to update their information
    """
    user = request.user
    student = get_student_for_user(user)
    
    if request.method == 'POST':
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        # Password change (optional)
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        errors = []
        
        # Validate email uniqueness (excluding current user)
        if email and User.objects.filter(email=email).exclude(pk=user.pk).exists():
            errors.append("This email is already in use by another account.")
        
        # Password validation
        if new_password:
            if not current_password:
                errors.append("Please enter your current password to change it.")
            elif not user.check_password(current_password):
                errors.append("Current password is incorrect.")
            elif new_password != confirm_password:
                errors.append("New passwords do not match.")
            elif len(new_password) < 6:
                errors.append("New password must be at least 6 characters long.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('update_profile')
        
        # Update User model
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        
        if new_password:
            user.set_password(new_password)
        
        user.save()
        
        # Update Student model if exists
        if student:
            student.email = email if email else student.email
            student.phone = phone if phone else student.phone
            
            # Update name in student if changed
            full_name = f"{first_name} {last_name}".strip()
            if full_name:
                student.name = full_name
            
            # Handle profile photo update
            if 'photo' in request.FILES:
                photo = request.FILES['photo']
                
                # Validate file type
                allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
                if photo.content_type not in allowed_types:
                    messages.warning(request, 'Invalid image format. Please upload JPG, PNG, GIF, or WebP.')
                elif photo.size > 5 * 1024 * 1024:  # 5MB limit
                    messages.warning(request, 'Image too large. Maximum size is 5MB.')
                else:
                    # Delete old photo if exists
                    if student.photo:
                        try:
                            import os
                            if os.path.isfile(student.photo.path):
                                os.remove(student.photo.path)
                        except Exception:
                            pass  # Ignore deletion errors
                    
                    # Save new photo
                    student.photo = photo
            
            # Handle photo removal
            if request.POST.get('remove_photo') == 'true' and student.photo:
                try:
                    import os
                    if os.path.isfile(student.photo.path):
                        os.remove(student.photo.path)
                except Exception:
                    pass
                student.photo = None
            
            student.save()
        
        # Log profile update
        SystemLog.objects.create(
            log_type='info',
            message=f"User '{user.username}' updated their profile"
        )
        
        messages.success(request, 'Your profile has been updated successfully!')
        
        # Re-login if password was changed
        if new_password:
            login(request, user)
            messages.info(request, 'Your password has been changed. You are still logged in.')
        
        return redirect('user_profile')
    
    context = {
        'user': user,
        'student': student,
        'is_admin': is_admin(user),
    }
    
    return render(request, 'attendance/update_profile.html', context)


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD VIEWS
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def dashboard(request):
    """
    Dashboard - Shows different view based on user role
    - Admin: Full system dashboard
    - User: Personal attendance dashboard
    """
    if is_admin(request.user):
        return admin_dashboard(request)
    else:
        return user_dashboard(request)


def admin_dashboard(request):
    """
    Admin Dashboard - Full access to all data
    """
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    seven_days_ago = today - timedelta(days=7)

    def _percent_change(current, previous):
        if previous == 0:
            return 0.0
        return round(((current - previous) / previous) * 100, 1)

    def _trend_meta(current, previous):
        change = _percent_change(current, previous)
        if abs(change) < 0.1:
            return {
                'value': 0.0,
                'is_positive': True,
                'is_stable': True,
                'icon': 'bi-stars',
                'label': 'Stable',
            }

        is_positive = change > 0
        signed_value = abs(change)
        return {
            'value': signed_value,
            'is_positive': is_positive,
            'is_stable': False,
            'icon': 'bi-arrow-up-right' if is_positive else 'bi-arrow-down-right',
            'label': f"{signed_value:.1f}",
        }
    
    # Get today's attendance
    today_attendance = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).select_related('student').order_by('-timestamp')
    
    # Get statistics
    total_students = Student.objects.filter(is_active=True).count()
    present_today = today_attendance.values('student').distinct().count()
    absent_today = total_students - present_today

    total_students_last_week = Student.objects.filter(
        is_active=True,
        registered_at__date__lte=seven_days_ago,
    ).count()

    present_yesterday = Attendance.objects.filter(
        timestamp__date=yesterday,
        entry_type='success'
    ).values('student').distinct().count()
    total_students_yesterday = Student.objects.filter(
        is_active=True,
        registered_at__date__lte=yesterday,
    ).count()
    absent_yesterday = max(total_students_yesterday - present_yesterday, 0)

    attendance_percentage = round((present_today / total_students * 100), 1) if total_students > 0 else 0
    attendance_percentage_yesterday = round(
        (present_yesterday / total_students_yesterday * 100), 1
    ) if total_students_yesterday > 0 else 0
    
    # Get recent entries
    recent_entries = today_attendance[:10]
    
    # Weekly stats for chart
    week_stats = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Attendance.objects.filter(
            timestamp__date=day,
            entry_type='success'
        ).values('student').distinct().count()
        week_stats.append({
            'day': day.strftime('%a'),
            'date': day.strftime('%Y-%m-%d'),
            'count': count
        })

    current_week_start = today - timedelta(days=6)
    previous_week_start = today - timedelta(days=13)
    previous_week_end = today - timedelta(days=7)

    previous_week_stats_map = {
        row['timestamp__date']: row['count']
        for row in Attendance.objects.filter(
            entry_type='success',
            timestamp__date__gte=previous_week_start,
            timestamp__date__lte=previous_week_end,
        ).values('timestamp__date').annotate(count=Count('student', distinct=True))
    }

    previous_week_stats = []
    for i in range(6, -1, -1):
        day = previous_week_start + timedelta(days=i)
        previous_week_stats.append(previous_week_stats_map.get(day, 0))

    current_week_values = [item['count'] for item in week_stats]
    current_week_average = round(
        sum(current_week_values) / len(current_week_values),
        1,
    ) if current_week_values else 0.0
    previous_week_average = round(
        sum(previous_week_stats) / len(previous_week_stats),
        1,
    ) if previous_week_stats else 0.0

    week_performance_trend = _trend_meta(current_week_average, previous_week_average)

    section_names = list(
        Department.objects.filter(is_active=True)
        .annotate(active_students=Count('students', filter=Q(students__is_active=True)))
        .order_by('-active_students', 'name')
        .values_list('name', flat=True)
    )

    section_labels = [item['day'] for item in week_stats]
    section_series = {name: [0] * len(section_labels) for name in section_names}
    if not section_names:
        section_names = ['Unassigned']
        section_series = {'Unassigned': [0] * len(section_labels)}

    day_index = {
        (current_week_start + timedelta(days=i)): i for i in range(len(section_labels))
    }

    section_rows = Attendance.objects.filter(
        entry_type='success',
        timestamp__date__gte=current_week_start,
        timestamp__date__lte=today,
    ).values(
        'timestamp__date',
        'student__department__name',
    ).annotate(count=Count('student', distinct=True))

    for row in section_rows:
        day = row['timestamp__date']
        idx = day_index.get(day)
        if idx is None:
            continue

        department_name = row.get('student__department__name') or 'Unassigned'
        if department_name in section_series:
            section_series[department_name][idx] += row['count']

    section_week_stats = {
        'labels': section_labels,
        'sections': section_names,
        'series': section_series,
    }
    
    context = {
        'is_admin': True,
        'total_students': total_students,
        'present_today': present_today,
        'absent_today': absent_today,
        'recent_entries': recent_entries,
        'today': today,
        'attendance_percentage': attendance_percentage,
        'week_stats': week_stats,
        'current_week_average': current_week_average,
        'week_performance_trend': week_performance_trend,
        'section_week_stats': section_week_stats,
        'total_students_trend': _trend_meta(total_students, total_students_last_week),
        'present_trend': _trend_meta(present_today, present_yesterday),
        'absent_trend': _trend_meta(absent_today, absent_yesterday),
        'attendance_rate_trend': _trend_meta(attendance_percentage, attendance_percentage_yesterday),
    }
    
    return render(request, 'attendance/admin_dashboard.html', context)


def user_dashboard(request):
    """
    User Dashboard - Personal attendance records only
    """
    today = timezone.localdate()
    
    # Get student profile for logged-in user
    student = get_student_for_user(request.user)
    
    if not student:
        messages.warning(request, 'No student profile linked to your account. Please contact admin.')
        context = {
            'is_admin': False,
            'student': None,
            'has_profile': False,
        }
        return render(request, 'attendance/user_dashboard.html', context)
    
    # Get user's attendance records
    all_attendance = Attendance.objects.filter(
        student=student,
        entry_type='success'
    )
    
    # Today's status
    is_present_today = all_attendance.filter(timestamp__date=today).exists()
    
    # Get last access
    last_access = all_attendance.first()  # Already ordered by -timestamp
    
    # This month's attendance
    first_of_month = today.replace(day=1)
    month_attendance = all_attendance.filter(
        timestamp__date__gte=first_of_month
    ).values('timestamp__date').distinct().count()
    
    # Total attendance days
    total_days = all_attendance.values('timestamp__date').distinct().count()
    
    # Recent attendance records
    recent_records = Attendance.objects.filter(student=student).order_by('-timestamp')[:20]
    
    # Weekly attendance for chart
    week_attendance = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        present = all_attendance.filter(timestamp__date=day).exists()
        week_attendance.append({
            'day': day.strftime('%a'),
            'date': day.strftime('%Y-%m-%d'),
            'present': present
        })
    
    context = {
        'is_admin': False,
        'student': student,
        'has_profile': True,
        'is_present_today': is_present_today,
        'last_access': last_access,
        'month_attendance': month_attendance,
        'total_days': total_days,
        'recent_records': recent_records,
        'week_attendance': week_attendance,
        'today': today,
    }
    
    return render(request, 'attendance/user_dashboard.html', context)


# ═══════════════════════════════════════════════════════════════════
# STUDENT REGISTRATION (Admin Only)
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def register_student(request):
    """
    Student registration page - Admin only
    """
    if request.method == 'POST':
        return handle_student_registration(request)
    
    # Fetch active departments and sections from database
    departments = Department.objects.filter(is_active=True).values_list('name', flat=True).order_by('name')
    sections = Section.objects.filter(is_active=True).select_related('department').order_by('department__name', 'name')
    
    context = {
        'camera_index': CAMERA_INDEX,
        'departments': list(departments),
        'sections': sections,
        'user_types': [
            ('student', 'Student'),
            ('staff', 'Staff'),
            ('visitor', 'Visitor'),
        ]
    }
    
    return render(request, 'attendance/register_student.html', context)

def handle_student_registration(request):
    """
    Handle POST request for student registration
    Also creates a User account and saves profile photo
    """
    try:
        # Get form data
        name = request.POST.get('name', '').strip()
        roll_number = request.POST.get('roll_number', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        department = request.POST.get('department', '').strip()
        section_id = request.POST.get('section', '').strip()
        user_type = request.POST.get('user_type', 'student')
        face_encodings_json = request.POST.get('face_encodings', '')
        profile_photo_data = request.POST.get('profile_photo', '')  # Base64 image
        create_account = request.POST.get('create_account', 'on')  # Checkbox
        
        # Validation
        errors = []
        
        if not name:
            errors.append("Name is required")
        
        if not roll_number:
            errors.append("Roll Number/ID is required")
        elif Student.objects.filter(roll_number=roll_number).exists():
            errors.append(f"Roll Number '{roll_number}' already exists")
        
        if not face_encodings_json:
            errors.append("Face data is required. Please capture face images.")
        
        if not department:
            errors.append("Department is required")

        if not section_id:
            errors.append("Section is required")
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('register_student')
        
        # ═══════════════════════════════════════════════════════════
        # SAVE PROFILE PHOTO FROM BASE64
        # ═══════════════════════════════════════════════════════════
        saved_photo_path = None
        
        if profile_photo_data:
            try:
                # Remove data URL prefix
                if 'base64,' in profile_photo_data:
                    profile_photo_data = profile_photo_data.split('base64,')[1]
                
                # Decode base64
                image_data = base64.b64decode(profile_photo_data)
                
                # Create filename
                filename = f"{roll_number.replace(' ', '_').replace('-', '_')}_{uuid.uuid4().hex[:8]}.jpg"
                
                # Ensure directory exists
                faces_dir = os.path.join(settings.MEDIA_ROOT, 'faces')
                os.makedirs(faces_dir, exist_ok=True)
                
                # Save file
                filepath = os.path.join(faces_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                
                saved_photo_path = f"faces/{filename}"
                print(f"✅ Profile photo saved: {saved_photo_path}")
                
            except Exception as e:
                print(f"⚠️ Error saving photo: {e}")
                # Continue without photo - not critical
        
        # Get department and section objects
        department_obj = Department.objects.filter(name=department).first()
        section_obj = Section.objects.filter(pk=section_id).first()
        if section_obj and department_obj and section_obj.department_id != department_obj.id:
            # Selected section does not belong to selected department
            errors.append("Selected section does not belong to the selected department")
        
        # Create User account if checkbox is checked
        user = None
        generated_username = None
        generated_password = None

        if create_account:
            # Get custom or generate username
            custom_username = request.POST.get('custom_username', '').strip()
            custom_password = request.POST.get('custom_password', '').strip()
            
            if custom_username:
                generated_username = custom_username.lower().replace(' ', '_')
            else:
                generated_username = roll_number.lower().replace(' ', '').replace('-', '_')
            
            # Check if username exists
            base_username = generated_username
            counter = 1
            while User.objects.filter(username=generated_username).exists():
                generated_username = f"{base_username}_{counter}"
                counter += 1
            
            # Use custom password or generate one
            if custom_password:
                generated_password = custom_password
            else:
                clean_roll = ''.join(c for c in roll_number if c.isalnum())
                generated_password = f"{clean_roll}@123"
            
            # Create user
            user = User.objects.create_user(
                username=generated_username,
                email=email if email else None,
                password=generated_password,
                first_name=name.split()[0] if name else '',
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
            )
            
            print(f"Created user: {generated_username} with password: {generated_password}")  # Debug log
        
        # Create student
        student = Student.objects.create(
            user=user,
            name=name,
            roll_number=roll_number,
            email=email if email else None,
            phone=phone if phone else None,
            department=department_obj if department_obj else None,
            section=section_obj if section_obj else None,
            user_type=user_type,
            face_encoding=face_encodings_json,
            photo=saved_photo_path,  # Path to saved image
            is_active=True
        )
        
        # Send welcome email
        if NOTIFICATIONS_AVAILABLE and user and generated_password:
            try:
                NotificationService.notify_registration(student, generated_username, generated_password)
            except Exception as e:
                print(f"Notification error: {e}")
        
        # Refresh face recognition cache
        service = get_face_recognition_service()
        service.refresh_cache()
        
        # Log registration
        SystemLog.objects.create(
            log_type='success',
            message=f"New student registered: {name} ({roll_number})"
        )
        
        # Success message with login credentials
        if user and generated_password:
            messages.success(
                request, 
                f'''
                <div id="success-message" class="p-3">
                    <div class="d-flex align-items-start">
                        <div class="me-3">
                            <span style="font-size: 3rem;">🎉</span>
                        </div>
                        <div class="flex-grow-1">
                            <h4 class="mb-3 text-success">
                                <i class="bi bi-check-circle-fill me-2"></i>Student Registered Successfully!
                            </h4>
                            <p class="mb-3"><strong>{name}</strong> has been added to the system.</p>
                            
                            <div class="card border-primary" style="max-width: 400px;">
                                <div class="card-header bg-primary text-white">
                                    <i class="bi bi-key-fill me-2"></i>Login Credentials
                                </div>
                                <div class="card-body">
                                    <div class="mb-3">
                                        <label class="form-label text-muted small mb-1">Username</label>
                                        <div class="input-group">
                                            <input type="text" class="form-control bg-light" value="{generated_username}" id="copy-username" readonly>
                                            <button class="btn btn-outline-primary" type="button" onclick="copyToClipboard('copy-username')">
                                                <i class="bi bi-clipboard"></i>
                                            </button>
                                        </div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label text-muted small mb-1">Password</label>
                                        <div class="input-group">
                                            <input type="text" class="form-control bg-light" value="{generated_password}" id="copy-password" readonly>
                                            <button class="btn btn-outline-primary" type="button" onclick="copyToClipboard('copy-password')">
                                                <i class="bi bi-clipboard"></i>
                                            </button>
                                        </div>
                                    </div>
                                    <div class="alert alert-warning mb-0 py-2">
                                        <small>
                                            <i class="bi bi-exclamation-triangle-fill me-1"></i>
                                            Please save these credentials! This message will disappear.
                                        </small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <script>
                function copyToClipboard(elementId) {{
                    const input = document.getElementById(elementId);
                    input.select();
                    document.execCommand('copy');
                    
                    const btn = input.nextElementSibling;
                    const originalHtml = btn.innerHTML;
                    btn.innerHTML = '<i class="bi bi-check"></i>';
                    btn.classList.remove('btn-outline-primary');
                    btn.classList.add('btn-success');
                    
                    setTimeout(() => {{
                        btn.innerHTML = originalHtml;
                        btn.classList.remove('btn-success');
                        btn.classList.add('btn-outline-primary');
                    }}, 2000);
                }}
                </script>
                '''
            )
        else:
            messages.success(request, f"✅ Student '{name}' registered successfully!")
        
        return redirect('student_list')
        
    except Exception as e:
        messages.error(request, f"Registration failed: {str(e)}")
        SystemLog.objects.create(
            log_type='error',
            message=f"Registration failed: {str(e)}"
        )
        return redirect('register_student')
# ═══════════════════════════════════════════════════════════════════
# FACE CAPTURE API
# ═══════════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(["POST"])
def capture_face_api(request):
    """
    API endpoint to process captured face image from webcam
    """
    try:
        data = json.loads(request.body)
        image_data = data.get('image', '')
        
        if not image_data:
            return JsonResponse({
                'success': False,
                'error': 'No image data received'
            })
        
        # Remove data URL prefix if present
        if 'base64,' in image_data:
            image_data = image_data.split('base64,')[1]
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return JsonResponse({
                'success': False,
                'error': 'Could not decode image'
            })
        
        # Get face recognition service
        service = get_face_recognition_service()
        
        # Detect face
        face_location = service.detect_single_face(image)
        
        print(f"Detected face location: {face_location}")  # Debug log
        
        if face_location is None:
            return JsonResponse({
                'success': False,
                'error': 'No face detected. Please position your face in the frame.'
            })
        
        # Check if face is valid
        if not service.is_face_valid(face_location):
            return JsonResponse({
                'success': False,
                'error': 'Face is too small. Please move closer to the camera.'
            })
        
        # Generate encoding
        encoding = service.generate_encoding(image, face_location)
        
        if encoding is None:
            return JsonResponse({
                'success': False,
                'error': 'Could not generate face encoding'
            })
        
        return JsonResponse({
            'success': True,
            'encoding': encoding.tolist(),
            'face_location': {
                'top': face_location[0],
                'right': face_location[1],
                'bottom': face_location[2],
                'left': face_location[3]
            },
            'message': 'Face captured successfully!'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@csrf_exempt
@require_http_methods(["GET"])
def check_camera_api(request):
    """
    API endpoint to check if camera is available
    """
    try:
        cap = cv2.VideoCapture(CAMERA_INDEX)
        
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                return JsonResponse({
                    'success': True,
                    'camera_index': CAMERA_INDEX,
                    'message': 'Camera is available'
                })
        
        return JsonResponse({
            'success': False,
            'error': 'Camera not available.'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


# ═══════════════════════════════════════════════════════════════════
# STUDENT MANAGEMENT (Admin Only)
# ═════════════════════════════════════════════════��═════════════════

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def student_list(request):
    """
    List all registered students - Admin only
    """
    search = request.GET.get('search', '')
    department = request.GET.get('department', '')
    section = request.GET.get('section', '')
    user_type = request.GET.get('user_type', '')
    status = request.GET.get('status', '')
    
    students = Student.objects.all().order_by('registered_at')
    
    if search:
        students = students.filter(
            Q(name__icontains=search) |
            Q(roll_number__icontains=search) |
            Q(email__icontains=search)
        )
    
    if department:
        students = students.filter(department__name__iexact=department)

    if section:
        students = students.filter(section__name__iexact=section)
    
    if user_type:
        students = students.filter(user_type__iexact=user_type)
    
    if status:
        if status == 'active':
            students = students.filter(is_active=True)
        elif status == 'inactive':
            students = students.filter(is_active=False)

    scope_students = Student.objects.filter(is_active=True)
    if department:
        scope_students = scope_students.filter(department__name__iexact=department)
    if section:
        scope_students = scope_students.filter(section__name__iexact=section)

    scope_total_students = scope_students.count()
    if department and section:
        students_scope_label = f'Department: {department} | Section: {section}'
    elif section:
        students_scope_label = f'Section: {section}'
    elif department:
        students_scope_label = f'Department: {department}'
    else:
        students_scope_label = 'All Active Students'

    filtered_students_count = students.count()
    
    paginator = Paginator(students, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get unique active departments from database
    departments = Department.objects.filter(is_active=True).values_list('name', flat=True).order_by('name')
    sections = Section.objects.filter(is_active=True).select_related('department').order_by('department__name', 'name')
    
    context = {
        'page_obj': page_obj,
        'students': page_obj,
        'total_students': students.count(),
        'scope_total_students': scope_total_students,
        'filtered_students_count': filtered_students_count,
        'students_scope_label': students_scope_label,
        'departments': list(departments),
        'sections': sections,
        'search': search,
        'selected_department': department,
        'selected_section': section,
        'selected_user_type': user_type,
        'selected_status': status,
    }
    
    return render(request, 'attendance/student_list.html', context)


@login_required(login_url='login')
def student_detail(request, pk):
    """
    View student details - Admin sees any student, User sees only self
    """
    student = get_object_or_404(Student, pk=pk)
    
    # Check permission: Admin can see all, User can see only their own
    if not is_admin(request.user):
        user_student = get_student_for_user(request.user)
        if not user_student or user_student.pk != student.pk:
            messages.error(request, 'You do not have permission to view this profile.')
            return redirect('dashboard')
    
    all_attendance = Attendance.objects.filter(
        student=student,
        entry_type='success'
    )
    
    total_days = all_attendance.values('timestamp__date').distinct().count()
    
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_attendance = Attendance.objects.filter(
        student=student,
        timestamp__gte=thirty_days_ago,
        entry_type='success'
    ).values('timestamp__date').distinct().count()
    
    attendance_records = Attendance.objects.filter(
        student=student
    ).order_by('-timestamp')[:50]
    
    context = {
        'student': student,
        'attendance_records': attendance_records,
        'total_attendance_days': total_days,
        'recent_attendance': recent_attendance,
        'is_admin': is_admin(request.user),
    }
    
    return render(request, 'attendance/student_detail.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def delete_student(request, pk):
    """
    Delete a student - Admin only
    """
    try:
        student = Student.objects.get(pk=pk)
    except Student.DoesNotExist:
        messages.error(request, f"Student with ID {pk} does not exist or has already been deleted.")
        return redirect('student_list')
    
    if request.method == 'POST':
        name = student.name
        
        # Also delete linked user account
        if student.user:
            student.user.delete()
        
        student.delete()
        
        service = get_face_recognition_service()
        service.refresh_cache()
        
        SystemLog.objects.create(
            log_type='warning',
            message=f"Student deleted: {name}"
        )
        
        messages.success(request, f"Student '{name}' has been deleted.")
        return redirect('student_list')
    
    return render(request, 'attendance/delete_student.html', {'student': student})


@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def toggle_student_status(request, pk):
    """
    Toggle student active/inactive status - Admin only
    """
    student = get_object_or_404(Student, pk=pk)
    student.is_active = not student.is_active
    student.save()
    
    # Also toggle user account if exists
    if student.user:
        student.user.is_active = student.is_active
        student.user.save()
    
    service = get_face_recognition_service()
    service.refresh_cache()
    
    status = "activated" if student.is_active else "deactivated"
    messages.success(request, f"Student '{student.name}' has been {status}.")
    
    return redirect('student_list')


# ═══════════════════════════════════════════════════════════════════
# ATTENDANCE RECORDS
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def attendance_list(request):
    """
    View attendance records
    - Admin: All records
    - User: Only their own records
    """
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    student_id = request.GET.get('student', '')
    entry_type = request.GET.get('entry_type', '')
    
    # Base queryset based on user role
    if is_admin(request.user):
        records = Attendance.objects.all().select_related('student').order_by('-timestamp')
    else:
        student = get_student_for_user(request.user)
        if student:
            records = Attendance.objects.filter(student=student).order_by('-timestamp')
        else:
            records = Attendance.objects.none()
    
    # Apply filters
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            records = records.filter(timestamp__date__gte=date_from_obj)
        except:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            records = records.filter(timestamp__date__lte=date_to_obj)
        except:
            pass
    
    if student_id and is_admin(request.user):
        records = records.filter(student_id=student_id)
    
    if entry_type == 'success':
        records = records.filter(entry_type=entry_type)
    
    paginator = Paginator(records, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    students = Student.objects.filter(is_active=True).order_by('name') if is_admin(request.user) else []
    
    context = {
        'page_obj': page_obj,
        'records': page_obj,
        'total_records': records.count(),
        'students': students,
        'date_from': date_from,
        'date_to': date_to,
        'selected_student': student_id,
        'selected_entry_type': entry_type,
        'is_admin': is_admin(request.user),
    }
    
    return render(request, 'attendance/attendance_list.html', context)


# ═══════════════════════════════════════════════════════════════════
# REPORTS (Admin Only)
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def reports(request):
    """
    Reports page - Admin only
    """
    context = {
        'students': Student.objects.filter(is_active=True).order_by('name'),
        'departments': Department.objects.filter(is_active=True).order_by('name'),
        'sections': Section.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'attendance/reports.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def generate_report(request):
    """
    Generate attendance report - Admin only
    """
    if request.method != 'POST':
        return redirect('reports')
    
    report_type = request.POST.get('report_type', 'daily')
    date_from = request.POST.get('date_from', '')
    date_to = request.POST.get('date_to', '')
    student_id = request.POST.get('student', '')
    department_id = request.POST.get('department', '')
    section_id = request.POST.get('section', '')
    format_type = request.POST.get('format', 'html')
    
    records = Attendance.objects.select_related('student')
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            records = records.filter(timestamp__date__gte=date_from_obj)
        except:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            records = records.filter(timestamp__date__lte=date_to_obj)
        except:
            pass
    
    if student_id:
        records = records.filter(student_id=student_id)

    if department_id:
        records = records.filter(student__department_id=department_id)

    if section_id:
        # filter by student's section (Section is a FK on Student)
        records = records.filter(student__section_id=section_id)

    selected_student_name = ''
    if student_id:
        selected_student = Student.objects.filter(pk=student_id).first()
        if selected_student:
            selected_student_name = selected_student.name

    selected_department_name = ''
    if department_id:
        selected_department = Department.objects.filter(pk=department_id).first()
        if selected_department:
            selected_department_name = selected_department.name

    selected_section_name = ''
    if section_id:
        selected_section = Section.objects.filter(pk=section_id).first()
        if selected_section:
            selected_section_name = selected_section.name

    student_scope = Student.objects.filter(is_active=True)
    if student_id:
        student_scope = student_scope.filter(pk=student_id)
    if department_id:
        student_scope = student_scope.filter(department_id=department_id)
    
    records = records.order_by('-timestamp')

    success_records = records.filter(entry_type='success')

    summary = success_records.values('student__name', 'student__roll_number').annotate(
        total_days=Count('timestamp__date', distinct=True),
        total_entries=Count('id')
    ).order_by('-total_days', 'student__name')

    daily_stats = records.values('timestamp__date').annotate(
        total_entries=Count('id'),
        success_entries=Count('id', filter=Q(entry_type='success')),
        unique_students=Count('student', distinct=True),
        success_students=Count('student', filter=Q(entry_type='success'), distinct=True)
    ).order_by('timestamp__date')

    summary_list = list(summary)
    daily_stats_list = list(daily_stats)
    for item in daily_stats_list:
        item['denied_entries'] = 0
        item['denied_students'] = 0
    max_summary_days = max([item['total_days'] for item in summary_list], default=1)
    max_daily_entries = max([item['total_entries'] for item in daily_stats_list], default=1)
    max_daily_students = max([item['unique_students'] for item in daily_stats_list], default=1)

    total_records = records.count()
    total_success = success_records.count()
    total_denied = 0
    unique_students = records.exclude(student__isnull=True).values('student').distinct().count()
    if department_id:
        student_scope = student_scope.filter(department_id=department_id)
    if section_id:
        student_scope = student_scope.filter(section_id=section_id)
    scope_total_students = student_scope.count()
    active_days = success_records.values('timestamp__date').distinct().count()
    avg_per_day = round((total_success / active_days), 1) if active_days > 0 else 0

    context = {
        'report_type': report_type,
        'records': records[:500],
        'summary': summary_list,
        'daily_stats': daily_stats_list,
        'max_summary_days': max_summary_days,
        'max_daily_entries': max_daily_entries,
        'max_daily_students': max_daily_students,
        'date_from': date_from,
        'date_to': date_to,
        'selected_student_name': selected_student_name,
        'selected_department_name': selected_department_name,
        'selected_section_name': selected_section_name,
        'total_records': total_records,
        'total_success': total_success,
        'total_denied': total_denied,
        'unique_students': unique_students,
        'scope_total_students': scope_total_students,
        'avg_per_day': avg_per_day,
    }
    
    if format_type == 'excel':
        return generate_excel_report(records, summary, request)

    if format_type == 'pdf':
        return generate_pdf_report(records, request)
    
    return render(request, 'attendance/report_result.html', context)


def generate_pdf_report(records, request):
    """Generate a professional PDF attendance report."""
    try:
        from reportlab.lib import colors  # type: ignore[import-not-found]
        from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore[import-not-found]
        from reportlab.lib.units import mm  # type: ignore[import-not-found]
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image  # type: ignore[import-not-found]

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title='Attendance Report',
        )

        styles = getSampleStyleSheet()
        style_uni = ParagraphStyle(
            'UniTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=18,
            textColor=colors.HexColor('#111827'),
            alignment=1,
            leading=22,
        )
        style_report = ParagraphStyle(
            'ReportTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=colors.HexColor('#2563EB'),
            alignment=1,
            leading=14,
        )
        style_meta = ParagraphStyle(
            'Meta',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.HexColor('#1F2937'),
            alignment=0,
            leading=13,
        )
        style_summary = ParagraphStyle(
            'Summary',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=colors.HexColor('#1E3A8A'),
            alignment=1,
        )
        style_footer = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            textColor=colors.HexColor('#6B7280'),
            alignment=2,
        )

        dept_id = request.POST.get('department', '') if hasattr(request, 'POST') else ''
        sec_id = request.POST.get('section', '') if hasattr(request, 'POST') else ''
        date_from = request.POST.get('date_from', '') if hasattr(request, 'POST') else ''
        date_to = request.POST.get('date_to', '') if hasattr(request, 'POST') else ''
        subject_name = request.POST.get('subject', '').strip() if hasattr(request, 'POST') else ''

        dept_name = 'All Departments'
        if dept_id:
            dept = Department.objects.filter(pk=dept_id).first()
            if dept:
                dept_name = dept.name

        sec_name = 'All Sections'
        if sec_id:
            sec = Section.objects.filter(pk=sec_id).first()
            if sec:
                sec_name = sec.name

        if date_from and date_to and date_from == date_to:
            date_label = date_from
        elif date_from and date_to:
            date_label = f'{date_from} to {date_to}'
        elif date_from:
            date_label = f'From {date_from}'
        elif date_to:
            date_label = f'Up to {date_to}'
        else:
            date_label = 'All Dates'

        generated_at = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %I:%M %p')

        student_scope = Student.objects.filter(is_active=True)
        if dept_id:
            student_scope = student_scope.filter(department__name__iexact=dept_name)
        if sec_id:
            student_scope = student_scope.filter(section__name__iexact=sec_name)

        total_students_scope = student_scope.count()
        total_entries = records.count()
        present_entries = records.filter(entry_type='success').count()
        unique_students = records.exclude(student__isnull=True).values('student').distinct().count()

        logo_path = None
        logo_candidates = []
        static_root = str(settings.STATIC_ROOT) if getattr(settings, 'STATIC_ROOT', None) else ''
        media_root = str(settings.MEDIA_ROOT) if getattr(settings, 'MEDIA_ROOT', None) else ''
        base_dir = str(settings.BASE_DIR) if getattr(settings, 'BASE_DIR', None) else ''
        if static_root:
            logo_candidates += [
                os.path.join(static_root, 'images', 'logo.png'),
                os.path.join(static_root, 'logo.png'),
            ]
        if media_root:
            logo_candidates += [
                os.path.join(media_root, 'logo.png'),
                os.path.join(media_root, 'images', 'logo.png'),
            ]
        if base_dir:
            logo_candidates += [
                os.path.join(base_dir, 'static', 'images', 'logo.png'),
                os.path.join(base_dir, 'static', 'logo.png'),
            ]
        for cand in logo_candidates:
            if cand and os.path.isfile(cand):
                logo_path = cand
                break

        story = []

        heading_text = Paragraph(
            'The Islamia University of Bahawalpur<br/><font size="11" color="#2563EB"><b>Faculty of Computing </b></font>',
            style_uni,
        )
        if logo_path:
            logo = Image(logo_path, width=20 * mm, height=20 * mm)
            heading_table = Table([[logo, heading_text]], colWidths=[24 * mm, 162 * mm])
            heading_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(heading_table)
        else:
            story.append(Paragraph('The Islamia University of Bahawalpur', style_uni))
            story.append(Paragraph('Faculty of Computing ', style_report))

        story.append(Spacer(1, 5))

        meta_rows = [
            [Paragraph(f'<b>Department:</b> {dept_name}', style_meta), Paragraph(f'<b>Section:</b> {sec_name}', style_meta)],
            [Paragraph(f'<b>Date:</b> {date_label}', style_meta), Paragraph('', style_meta)],
            
        ]
        if subject_name:
            meta_rows.append([Paragraph(f'<b>Subject:</b> {subject_name}', style_meta), Paragraph('', style_meta)])

        meta_table = Table(meta_rows, colWidths=[93 * mm, 93 * mm])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 7))

        summary_table = Table([
            [
                Paragraph(f'Total Students: {total_students_scope}', style_summary),
                Paragraph(f'Present Students: {unique_students}', style_summary),
                Paragraph(f'', style_summary),

            ]
        ], colWidths=[62 * mm, 62 * mm, 62 * mm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#DBEAFE')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#93C5FD')),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#BFDBFE')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 8))

        table_data = [['Sr.', 'Name', 'Roll Number', 'Date', 'Time', 'Status']]
        row_status = []
        for idx, record in enumerate(records[:1000], 1):
            local_ts = timezone.localtime(record.timestamp) if timezone.is_aware(record.timestamp) else record.timestamp
            status_text = 'Present' if record.entry_type == 'success' else 'Denied'
            row_status.append(status_text)
            table_data.append([
                str(idx),
                record.student.name if record.student else 'Unknown',
                record.student.roll_number if record.student else 'N/A',
                local_ts.strftime('%Y-%m-%d'),
                local_ts.strftime('%I:%M %p').lstrip('0'),
                status_text,
            ])

        if len(table_data) == 1:
            table_data.append(['-', 'No records found for selected filters', '-', '-', '-', '-'])

        attendance_table = Table(
            table_data,
            repeatRows=1,
            colWidths=[12 * mm, 66 * mm, 32 * mm, 24 * mm, 21 * mm, 31 * mm],
        )
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E40AF')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9.5),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8.8),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D1D5DB')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (3, 1), (5, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]

        for i, status_text in enumerate(row_status, start=1):
            if status_text == 'Present':
                table_style.append(('TEXTCOLOR', (5, i), (5, i), colors.HexColor('#166534')))
            else:
                table_style.append(('TEXTCOLOR', (5, i), (5, i), colors.HexColor('#B91C1C')))

        attendance_table.setStyle(TableStyle(table_style))
        story.append(attendance_table)
        story.append(Spacer(1, 7))
        story.append(Paragraph(f'This is a system-generated attendance report. Generated on: {generated_at}', style_footer))

        def _draw_page_footer(canvas, doc_obj):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.HexColor('#6B7280'))
            canvas.drawRightString(A4[0] - (16 * mm), 9 * mm, f'Page {doc_obj.page}')
            canvas.restoreState()

        doc.build(story, onFirstPage=_draw_page_footer, onLaterPages=_draw_page_footer)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f"Error generating PDF report: {str(e)}")
        return redirect('reports')


def generate_excel_report(records, summary, request):
    """
    Generate Excel report
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

        # Read optional filters from the request to show in header
        dept_id = request.POST.get('department') if hasattr(request, 'POST') else None
        sec_id = request.POST.get('section') if hasattr(request, 'POST') else None
        date_from = request.POST.get('date_from', '') if hasattr(request, 'POST') else ''
        date_to = request.POST.get('date_to', '') if hasattr(request, 'POST') else ''
        subject_name = (request.POST.get('subject', '').strip() if hasattr(request, 'POST') else '')
        dept_name = ''
        sec_name = ''
        if dept_id:
            d = Department.objects.filter(pk=dept_id).first()
            if d:
                dept_name = d.name
        if sec_id:
            s = Section.objects.filter(pk=sec_id).first()
            if s:
                sec_name = s.name

        # Try to embed a logo if available in common locations
        logo_path = None
        logo_candidates = []
        try:
            static_root = str(settings.STATIC_ROOT) if getattr(settings, 'STATIC_ROOT', None) else ''
            media_root = str(settings.MEDIA_ROOT) if getattr(settings, 'MEDIA_ROOT', None) else ''
            base_dir = str(settings.BASE_DIR) if getattr(settings, 'BASE_DIR', None) else ''
        except Exception:
            static_root = media_root = base_dir = ''

        if static_root:
            logo_candidates += [
                os.path.join(static_root, 'images', 'logo.png'),
                os.path.join(static_root, 'logo.png'),
            ]
        if media_root:
            logo_candidates += [
                os.path.join(media_root, 'logo.png'),
                os.path.join(media_root, 'images', 'logo.png'),
            ]
        if base_dir:
            logo_candidates += [
                os.path.join(base_dir, 'static', 'images', 'logo.png'),
                os.path.join(base_dir, 'static', 'logo.png'),
            ]

        for cand in logo_candidates:
            try:
                if cand and os.path.isfile(cand):
                    logo_path = cand
                    break
            except Exception:
                continue

        # Reserve top rows for a single report info box + logo
        header_row = 6

        # Insert logo if available
        if logo_path:
            try:
                from openpyxl.drawing.image import Image as XLImage
                img = XLImage(logo_path)
                img.width = 120
                img.height = 60
                ws.add_image(img, 'A1')
            except Exception:
                # if image can't be embedded, ignore and continue
                pass

        # Draw one clean top box for report metadata
        box_fill = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
        box_border = Border(
            left=Side(style='thin', color='B8C3E6'),
            right=Side(style='thin', color='B8C3E6'),
            top=Side(style='thin', color='B8C3E6'),
            bottom=Side(style='thin', color='B8C3E6'),
        )
        for r in range(1, 5):
            for c in range(1, 7):
                cell = ws.cell(row=r, column=c)
                cell.fill = box_fill
                cell.border = box_border

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
        title_cell = ws.cell(row=1, column=1, value='The Islamia University of Bahawalpur')
        title_cell.font = Font(bold=True, size=14, color="1F2A44")
        title_cell.alignment = Alignment(horizontal='center', vertical='center')

        date_label = 'All Dates'
        if date_from and date_to and date_from == date_to:
            date_label = date_from
        elif date_from and date_to:
            date_label = f'{date_from} to {date_to}'
        elif date_from:
            date_label = f'From {date_from}'
        elif date_to:
            date_label = f'Up to {date_to}'

        dept_label = dept_name if dept_name else 'All Departments'
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=6)
        dept_cell = ws.cell(row=2, column=1, value=f'Department: {dept_label}')
        dept_cell.font = Font(bold=False, size=11, color="2B2D42")
        dept_cell.alignment = Alignment(horizontal='center', vertical='center')

        sec_label = sec_name if sec_name else 'All Sections'
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=6)
        sec_cell = ws.cell(row=3, column=1, value=f'Section: {sec_label}')
        sec_cell.font = Font(bold=False, size=11, color="2B2D42")
        sec_cell.alignment = Alignment(horizontal='center', vertical='center')

        # Keep Date + Subject in a single row cell so text remains within one box.
        ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=6)
        row4_text = f'Date: {date_label}'
        if subject_name:
            row4_text = f'{row4_text}    |    Subject: {subject_name}'
        row4_cell = ws.cell(row=4, column=1, value=row4_text)
        row4_cell.font = Font(bold=True, size=11, color="243B6B")
        row4_cell.alignment = Alignment(horizontal='left', vertical='center', shrink_to_fit=True)

        headers = ['Sr.', 'Name', 'Roll Number', 'Date', 'Time', 'Status']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

        for row, record in enumerate(records[:1000], header_row + 1):
            local_timestamp = timezone.localtime(record.timestamp) if timezone.is_aware(record.timestamp) else record.timestamp
            display_time = local_timestamp.strftime('%I:%M %p').lstrip('0')
            ws.cell(row=row, column=1, value=(row - header_row))
            ws.cell(row=row, column=2, value=record.student.name if record.student else 'Unknown')
            ws.cell(row=row, column=3, value=record.student.roll_number if record.student else 'N/A')
            ws.cell(row=row, column=4, value=local_timestamp.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=5, value=display_time)
            ws.cell(row=row, column=6, value='Present')
        
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 25
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 10
        ws.column_dimensions['F'].width = 10
        ws.row_dimensions[1].height = 24
        ws.row_dimensions[2].height = 20
        ws.row_dimensions[3].height = 20
        ws.row_dimensions[4].height = 20
        
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response
        
    except Exception as e:
        messages.error(request, f"Error generating Excel report: {str(e)}")
        return redirect('reports')


# ═══════════════════════════════════════════════════════════════════
# SYSTEM LOGS (Admin Only)
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='dashboard')
def system_logs(request):
    """
    View system logs - Admin only
    """
    log_type = request.GET.get('type', '')
    
    logs = SystemLog.objects.all().order_by('-timestamp')
    
    if log_type:
        logs = logs.filter(log_type=log_type)
    
    paginator = Paginator(logs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for log in page_obj.object_list:
        log.image_url = _resolve_log_image_url(log)
    
    context = {
        'page_obj': page_obj,
        'logs': page_obj,
        'selected_type': log_type,
    }
    
    return render(request, 'attendance/system_logs.html', context)


def _resolve_log_image_url(log):
    """Return a media URL for unknown-person log snapshots when available."""
    if not log:
        return None

    message = (log.message or '').lower()
    # Check for either "unknown" or "pir motion detected" + "no known face" patterns
    has_unknown = 'unknown' in message
    has_pir_motion = ('pir motion detected' in message and 'no known face' in message)
    
    if not (has_unknown or has_pir_motion):
        return None

    details = (log.details or '').strip()
    if not details:
        return None

    image_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    details_lower = details.lower()
    if not details_lower.endswith(image_exts):
        return None

    media_url = str(settings.MEDIA_URL).rstrip('/') + '/'

    if details.startswith(str(settings.MEDIA_URL)):
        return details

    normalized = os.path.normpath(details)
    candidates = []

    if os.path.isabs(normalized):
        candidates.append(normalized)
    else:
        candidates.append(os.path.normpath(os.path.join(str(settings.BASE_DIR), normalized)))
        candidates.append(os.path.normpath(os.path.join(str(settings.MEDIA_ROOT), normalized)))

        if details.startswith('media/') or details.startswith('media\\'):
            relative = details[6:].replace('\\', '/').lstrip('/')
            return f"{media_url}{relative}"

    media_root_norm = os.path.normpath(str(settings.MEDIA_ROOT))

    for file_path in candidates:
        if not os.path.isfile(file_path):
            continue

        try:
            relative = os.path.relpath(file_path, media_root_norm)
        except ValueError:
            continue

        if relative.startswith('..'):
            continue

        relative_url = relative.replace('\\', '/')
        return f"{media_url}{relative_url}"

    return None


# ═══════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@login_required(login_url='login')
@require_http_methods(["POST"])
def notification_state_api(request):
    """Persist read/clear notification state for the current user."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    action = payload.get('action')
    keys = payload.get('keys', [])
    if action not in {'read', 'clear'}:
        return JsonResponse({'success': False, 'error': 'Unsupported action'}, status=400)
    if not isinstance(keys, list):
        return JsonResponse({'success': False, 'error': 'keys must be a list'}, status=400)

    updated_count = 0
    for raw_key in set(keys):
        notification_type, object_id = _parse_notification_key(raw_key)
        if not notification_type:
            continue
        if not _can_access_notification(request.user, notification_type, object_id):
            continue

        state, _ = NotificationState.objects.get_or_create(
            user=request.user,
            notification_type=notification_type,
            object_id=object_id,
        )

        if action == 'read':
            if state.is_cleared:
                continue
            if not state.is_read:
                state.is_read = True
                state.save(update_fields=['is_read', 'updated_at'])
                updated_count += 1
            continue

        if not state.is_cleared or not state.is_read:
            state.is_cleared = True
            state.is_read = True
            state.save(update_fields=['is_cleared', 'is_read', 'updated_at'])
            updated_count += 1

    return JsonResponse({'success': True, 'updated': updated_count})

@csrf_exempt
def api_dashboard_stats(request):
    """
    API endpoint to get dashboard statistics
    """
    today = timezone.localdate()
    
    total_students = Student.objects.filter(is_active=True).count()
    present_today = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).values('student').distinct().count()
    
    failed_attempts = SystemLog.objects.filter(
        timestamp__date=today,
        log_type='warning',
        message__istartswith='Access denied:'
    ).count()
    
    recent = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).select_related('student').order_by('-timestamp')[:5]
    
    recent_list = []
    for entry in recent:
        recent_list.append({
            'name': entry.student.name if entry.student else 'Unknown',
            'time': entry.timestamp.strftime('%H:%M:%S'),
            'roll_number': entry.student.roll_number if entry.student else 'N/A'
        })
    
    return JsonResponse({
        'total_students': total_students,
        'present_today': present_today,
        'absent_today': total_students - present_today,
        'failed_attempts': failed_attempts,
        'recent_entries': recent_list,
    })