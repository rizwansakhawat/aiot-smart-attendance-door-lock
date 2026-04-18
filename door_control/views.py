import json
import os
import signal
import subprocess
import sys
import time
import cv2

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from attendance.models import SystemLog


DOOR_SYSTEM_MODES = {
    '1': 'Live View (Continuous recognition)',
    '2': 'Live Attendance (No Arduino)',
    '3': 'Live Door Lock (Camera + Arduino, no PIR)',
    '4': 'Full Mode (Arduino + Camera + PIR)',
}

DOOR_STATE_FILE = os.path.join(settings.BASE_DIR, 'media', 'runtime', 'door_system_state.json')
DOOR_FAILURE_FILE = os.path.join(settings.BASE_DIR, 'media', 'runtime', 'door_system_failure.json')
DOOR_LOG_FILE = os.path.join(settings.BASE_DIR, 'media', 'runtime', 'door_system.log')


def is_superuser_only(user):
    return user.is_superuser


def _ensure_runtime_dir():
    os.makedirs(os.path.dirname(DOOR_STATE_FILE), exist_ok=True)


def _read_door_state():
    if not os.path.exists(DOOR_STATE_FILE):
        return {}

    try:
        with open(DOOR_STATE_FILE, 'r', encoding='utf-8') as state_file:
            data = json.load(state_file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_door_state(state):
    _ensure_runtime_dir()
    with open(DOOR_STATE_FILE, 'w', encoding='utf-8') as state_file:
        json.dump(state, state_file, ensure_ascii=True, indent=2)


def _clear_door_state():
    if os.path.exists(DOOR_STATE_FILE):
        try:
            os.remove(DOOR_STATE_FILE)
        except Exception:
            pass


def _read_door_failure():
    if not os.path.exists(DOOR_FAILURE_FILE):
        return {}

    try:
        with open(DOOR_FAILURE_FILE, 'r', encoding='utf-8') as failure_file:
            data = json.load(failure_file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_door_failure(failure):
    _ensure_runtime_dir()
    with open(DOOR_FAILURE_FILE, 'w', encoding='utf-8') as failure_file:
        json.dump(failure, failure_file, ensure_ascii=True, indent=2)


def _clear_door_failure():
    if os.path.exists(DOOR_FAILURE_FILE):
        try:
            os.remove(DOOR_FAILURE_FILE)
        except Exception:
            pass


def _is_pid_running(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    if pid <= 0:
        return False

    if os.name == 'nt':
        try:
            check = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                capture_output=True,
                text=True,
                check=False,
            )
            output = (check.stdout or '').strip()
            if not output or output.lower().startswith('info:'):
                return False

            for line in output.splitlines():
                cleaned = line.strip().strip('"')
                if not cleaned:
                    continue
                parts = [part.strip().strip('"') for part in line.split(',')]
                if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) == pid:
                    return True
            return False
        except Exception:
            return False

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _door_status():
    state = _read_door_state()
    failure = _read_door_failure()
    pid = state.get('pid')
    running = _is_pid_running(pid)

    if state and not running:
        _clear_door_state()
        state = {}

    mode = state.get('mode')
    failed = bool(failure) and not running and not state
    return {
        'running': running,
        'failed': failed,
        'pid': state.get('pid'),
        'mode': mode,
        'mode_label': DOOR_SYSTEM_MODES.get(mode, 'Unknown mode'),
        'started_at': state.get('started_at'),
        'started_by': state.get('started_by'),
        'error_message': failure.get('message'),
        'error_mode': failure.get('mode'),
        'error_mode_label': DOOR_SYSTEM_MODES.get(failure.get('mode'), 'Unknown mode') if failure else None,
        'error_started_by': failure.get('started_by'),
        'error_occurred_at': failure.get('occurred_at'),
    }


def _start_door_system(mode, username):
    if mode not in DOOR_SYSTEM_MODES:
        return False, 'Invalid mode selected.'

    status = _door_status()
    if status['running']:
        return False, f"Door system already running in mode {status['mode']} (PID {status['pid']})."

    script_path = os.path.join(settings.BASE_DIR, 'door_system.py')
    if not os.path.exists(script_path):
        return False, 'door_system.py not found in project root.'

    _ensure_runtime_dir()
    process_env = os.environ.copy()
    process_env['PYTHONIOENCODING'] = 'utf-8'
    process_env['PYTHONUTF8'] = '1'

    with open(DOOR_LOG_FILE, 'a', encoding='utf-8') as log_file:
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            process = subprocess.Popen(
                [sys.executable, script_path, mode],
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
                cwd=settings.BASE_DIR,
                env=process_env,
            )
        else:
            process = subprocess.Popen(
                [sys.executable, script_path, mode],
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=settings.BASE_DIR,
                env=process_env,
            )

    # If process exits immediately, report failure instead of showing false running state.
    time.sleep(1.0)
    if process.poll() is not None:
        tail = ''
        try:
            with open(DOOR_LOG_FILE, 'r', encoding='utf-8') as log_file:
                lines = log_file.readlines()
                tail = ''.join(lines[-5:]).strip()
        except Exception:
            pass
        failure_message = f'Door system failed to start. Last log lines: {tail}' if tail else 'Door system failed to start. Check media/runtime/door_system.log.'
        _write_door_failure(
            {
                'mode': mode,
                'started_by': username,
                'occurred_at': timezone.now().isoformat(),
                'message': failure_message,
            }
        )
        if tail:
            return False, failure_message
        return False, failure_message

    _clear_door_failure()
    _write_door_state(
        {
            'pid': process.pid,
            'mode': mode,
            'started_by': username,
            'started_at': timezone.now().isoformat(),
        }
    )

    return True, f"Door system started in mode {mode} (PID {process.pid})."


def _stop_door_system():
    state = _read_door_state()
    pid = state.get('pid')

    if not _is_pid_running(pid):
        _clear_door_state()
        return False, 'Door system is not running.'

    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/T', '/F'],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            os.killpg(int(pid), signal.SIGTERM)
    except Exception as exc:
        return False, f'Failed to stop process: {exc}'

    _clear_door_state()
    _clear_door_failure()
    return True, f'Door system stopped (PID {pid}).'


@login_required(login_url='login')
@user_passes_test(is_superuser_only, login_url='dashboard')
def control_panel(request):
    context = {
        'is_admin': True,
        'door_system_modes': DOOR_SYSTEM_MODES,
        'door_system_status': _door_status(),
    }
    return render(request, 'door_control/control.html', context)


@login_required(login_url='login')
@user_passes_test(is_superuser_only, login_url='dashboard')
@require_http_methods(['POST'])
def control_action(request):
    action = request.POST.get('action', '').strip().lower()

    if action == 'start':
        mode = request.POST.get('mode', '5').strip()
        ok, msg = _start_door_system(mode, request.user.username)
    elif action == 'stop':
        ok, msg = _stop_door_system()
    else:
        ok, msg = False, 'Invalid action.'

    if ok:
        messages.success(request, msg)
        SystemLog.objects.create(log_type='info', message=f"Door system control: {msg}")
    else:
        messages.warning(request, msg)
        SystemLog.objects.create(log_type='warning', message=f"Door system control failed: {msg}")

    return redirect('door_control_panel')


def _camera_frame_generator(camera_index):
    """Yield JPEG frames as multipart stream for browser preview."""
    camera = None
    try:
        if os.name == 'nt':
            camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not camera.isOpened():
                camera.release()
                camera = cv2.VideoCapture(camera_index)
        else:
            camera = cv2.VideoCapture(camera_index)

        if not camera.isOpened():
            return

        camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(getattr(settings, 'CAMERA_WIDTH', 640)))
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(getattr(settings, 'CAMERA_HEIGHT', 480)))
        camera.set(cv2.CAP_PROP_FPS, int(getattr(settings, 'CAMERA_FPS', 24)))

        while True:
            ok, frame = camera.read()
            if not ok or frame is None:
                break

            frame = cv2.flip(frame, 1)
            encoded, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not encoded:
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n'
            )
            time.sleep(0.04)
    finally:
        if camera is not None:
            camera.release()


@login_required(login_url='login')
@user_passes_test(is_superuser_only, login_url='dashboard')
def camera_stream(request):
    """Live camera stream for in-browser preview on Door Control page."""
    try:
        camera_index = int(request.GET.get('camera', getattr(settings, 'CAMERA_INDEX', 0)))
    except (TypeError, ValueError):
        camera_index = int(getattr(settings, 'CAMERA_INDEX', 0))

    return StreamingHttpResponse(
        _camera_frame_generator(camera_index),
        content_type='multipart/x-mixed-replace; boundary=frame',
    )
