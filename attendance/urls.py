from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard (auto-routes to admin or user dashboard)
    path('', views.dashboard, name='dashboard'),
    
    # Student Management (Admin only)
    path('students/', views.student_list, name='student_list'),
    path('students/register/', views.register_student, name='register_student'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/delete/', views.delete_student, name='delete_student'),
    path('students/<int:pk>/toggle-status/', views.toggle_student_status, name='toggle_student_status'),
    
    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    
    # Reports (Admin only)
    path('reports/', views.reports, name='reports'),
    path('reports/generate/', views.generate_report, name='generate_report'),
    
    # System Logs (Admin only)
    path('logs/', views.system_logs, name='system_logs'),
    
    # API Endpoints
    path('api/capture-face/', views.capture_face_api, name='capture_face_api'),
    path('api/check-camera/', views.check_camera_api, name='check_camera_api'),
    path('api/dashboard-stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
]