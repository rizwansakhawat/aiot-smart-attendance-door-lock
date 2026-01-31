"""
Views for Smart Attendance System
=================================
Handles web pages and API endpoints for:
- Dashboard
- Student Registration
- Attendance Records
- Reports
"""

import json
import base64
import cv2
import numpy as np
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from .models import Student, Attendance, SystemLog
from .services.face_recognition_service import (
    get_face_recognition_service,
    USB_CAMERA_INDEX
)


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════

def dashboard(request):
    """
    Main dashboard view - shows today's attendance summary
    """
    today = timezone.now().date()
    
    # Get today's attendance
    today_attendance = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).select_related('student').order_by('-timestamp')
    
    # Get statistics
    total_students = Student.objects.filter(is_active=True).count()
    present_today = today_attendance.values('student').distinct().count()
    absent_today = total_students - present_today
    
    # Get recent failed attempts
    failed_attempts = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='denied'
    ).count()
    
    # Get last 10 entries
    recent_entries = today_attendance[:10]
    
    context = {
        'total_students': total_students,
        'present_today': present_today,
        'absent_today': absent_today,
        'failed_attempts': failed_attempts,
        'recent_entries': recent_entries,
        'today': today,
        'attendance_percentage': round((present_today / total_students * 100), 1) if total_students > 0 else 0,
    }
    
    return render(request, 'attendance/dashboard.html', context)


# ═══════════════════════════════════════════════════════════════════
# STUDENT REGISTRATION
# ═══════════════════════════════════════════════════════════════════

