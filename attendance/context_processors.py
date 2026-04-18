import re

from django.db.models import Q

from attendance.models import Attendance, NotificationState, SystemLog


def _normalize_media_url(raw_path):
    if not raw_path:
        return None

    path = str(raw_path).strip().replace('\\', '/')
    if not path:
        return None

    if path.startswith('http://') or path.startswith('https://'):
        return path

    if path.startswith('/media/'):
        return path

    media_marker = '/media/'
    marker_index = path.lower().find(media_marker)
    if marker_index >= 0:
        return path[marker_index:]

    if path.startswith('media/'):
        return f"/{path}"

    return None


def _humanize_alert_message(message):
    text = str(message or '').strip()
    if not text:
        return 'Security alert'

    failed_login_username = _extract_failed_login_username(text)
    if failed_login_username is not None:
        return f"Sign-in attempt failed for username '{failed_login_username}'."

    lowered = text.lower()

    if lowered.startswith('access denied: unknown face'):
        return 'Access denied because the face was not recognized.'

    if 'unknown person persisted' in lowered:
        seconds_match = re.search(r'(\d+)\s*s', lowered)
        seconds = seconds_match.group(1) if seconds_match else 'few'
        if ':' in text:
            source = text.split(':', 1)[0].strip()
            return f"Unknown person was detected continuously for {seconds} seconds during {source}."
        return f"Unknown person was detected continuously for {seconds} seconds."

    if 'pir motion detected but no known face was recognized' in lowered:
        return 'PIR motion detected, but no known face was recognized within the timeout window.'

    error_patterns = [
        (r'^attendance error:\s*(.+)$', 'Attendance processing failed: {detail}.'),
        (r'^registration failed:\s*(.+)$', 'Student registration failed: {detail}.'),
        (r'^camera failed:\s*(.+)$', 'Camera connection failed: {detail}.'),
        (r'^arduino failed:\s*(.+)$', 'Arduino communication failed: {detail}.'),
        (r'^face recognition failed:\s*(.+)$', 'Face recognition failed: {detail}.'),
        (r'^(.+?) disconnected$', '{detail} disconnected unexpectedly.'),
    ]
    for pattern, template in error_patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            detail = match.group(1).strip().rstrip('.')
            return template.format(detail=detail)

    # Final cleanup for unhandled messages.
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if cleaned and cleaned[-1] not in '.!?':
        cleaned = f"{cleaned}."
    return cleaned


def _extract_failed_login_username(message):
    """Extract username from failed-login log message when present."""
    text = str(message or '').strip()
    match = re.search(r'failed login attempt for username:\s*(.+)$', text, re.IGNORECASE)
    if not match:
        return None

    raw_username = match.group(1).strip().strip('"\'')
    return raw_username or None


def _is_student_visible_alert(message, user, student_profile):
    """Allow students to see only alerts explicitly tied to their account."""
    text = str(message or '').strip()
    if not text:
        return False

    failed_login_username = _extract_failed_login_username(text)
    if failed_login_username is not None:
        return failed_login_username.casefold() == (user.username or '').strip().casefold()

    # For non-login alerts, avoid partial username matches by using token boundaries.
    username = (user.username or '').strip()
    if username:
        pattern = rf'(?<![A-Za-z0-9_.-]){re.escape(username)}(?![A-Za-z0-9_.-])'
        if re.search(pattern, text, re.IGNORECASE):
            return True

    if student_profile and student_profile.name:
        return student_profile.name.casefold() in text.casefold()

    return False


def global_notifications(request):
    """Provide recent alerts and attendance entries to all templates."""
    if not request.user.is_authenticated:
        return {
            'recent_alerts': [],
            'recent_attendance_entries': [],
            'unread_alert_count': 0,
            'recent_entry_count': 0,
        }

    alerts_qs = SystemLog.objects.filter(log_type__in=['warning', 'error']).order_by('-timestamp')
    is_admin_user = request.user.is_staff or request.user.is_superuser
    student_profile = None

    if is_admin_user:
        attendance_qs = Attendance.objects.select_related('student').order_by('-timestamp')
    else:
        student_profile = getattr(request.user, 'student_profile', None)
        attendance_qs = Attendance.objects.select_related('student').filter(
            student__user=request.user
        ).order_by('-timestamp')

    if is_admin_user:
        alerts_for_user = list(alerts_qs)
    else:
        alerts_for_user = [
            alert for alert in alerts_qs
            if _is_student_visible_alert(alert.message, request.user, student_profile)
        ]

    alert_ids = [alert.id for alert in alerts_for_user]
    entry_ids = list(attendance_qs.values_list('id', flat=True))

    alert_state_map = {
        state.object_id: state
        for state in NotificationState.objects.filter(
            user=request.user,
            notification_type='alert',
            object_id__in=alert_ids,
        )
    }
    entry_state_map = {
        state.object_id: state
        for state in NotificationState.objects.filter(
            user=request.user,
            notification_type='entry',
            object_id__in=entry_ids,
        )
    }

    recent_alerts = []
    for alert in alerts_for_user:
        state = alert_state_map.get(alert.id)
        if state and state.is_cleared:
            continue

        recent_alerts.append({
            'id': alert.id,
            'message': alert.message,
            'display_message': _humanize_alert_message(alert.message),
            'timestamp': alert.timestamp,
            'image_url': _normalize_media_url(alert.details),
            'is_read': bool(state and state.is_read),
        })

    recent_attendance_entries = []
    for entry in attendance_qs:
        state = entry_state_map.get(entry.id)
        if state and state.is_cleared:
            continue

        recent_attendance_entries.append({
            'id': entry.id,
            'student_name': entry.student.name if entry.student else 'Unknown',
            'entry_type': entry.get_entry_type_display(),
            'timestamp': entry.timestamp,
            'location': entry.location,
            'image_url': _normalize_media_url(entry.image_path),
            'is_read': bool(state and state.is_read),
        })

    return {
        'recent_alerts': recent_alerts,
        'recent_attendance_entries': recent_attendance_entries,
        'unread_alert_count': len([item for item in recent_alerts if not item['is_read']]),
        'recent_entry_count': len([item for item in recent_attendance_entries if not item['is_read']]),
    }
