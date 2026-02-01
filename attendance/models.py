from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User  
import json

class Student(models.Model):
    """Model for registered students/staff"""
    
    USER_TYPE_CHOICES = [
        ('student', 'Student'),
        ('staff', 'Staff'),
        ('visitor', 'Visitor'),
    ]
    
    #  Link to Django User for login
    user = models.OneToOneField(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='student_profile'
    )
    
    name = models.CharField(max_length=100, verbose_name="Full Name")
    roll_number = models.CharField(max_length=50, unique=True, verbose_name="Roll Number/ID")
    email = models.EmailField(blank=True, null=True, verbose_name="Email Address")
    phone = models.CharField(max_length=15, blank=True, null=True, verbose_name="Phone Number")
    department = models.CharField(max_length=50, blank=True, null=True, verbose_name="Department")
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='student', verbose_name="User Type")
    
    # Face recognition data
    face_encoding = models.TextField(verbose_name="Face Encoding (JSON)")
    photo = models.ImageField(upload_to='faces/', blank=True, null=True, verbose_name="Profile Photo")
    
    # Status
    is_active = models.BooleanField(default=True, verbose_name="Active Status")
    registered_at = models.DateTimeField(default=timezone.now, verbose_name="Registration Date")
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Student/Staff'
        verbose_name_plural = 'Students/Staff'
    
    def __str__(self):
        return f"{self.name} ({self.roll_number})"
    
    def get_face_encodings(self):
        """Get face encodings as Python list"""
        try:
            return json.loads(self.face_encoding)
        except:
            return []


class Attendance(models.Model):
    """Model for attendance records"""
    
    ENTRY_TYPE_CHOICES = [
        ('success', 'Access Granted'),
        ('denied', 'Access Denied'),
    ]
    
    student = models.ForeignKey(
        Student, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='attendance_records',
        verbose_name="Student/Staff"
    )
    timestamp = models.DateTimeField(default=timezone.now, verbose_name="Date & Time")
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES, default='success', verbose_name="Entry Type")
    location = models.CharField(max_length=50, default='Main Door', verbose_name="Location")
    image_path = models.CharField(max_length=255, blank=True, null=True, verbose_name="Captured Image Path")
    confidence = models.FloatField(null=True, blank=True, verbose_name="Recognition Confidence")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'
    
    def __str__(self):
        if self.student:
            return f"{self.student.name} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
        return f"Unknown - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class SystemLog(models.Model):
    """Model for system logs and errors"""
    
    LOG_TYPE_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('success', 'Success'),
    ]
    
    timestamp = models.DateTimeField(default=timezone.now, verbose_name="Timestamp")
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, default='info', verbose_name="Log Type")
    message = models.TextField(verbose_name="Log Message")
    details = models.TextField(blank=True, null=True, verbose_name="Additional Details")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'System Log'
        verbose_name_plural = 'System Logs'
    
    def __str__(self):
        return f"[{self.log_type.upper()}] {self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.message[:50]}"