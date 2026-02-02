from django.contrib import admin
from django.utils.html import format_html
from .models import Student, Attendance, SystemLog, Department

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'status_badge', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    list_per_page = 20
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Department Information', {
            'fields': ('name', 'description')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at')
        }),
    )
    
    readonly_fields = ['created_at']
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">● Active</span>')
        return format_html('<span style="color: red;">● Inactive</span>')
    status_badge.short_description = 'Status'

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'roll_number', 'department', 'user_type', 'status_badge', 'registered_at']
    list_filter = ['user_type', 'department', 'is_active', 'registered_at']  #department__is_active
    search_fields = ['name', 'roll_number', 'email', 'phone']
    list_per_page = 20
    date_hierarchy = 'registered_at'
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('name', 'roll_number', 'email', 'phone')
        }),
        ('Academic/Work Information', {
            'fields': ('department', 'user_type')
        }),
        ('Face Recognition Data', {
            'fields': ('face_encoding', 'photo'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'registered_at')
        }),
    )
    
    readonly_fields = ['registered_at']
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">● Active</span>')
        return format_html('<span style="color: red;">● Inactive</span>')
    status_badge.short_description = 'Status'


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'date', 'time', 'entry_badge', 'location', 'confidence_display']
    list_filter = ['entry_type', 'location', 'timestamp']
    search_fields = ['student__name', 'student__roll_number']
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    readonly_fields = ['timestamp']
    
    def student_name(self, obj):
        return obj.student.name if obj.student else 'Unknown'
    student_name.short_description = 'Student/Staff'
    
    def date(self, obj):
        return obj.timestamp.strftime('%Y-%m-%d')
    date.short_description = 'Date'
    
    def time(self, obj):
        return obj.timestamp.strftime('%H:%M:%S')
    time.short_description = 'Time'
    
    def entry_badge(self, obj):
        if obj.entry_type == 'success':
            return format_html('<span style="color: white; background-color: green; padding: 3px 10px; border-radius: 3px;">✓ Granted</span>')
        return format_html('<span style="color: white; background-color: red; padding: 3px 10px; border-radius: 3px;">✗ Denied</span>')
    entry_badge.short_description = 'Access'
    
    def confidence_display(self, obj):
        if obj.confidence:
            percentage = (1 - obj.confidence) * 100
            return f"{percentage:.1f}%"
        return "N/A"
    confidence_display.short_description = 'Confidence'


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'log_badge', 'message_preview']
    list_filter = ['log_type', 'timestamp']
    search_fields = ['message', 'details']
    date_hierarchy = 'timestamp'
    list_per_page = 100
    
    readonly_fields = ['timestamp']
    
    def log_badge(self, obj):
        colors = {
            'info': '#17a2b8',
            'success': '#28a745',
            'warning': '#ffc107',
            'error': '#dc3545'
        }
        color = colors.get(obj.log_type, '#6c757d')
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.log_type.upper()
        )
    log_badge.short_description = 'Type'
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'