def register_student(request):
    """
    Student registration page - form to add new student
    """
    if request.method == 'POST':
        return handle_student_registration(request)
    
    # GET request - show registration form
    context = {
        'camera_index': USB_CAMERA_INDEX,
        'departments': [
            'Computer Science',
            'Electrical Engineering',
            'Mechanical Engineering',
            'Civil Engineering',
            'Electronics',
            'Software Engineering',
            'Information Technology',
            'Other'
        ],
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
    """
    try:
        # Get form data
        name = request.POST.get('name', '').strip()
        roll_number = request.POST.get('roll_number', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        department = request.POST.get('department', '').strip()
        user_type = request.POST.get('user_type', 'student')
        face_encodings_json = request.POST.get('face_encodings', '')
        
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
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('register_student')
        
        # Create student
        student = Student.objects.create(
            name=name,
            roll_number=roll_number,
            email=email if email else None,
            phone=phone if phone else None,
            department=department if department else None,
            user_type=user_type,
            face_encoding=face_encodings_json,
            is_active=True
        )
        
        # Refresh face recognition cache
        service = get_face_recognition_service()
        service.refresh_cache()
        
        # Log registration
        SystemLog.objects.create(
            log_type='success',
            message=f"New student registered: {name} ({roll_number})"
        )
        
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
    
    Receives: Base64 encoded image
    Returns: Face encoding if face detected, error otherwise
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
        
        if face_location is None:
            return JsonResponse({
                'success': False,
                'error': 'No face detected. Please position your face in the frame.'
            })
        
        # Check if face is valid (large enough)
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
        
        # Return success with encoding
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
        cap = cv2.VideoCapture(USB_CAMERA_INDEX)
        
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                return JsonResponse({
                    'success': True,
                    'camera_index': USB_CAMERA_INDEX,
                    'message': 'USB Camera is available'
                })
        
        return JsonResponse({
            'success': False,
            'error': 'Camera not available. Please check USB camera connection.'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


# ═══════════════════════════════════════════════════════════════════
# STUDENT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def student_list(request):
    """
    List all registered students
    """
    # Get filter parameters
    search = request.GET.get('search', '')
    department = request.GET.get('department', '')
    user_type = request.GET.get('user_type', '')
    status = request.GET.get('status', '')
    
    # Base queryset
    students = Student.objects.all().order_by('-registered_at')
    
    # Apply filters
    if search:
        students = students.filter(
            Q(name__icontains=search) |
            Q(roll_number__icontains=search) |
            Q(email__icontains=search)
        )
    
    if department:
        students = students.filter(department=department)
    
    if user_type:
        students = students.filter(user_type=user_type)
    
    if status:
        if status == 'active':
            students = students.filter(is_active=True)
        elif status == 'inactive':
            students = students.filter(is_active=False)
    
    # Pagination
    paginator = Paginator(students, 20)  # 20 students per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get unique departments for filter dropdown
    departments = Student.objects.values_list('department', flat=True).distinct()
    departments = [d for d in departments if d]
    
    context = {
        'page_obj': page_obj,
        'students': page_obj,
        'total_students': students.count(),
        'departments': departments,
        'search': search,
        'selected_department': department,
        'selected_user_type': user_type,
        'selected_status': status,
    }
    
    return render(request, 'attendance/student_list.html', context)


def student_detail(request, pk):
    """
    View student details and attendance history
    """
    student = get_object_or_404(Student, pk=pk)
    
    # Get attendance history
    attendance_records = Attendance.objects.filter(
        student=student
    ).order_by('-timestamp')[:50]
    
    # Calculate statistics
    total_days = attendance_records.values('timestamp__date').distinct().count()
    
    # Get attendance for last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_attendance = Attendance.objects.filter(
        student=student,
        timestamp__gte=thirty_days_ago,
        entry_type='success'
    ).values('timestamp__date').distinct().count()
    
    context = {
        'student': student,
        'attendance_records': attendance_records,
        'total_attendance_days': total_days,
        'recent_attendance': recent_attendance,
    }
    
    return render(request, 'attendance/student_detail.html', context)


def delete_student(request, pk):
    """
    Delete a student
    """
    student = get_object_or_404(Student, pk=pk)
    
    if request.method == 'POST':
        name = student.name
        student.delete()
        
        # Refresh face recognition cache
        service = get_face_recognition_service()
        service.refresh_cache()
        
        # Log deletion
        SystemLog.objects.create(
            log_type='warning',
            message=f"Student deleted: {name}"
        )
        
        messages.success(request, f"Student '{name}' has been deleted.")
        return redirect('student_list')
    
    return render(request, 'attendance/delete_student.html', {'student': student})


def toggle_student_status(request, pk):
    """
    Toggle student active/inactive status
    """
    student = get_object_or_404(Student, pk=pk)
    student.is_active = not student.is_active
    student.save()
    
    # Refresh face recognition cache
    service = get_face_recognition_service()
    service.refresh_cache()
    
    status = "activated" if student.is_active else "deactivated"
    messages.success(request, f"Student '{student.name}' has been {status}.")
    
    return redirect('student_list')


# ═══════════════════════════════════════════════════════════════════
# ATTENDANCE RECORDS
# ═══════════════════════════════════════════════════════════════════

def attendance_list(request):
    """
    View attendance records with filtering
    """
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    student_id = request.GET.get('student', '')
    entry_type = request.GET.get('entry_type', '')
    
    # Base queryset
    records = Attendance.objects.all().select_related('student').order_by('-timestamp')
    
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
    
    if student_id:
        records = records.filter(student_id=student_id)
    
    if entry_type:
        records = records.filter(entry_type=entry_type)
    
    # Pagination
    paginator = Paginator(records, 50)  # 50 records per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get students for filter dropdown
    students = Student.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'records': page_obj,
        'total_records': records.count(),
        'students': students,
        'date_from': date_from,
        'date_to': date_to,
        'selected_student': student_id,
        'selected_entry_type': entry_type,
    }
    
    return render(request, 'attendance/attendance_list.html', context)


# ═══════════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════════

def reports(request):
    """
    Reports page - generate various attendance reports
    """
    context = {
        'students': Student.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'attendance/reports.html', context)


def generate_report(request):
    """
    Generate attendance report based on parameters
    """
    if request.method != 'POST':
        return redirect('reports')
    
    report_type = request.POST.get('report_type', 'daily')
    date_from = request.POST.get('date_from', '')
    date_to = request.POST.get('date_to', '')
    student_id = request.POST.get('student', '')
    format_type = request.POST.get('format', 'html')
    
    # Build query
    records = Attendance.objects.filter(entry_type='success').select_related('student')
    
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
    
    records = records.order_by('-timestamp')
    
    # Generate summary
    summary = records.values('student__name', 'student__roll_number').annotate(
        total_days=Count('timestamp__date', distinct=True)
    ).order_by('student__name')
    
    context = {
        'records': records[:500],  # Limit to 500 records
        'summary': summary,
        'date_from': date_from,
        'date_to': date_to,
        'total_records': records.count(),
    }
    
    if format_type == 'excel':
        return generate_excel_report(records, summary)
    
    return render(request, 'attendance/report_result.html', context)


def generate_excel_report(request, records, summary):
    """
    Generate Excel report
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from django.http import HttpResponse
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"
        
        # Header styling
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        
        # Add headers
        headers = ['Sr.', 'Name', 'Roll Number', 'Date', 'Time', 'Status']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
        
        # Add data
        for row, record in enumerate(records[:1000], 2):  # Limit to 1000
            ws.cell(row=row, column=1, value=row-1)
            ws.cell(row=row, column=2, value=record.student.name if record.student else 'Unknown')
            ws.cell(row=row, column=3, value=record.student.roll_number if record.student else 'N/A')
            ws.cell(row=row, column=4, value=record.timestamp.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=5, value=record.timestamp.strftime('%H:%M:%S'))
            ws.cell(row=row, column=6, value='Present')
        
        # Adjust column widths
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 25
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 10
        ws.column_dimensions['F'].width = 10
        
        # Create response
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
# SYSTEM LOGS
# ═══════════════════════════════════════════════════════════════════

def system_logs(request):
    """
    View system logs
    """
    log_type = request.GET.get('type', '')
    
    logs = SystemLog.objects.all().order_by('-timestamp')
    
    if log_type:
        logs = logs.filter(log_type=log_type)
    
    # Pagination
    paginator = Paginator(logs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'logs': page_obj,
        'selected_type': log_type,
    }
    
    return render(request, 'attendance/system_logs.html', context)


# ═══════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@csrf_exempt
def api_dashboard_stats(request):
    """
    API endpoint to get dashboard statistics (for real-time updates)
    """
    today = timezone.now().date()
    
    total_students = Student.objects.filter(is_active=True).count()
    present_today = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).values('student').distinct().count()
    
    failed_attempts = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='denied'
    ).count()
    
    # Recent entries
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
