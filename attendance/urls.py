# attendance/urls.py
"""
URL Configuration for Attendance App
"""

from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Student Management
    path('students/', views.student_list, name='student_list'),
    path('students/register/', views.register_student, name='register_student'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/delete/', views.delete_student, name='delete_student'),
    path('students/<int:pk>/toggle-status/', views.toggle_student_status, name='toggle_student_status'),
    
    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    
    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/generate/', views.generate_report, name='generate_report'),
    
    # System Logs
    path('logs/', views.system_logs, name='system_logs'),
    
    # API Endpoints
    path('api/capture-face/', views.capture_face_api, name='capture_face_api'),
    path('api/check-camera/', views.check_camera_api, name='check_camera_api'),
    path('api/dashboard-stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
]