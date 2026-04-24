"""
═══════════════════════════════════════════════════════════════════
AIoT Smart Attendance & Door Lock System
Main Door Control Script - IMPROVED VERSION
═══════════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import threading
import json
import cv2
import numpy as np
import face_recognition
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════
# Django Setup
# ═══════════════════════════════════════════════════════════════════
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_attendance_project.settings')

import django
django.setup()

from django.utils import timezone
from django.conf import settings
from attendance.models import Student, Attendance, SystemLog
from attendance.services.face_recognition_service import FaceRecognitionService

# ═══════════════════════════════════════════════════════════════════
# Serial Import
# ═══════════════════════════════════════════════════════════════════
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("❌ PySerial not installed! Run: pip install pyserial")
    
# Notification Service
try:
    from attendance.services.notification_service import NotificationService
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    print("⚠️ Notification service not available")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
SERIAL_PORT = None
BAUD_RATE = 9600
CAMERA_INDEX = 0
RECOGNITION_TOLERANCE = float(getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.45))
MATCH_SEPARATION_MARGIN = float(getattr(settings, 'FACE_RECOGNITION_MIN_GAP', 0.04))
MIN_MATCH_CONFIDENCE = float(getattr(settings, 'FACE_RECOGNITION_MIN_CONFIDENCE', 0.58))
REQUIRED_CONFIRM_FRAMES = int(getattr(settings, 'FACE_RECOGNITION_CONFIRM_FRAMES', 2))
CONFIRM_WINDOW_SECONDS = float(getattr(settings, 'FACE_RECOGNITION_CONFIRM_WINDOW_SECONDS', 1.5))
RECOGNITION_ATTEMPTS = 3
CAPTURE_DELAY = 0.5
CAMERA_WIDTH = int(getattr(settings, 'CAMERA_WIDTH', 640))
CAMERA_HEIGHT = int(getattr(settings, 'CAMERA_HEIGHT', 480))
CAMERA_FPS = int(getattr(settings, 'CAMERA_FPS', 30))
CAMERA_BUFFER_SIZE = int(getattr(settings, 'CAMERA_BUFFER_SIZE', 1))
CAMERA_DROP_FRAMES = int(getattr(settings, 'CAMERA_DROP_FRAMES', 1))
CAMERA_WARMUP_FRAMES = int(getattr(settings, 'CAMERA_WARMUP_FRAMES', 6))

# Connection settings
CONNECTION_CHECK_INTERVAL = 3  # Check every 3 seconds
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_WAIT_TIME = 2  # Wait 2 seconds between attempts
FULL_MODE_RECOGNITION_INTERVAL = float(getattr(settings, 'FULL_MODE_RECOGNITION_INTERVAL', 0.4))
FULL_MODE_MOTION_TIMEOUT_SECONDS = float(getattr(settings, 'FULL_MODE_MOTION_TIMEOUT_SECONDS', 10))
FULL_MODE_ALERT_COOLDOWN_SECONDS = float(getattr(settings, 'FULL_MODE_ALERT_COOLDOWN_SECONDS', 30))
FULL_MODE_REPEAT_UNKNOWN_AFTER_SECONDS = float(getattr(settings, 'FULL_MODE_REPEAT_UNKNOWN_AFTER_SECONDS', 30))
FULL_MODE_UNKNOWN_PERSIST_GRACE_SECONDS = float(getattr(settings, 'FULL_MODE_UNKNOWN_PERSIST_GRACE_SECONDS', 2.0))
FULL_MODE_PERSON_COOLDOWN_SECONDS = float(getattr(settings, 'FULL_MODE_PERSON_COOLDOWN_SECONDS', 6))
LIVE_DOOR_UNLOCK_DURATION_SECONDS = float(getattr(settings, 'LIVE_DOOR_UNLOCK_DURATION_SECONDS', 6))
LIVE_DOOR_PERSON_COOLDOWN_SECONDS = float(getattr(settings, 'LIVE_DOOR_PERSON_COOLDOWN_SECONDS', 2))
LIVE_UNKNOWN_ALERT_SECONDS = float(getattr(settings, 'LIVE_UNKNOWN_ALERT_SECONDS', 5))
LIVE_UNKNOWN_ALERT_COOLDOWN_SECONDS = float(getattr(settings, 'LIVE_UNKNOWN_ALERT_COOLDOWN_SECONDS', 30))
LIVE_FALLBACK_MIN_INTERVAL_SECONDS = float(getattr(settings, 'LIVE_FALLBACK_MIN_INTERVAL_SECONDS', 2.5))
DOOR_COMMAND_FILE = os.path.join(PROJECT_DIR, 'media', 'runtime', 'door_system_command.json')


# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def find_arduino_port():
    """Auto-detect Arduino COM port"""
    if not SERIAL_AVAILABLE:
        return None
        
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        desc = port.description.lower()
        if 'arduino' in desc or 'ch340' in desc or 'usb serial' in desc:
            return port.device
    
    return None


def log_system(log_type, message, details=None):
    """Log to database and console"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{log_type.upper()}] {message}")
    try:
        SystemLog.objects.create(log_type=log_type, message=message, details=details)
    except:
        pass


def run_in_background(task_name, target, *args, **kwargs):
    """Run a potentially slow task on a daemon thread so UI loops remain responsive."""

    def _runner():
        try:
            target(*args, **kwargs)
        except Exception as e:
            print(f"   ⚠️ Background task failed ({task_name}): {e}")

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread


def consume_runtime_command():
    """Read and remove one pending runtime command sent from the control panel."""
    if not os.path.exists(DOOR_COMMAND_FILE):
        return None

    data = None
    try:
        with open(DOOR_COMMAND_FILE, 'r', encoding='utf-8') as command_file:
            raw = json.load(command_file)
        if isinstance(raw, dict):
            data = raw
    except Exception:
        data = None
    finally:
        try:
            os.remove(DOOR_COMMAND_FILE)
        except Exception:
            pass

    if not data:
        return None

    command = str(data.get('command') or '').strip().upper()
    if not command:
        return None

    return {
        'command': command,
        'requested_by': data.get('requested_by'),
    }


def build_unlock_command(student_name=None):
    """Build an Arduino UNLOCK command with an optional LCD-safe user name."""
    if not student_name:
        return "UNLOCK"

    cleaned = ''.join(ch for ch in str(student_name) if 32 <= ord(ch) <= 126)
    cleaned = cleaned.replace('|', ' ').replace(':', ' ').strip()

    if not cleaned:
        return "UNLOCK"

    # 16 characters keeps the LCD second line clean on 16x2 displays.
    return f"UNLOCK:{cleaned[:16]}"


def save_attendance(student, entry_type='success', location='Main Door'):
    """Save attendance record and send notifications"""
    try:
        today = timezone.now().date()
        existing = Attendance.objects.filter(
            student=student,
            timestamp__date=today,
            entry_type='success'
        ).exists()
        
        if existing:
            print(f"   ℹ️ {student.name} already marked today")
            return False
        
        # Save attendance
        attendance = Attendance.objects.create(
            student=student,
            entry_type=entry_type,
            location=location
        )
        
        log_system('success', f"Attendance saved: {student.name}")
        
        # Send notifications
        if NOTIFICATIONS_AVAILABLE:
            try:
                run_in_background(
                    'attendance notification',
                    NotificationService.notify_attendance,
                    student,
                    attendance.timestamp,
                )
            except Exception as e:
                print(f"   ⚠️ Notification error: {e}")
        
        return True
        
    except Exception as e:
        log_system('error', f"Attendance error: {e}")
        return False


def save_unknown_snapshot(frame, prefix='unknown'):
    """Save a frame for unknown-person alerts and return file path."""
    if frame is None:
        return None

    try:
        denied_dir = os.path.join(PROJECT_DIR, 'media', 'denied')
        os.makedirs(denied_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(denied_dir, f"{prefix}_{ts}.jpg")
        if cv2.imwrite(filepath, frame):
            return filepath
    except Exception as e:
        print(f"   ⚠️ Failed to save unknown snapshot: {e}")

    return None


def notify_unknown_alert(frame=None, reason='Unknown person detected'):
    """Log and send unknown-person alert notification with optional snapshot."""
    snapshot_path = save_unknown_snapshot(frame, prefix='unknown_live')
    log_system('warning', reason, details=snapshot_path)

    if NOTIFICATIONS_AVAILABLE:
        try:
            run_in_background(
                'unknown person alert',
                NotificationService.notify_unknown_person,
                snapshot_path,
            )
            return True
        except Exception as e:
            print(f"   ⚠️ Unknown alert notification failed: {e}")

    return False


def print_access_granted_block(student_name, confidence):
    """Print a consistent ACCESS GRANTED block in terminal logs."""
    print("\n  ╔════════════════════════════════════════════╗")
    print(f"  ║  ✅ ACCESS GRANTED: {student_name[:25].ljust(25)}║")
    print("  ╚════════════════════════════════════════════╝")
    print(f"  📊 Final Confidence: {confidence:.1%}")
    print()
    print("  ┌──────────────────────────────────────────┐")
    print("  │  ➡️  Sending UNLOCK command to Arduino   │")
    print("  │  🔓 DOOR UNLOCKED                        │")
    print("  └──────────────────────────────────────────┘")


def print_error_box(title, message):
    """Print error in a visible box"""
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║" + f"  ❌ {title}".ljust(60) + "║")
    print("╠" + "═" * 60 + "╣")
    
    # Split message into lines
    lines = message.split('\n')
    for line in lines:
        if len(line) > 58:
            words = line.split()
            current = ""
            for word in words:
                if len(current + " " + word) <= 58:
                    current += (" " + word if current else word)
                else:
                    print("║ " + current.ljust(58) + " ║")
                    current = word
            if current:
                print("║ " + current.ljust(58) + " ║")
        else:
            print("║ " + line.ljust(58) + " ║")
    
    print("╚" + "═" * 60 + "╝")
    print()


def print_success_box(title, message=""):
    """Print success message in a box"""
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║" + f"  ✅ {title}".ljust(60) + "║")
    if message:
        print("╠" + "═" * 60 + "╣")
        print("║ " + message.ljust(58) + " ║")
    print("╚" + "═" * 60 + "╝")
    print()


# ═══════════════════════════════════════════════════════════════════
# CONNECTION MANAGER
# ═══════════════════════════════════════════════════════════════════

class ConnectionManager:
    """Manage hardware connections"""
    
    def __init__(self):
        self.camera = None
        self.arduino = None
        self.camera_ok = False
        self.arduino_ok = False
    
    # ─────────────────────────────────────────────────────────────
    # CAMERA FUNCTIONS
    # ��────────────────────────────────────────────────────────────
    
    def connect_camera(self, index=0):
        """Connect to camera"""
        try:
            # Release old camera if exists
            if self.camera is not None:
                try:
                    self.camera.release()
                except:
                    pass
            
            # Open new connection
            if os.name == 'nt':
                self.camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if not self.camera.isOpened():
                    self.camera.release()
                    self.camera = cv2.VideoCapture(index)
            else:
                self.camera = cv2.VideoCapture(index)
            
            if not self.camera.isOpened():
                self.camera_ok = False
                return False, "Camera cannot be opened"

            # Tune capture settings for lower latency and smoother preview.
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            self.camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_BUFFER_SIZE)

            for _ in range(max(0, CAMERA_WARMUP_FRAMES)):
                self.camera.grab()
            
            # Test capture
            ret, frame = self.camera.read()
            if not ret or frame is None:
                self.camera_ok = False
                return False, "Camera opened but cannot capture"
            
            h, w = frame.shape[:2]
            current_fps = self.camera.get(cv2.CAP_PROP_FPS)
            self.camera_ok = True
            return True, f"Camera ready ({w}x{h} @ {current_fps:.0f} FPS)"
            
        except Exception as e:
            self.camera_ok = False
            return False, f"Camera error: {str(e)}"
    
    def check_camera(self):
        """Check if camera is still working"""
        if self.camera is None:
            self.camera_ok = False
            return False
        
        try:
            if not self.camera.isOpened():
                self.camera_ok = False
                return False
            
            # Use grab() for a lightweight health check without decoding a full frame.
            self.camera_ok = self.camera.grab()
            return self.camera_ok
        except:
            self.camera_ok = False
            return False
    
    def capture_frame(self):
        """Capture a frame from camera"""
        if not self.camera_ok:
            return None
        
        try:
            # Grab/retrieve and drop stale buffered frames to keep preview real-time.
            if not self.camera.grab():
                self.camera_ok = False
                return None

            for _ in range(max(0, CAMERA_DROP_FRAMES)):
                if not self.camera.grab():
                    break

            ret, frame = self.camera.retrieve()
            if not ret or frame is None:
                ret, frame = self.camera.read()

            if ret and frame is not None:
                return frame
            else:
                self.camera_ok = False
                return None
        except:
            self.camera_ok = False
            return None
    
    def release_camera(self):
        """Release camera"""
        if self.camera is not None:
            try:
                self.camera.release()
            except:
                pass
            self.camera = None
        self.camera_ok = False
    
    # ─────────────────────────────────────────────────────────────
    # ARDUINO FUNCTIONS
    # ─────────────────────────────────────────────────────────────
    
    def connect_arduino(self, port=None):
        """Connect to Arduino"""
        if not SERIAL_AVAILABLE:
            return False, "PySerial not installed"
        
        try:
            # Close old connection if exists
            if self.arduino is not None:
                try:
                    self.arduino.close()
                except:
                    pass
            
            # Find port
            if port is None:
                port = find_arduino_port()
            
            if port is None:
                self.arduino_ok = False
                return False, "Arduino not found. Connect via USB."
            
            # Connect
            self.arduino = serial.Serial(port, BAUD_RATE, timeout=1)
            time.sleep(2)  # Wait for Arduino reset
            
            # Clear any pending data
            self.arduino.reset_input_buffer()
            
            # Test connection
            self.arduino.write(b"PING\n")
            time.sleep(0.5)
            
            self.arduino_ok = True
            return True, f"Arduino connected on {port}"
            
        except Exception as e:
            self.arduino_ok = False
            return False, f"Arduino error: {str(e)}"
    
    def check_arduino(self):
        """Check if Arduino is still connected"""
        if self.arduino is None:
            self.arduino_ok = False
            return False
        
        try:
            if not self.arduino.is_open:
                self.arduino_ok = False
                return False
            
            # Try to write (will fail if disconnected)
            self.arduino.write(b"")
            self.arduino_ok = True
            return True
        except:
            self.arduino_ok = False
            return False
    
    def send_command(self, cmd):
        """Send command to Arduino"""
        if not self.arduino_ok or self.arduino is None:
            return False
        
        try:
            self.arduino.write(f"{cmd}\n".encode())
            return True
        except:
            self.arduino_ok = False
            return False
    
    def read_arduino(self):
        """Read line from Arduino (non-blocking)"""
        if not self.arduino_ok or self.arduino is None:
            return None
        
        try:
            if self.arduino.in_waiting > 0:
                line = self.arduino.readline().decode().strip()
                return line
        except:
            self.arduino_ok = False
        
        return None
    
    def close_arduino(self):
        """Close Arduino connection"""
        if self.arduino is not None:
            try:
                self.arduino.close()
            except:
                pass
            self.arduino = None
        self.arduino_ok = False
    
    # ─────────────────────────────────────────────────────────────
    # CLEANUP
    # ─────────────────────────────────────────────────────────────
    
    def cleanup(self):
        """Release all connections"""
        self.release_camera()
        self.close_arduino()
        cv2.destroyAllWindows()


# ═══════════════════════════════════════════════════════════════════
# DOOR SYSTEM CLASS
# ═══════════════════════════════════════════════════════════════════

class DoorSystem:
    def __init__(self, require_arduino=True):
        self.conn = ConnectionManager()
        self.face_service = None
        self.running = False
        self.require_arduino = require_arduino
        self.last_check_time = 0
        self.paused = False  # Pause when connection lost
        self.last_motion_alert_time = 0
    
    def initialize(self):
        """Initialize all components"""
        print("\n" + "═" * 62)
        print("║" + "  AIoT Smart Attendance & Door Lock System".ljust(60) + "║")
        print("═" * 62 + "\n")
        
        # ─────────────────────────────────────────────────────────
        # STEP 1: Connect Camera (REQUIRED)
        # ─────────────────────────────────────────────────────────
        print("📷 Connecting Camera...")
        
        ok, msg = self.conn.connect_camera(CAMERA_INDEX)
        
        if not ok:
            print_error_box("CAMERA NOT CONNECTED", msg + "\n\nPlease connect a USB camera and restart.")
            log_system('error', f'Camera failed: {msg}')
            return False
        
        print(f"   ✅ {msg}")
        
        # ─────────────────────────────────────────────────────────
        # STEP 2: Connect Arduino (if required)
        # ─────────────────────────────────────────────────────────
        if self.require_arduino:
            print("\n🔌 Connecting Arduino...")
            
            ok, msg = self.conn.connect_arduino()
            
            if not ok:
                print_error_box("ARDUINO NOT CONNECTED", msg + "\n\nPlease:\n1. Connect Arduino via USB\n2. Check COM port in Device Manager\n3. Restart the program")
                log_system('error', f'Arduino failed: {msg}')
                self.conn.cleanup()
                return False
            
            print(f"   ✅ {msg}")
        else:
            print("\n🔌 Arduino: Skipped (Simulation Mode)")
        
        # ─────────────────────────────────────────────────────────
        # STEP 3: Load Face Recognition
        # ─────────────────────────────────────────────────────────
        print("\n🤖 Loading Face Recognition...")
        
        try:
            self.face_service = FaceRecognitionService(
                tolerance=RECOGNITION_TOLERANCE,
                camera_index=CAMERA_INDEX
            )
            self.face_service.refresh_cache()
            
            total = Student.objects.filter(is_active=True).count()
            print(f"   ✅ Ready ({total} registered students)")
            
            if total == 0:
                print("   ⚠️ Warning: No students registered!")
                
        except Exception as e:
            print_error_box("FACE RECOGNITION FAILED", str(e))
            log_system('error', f'Face recognition failed: {e}')
            self.conn.cleanup()
            return False
        
        # ─────────────────────────────────────────────────────────
        # ALL OK
        # ─────────────────────────────────────────────────────────
        print_success_box("SYSTEM READY", "All components initialized successfully!")
        log_system('success', 'Door system started')
        return True
    
    def check_connections(self):
        """Check all connections and handle errors"""
        errors = []
        
        # Check camera
        if not self.conn.check_camera():
            errors.append("CAMERA")
        
        # Check Arduino
        if self.require_arduino and not self.conn.check_arduino():
            errors.append("ARDUINO")
        
        return errors
    
    def attempt_reconnect(self, device):
        """Attempt to reconnect a specific device"""
        print(f"\n🔄 Attempting to reconnect {device}...")
        
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            print(f"   Attempt {attempt + 1}/{MAX_RECONNECT_ATTEMPTS}...")
            
            if device == "CAMERA":
                ok, msg = self.conn.connect_camera(CAMERA_INDEX)
            elif device == "ARDUINO":
                ok, msg = self.conn.connect_arduino()
            else:
                return False
            
            if ok:
                print(f"   ✅ {device} reconnected!")
                log_system('success', f'{device} reconnected')
                return True
            
            print(f"   ❌ Failed: {msg}")
            time.sleep(RECONNECT_WAIT_TIME)
        
        print(f"   ❌ Could not reconnect {device} after {MAX_RECONNECT_ATTEMPTS} attempts")
        return False
    
    def recognize_face(self, frame):
        """Recognize face in frame"""
        if frame is None:
            return None, 0
        
        try:
            result = self.face_service.recognize_face(frame)
            
            if result['success']:
                return result['student'], result['confidence']
            return None, 0
            
        except Exception as e:
            print(f"   ❌ Recognition error: {e}")
            return None, 0

    def _save_motion_alert_snapshot(self, frame):
        """Save a snapshot for admin alerts and return the file path."""
        if frame is None:
            return None

        try:
            denied_dir = os.path.join(PROJECT_DIR, 'media', 'denied')
            os.makedirs(denied_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(denied_dir, f"motion_alert_{ts}.jpg")
            if cv2.imwrite(filepath, frame):
                return filepath
        except Exception as e:
            print(f"   ⚠️ Failed to save alert snapshot: {e}")

        return None

    def _send_motion_timeout_alert(self, frame, timeout_seconds):
        """Notify admin when motion was detected but no known face matched."""
        filepath = self._save_motion_alert_snapshot(frame)
        message = (
            f"PIR motion detected but no known face was recognized within "
            f"{timeout_seconds:.0f} seconds."
        )

        print_error_box("NO KNOWN FACE DETECTED", message)
        log_system('warning', message, details=filepath)

        if NOTIFICATIONS_AVAILABLE:
            try:
                run_in_background(
                    'full mode motion timeout alert',
                    NotificationService.notify_unknown_person,
                    filepath,
                )
            except Exception as e:
                print(f"   ⚠️ Admin alert failed: {e}")

        if self.require_arduino:
            self.conn.send_command("DENIED")

    def run_full_mode_live(self):
        """Full mode with continuous recognition and PIR-triggered unknown-person alerts."""
        if not self.initialize():
            print("\n❌ Cannot start - initialization failed!")
            return

        self.running = True
        self.last_check_time = time.time()
        self.last_motion_alert_time = 0

        print("\n" + "═" * 58)
        print("  🎥 FULL MODE - LIVE CAMERA + PIR")
        print("═" * 58)
        print(f"  • Motion timeout: {FULL_MODE_MOTION_TIMEOUT_SECONDS:.0f} seconds")
        print("  • Camera recognition runs continuously")
        print("  • PIR starts unknown-face timeout window")
        print("  • Known face = gate unlocks immediately")
        print("  • PIR window timeout with no known face = admin alert")
        print("═" * 58 + "\n")

        cv2.namedWindow('Full Mode', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Full Mode', 1000, 750)

        pir_window_active = False
        motion_deadline = 0
        recognition_votes = {}
        recent_unlocks = {}
        last_recognition_time = 0
        detected_faces = []
        first_timeout_alert_sent = False
        unknown_visible_since = 0
        unknown_last_seen_time = 0
        detection_scale = float(getattr(settings, 'LIVE_DETECTION_SCALE', 0.5))
        detection_upsample = int(getattr(settings, 'LIVE_DETECTION_UPSAMPLE', 1))
        last_result_text = "Continuous scanning active..."
        last_result_color = (180, 180, 180)
        result_time = 0
        status_messages = []
        status_time = 0

        try:
            while self.running:
                current_time = time.time()

                # Keep hardware connection checks active while the camera is live.
                if current_time - self.last_check_time >= CONNECTION_CHECK_INTERVAL:
                    errors = self.check_connections()

                    if errors:
                        self.paused = True

                        for device in errors:
                            print_error_box(f"{device} DISCONNECTED", f"{device} connection lost!\n\nAttempting to reconnect...")
                            log_system('error', f'{device} disconnected')

                            if not self.attempt_reconnect(device):
                                print_error_box("RECONNECTION FAILED", f"Cannot reconnect {device}.\n\nPlease check the connection and restart.")
                                self.running = False
                                break

                        if self.running:
                            self.paused = False
                            print("\n🎯 System resumed. Waiting for motion...\n")

                    self.last_check_time = current_time

                if self.paused:
                    time.sleep(0.1)
                    continue

                pending = consume_runtime_command()
                if pending and pending.get('command') == 'OPEN_DOOR':
                    requested_by = pending.get('requested_by') or 'admin'
                    if self.conn.arduino_ok:
                        self.conn.send_command(build_unlock_command('Manual Open'))
                        message = f"Manual open executed in Full Mode by {requested_by}."
                        print(f"\n🔓 {message}")
                        log_system('info', message)
                    else:
                        message = f"Manual open request ignored (Arduino offline) by {requested_by}."
                        print(f"\n⚠️ {message}")
                        log_system('warning', message)

                if self.require_arduino:
                    msg = self.conn.read_arduino()
                    if msg and "MOTION" in msg:
                        recognition_votes = {}
                        pir_window_active = True
                        first_timeout_alert_sent = False
                        unknown_visible_since = 0
                        unknown_last_seen_time = 0
                        motion_deadline = current_time + FULL_MODE_MOTION_TIMEOUT_SECONDS
                        print("\n📡 [ARDUINO] 🚶 PIR Motion Detected!")
                        status_messages = [f"🚶 Motion detected - awaiting known face for {FULL_MODE_MOTION_TIMEOUT_SECONDS:.0f}s"]
                        status_time = current_time

                frame = self.conn.capture_frame()

                if frame is None:
                    error_img = np.zeros((500, 800, 3), dtype=np.uint8)
                    cv2.putText(error_img, "CAMERA DISCONNECTED",
                               (200, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
                    cv2.imshow('Full Mode', error_img)
                    if cv2.waitKey(500) & 0xFF == ord('q'):
                        self.running = False
                    continue

                frame = cv2.flip(frame, 1)
                display = frame.copy()
                h, w = display.shape[:2]

                if current_time - last_recognition_time >= FULL_MODE_RECOGNITION_INTERVAL:
                    detected_faces = []
                    student = None
                    confidence = 0

                    try:
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        small_frame = cv2.resize(rgb_frame, (0, 0), fx=detection_scale, fy=detection_scale)
                        scale_back = 1.0 / detection_scale

                        face_locations = face_recognition.face_locations(
                            small_frame,
                            model='hog',
                            number_of_times_to_upsample=detection_upsample
                        )

                        if face_locations:
                            face_encodings = face_recognition.face_encodings(small_frame, face_locations)

                            best_student = None
                            best_confidence = 0

                            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                                top = int(top * scale_back)
                                right = int(right * scale_back)
                                bottom = int(bottom * scale_back)
                                left = int(left * scale_back)

                                face_name = "Unknown"
                                face_color = (0, 0, 255)
                                face_conf = 0

                                if self.face_service.known_face_encodings:
                                    distances = face_recognition.face_distance(
                                        self.face_service.known_face_encodings,
                                        face_encoding
                                    )

                                    if len(distances) > 0:
                                        best_idx = int(np.argmin(distances))
                                        best_distance = float(distances[best_idx])
                                        sorted_distances = np.sort(distances)
                                        second_best = float(sorted_distances[1]) if len(sorted_distances) > 1 else 1.0
                                        distance_gap = second_best - best_distance
                                        is_separated = len(sorted_distances) == 1 or distance_gap >= MATCH_SEPARATION_MARGIN

                                        if best_distance <= RECOGNITION_TOLERANCE and is_separated:
                                            candidate = self.face_service.known_students[best_idx]
                                            candidate_conf = 1 - best_distance
                                            face_name = candidate.name
                                            face_conf = candidate_conf

                                            if candidate_conf >= MIN_MATCH_CONFIDENCE:
                                                face_color = (0, 255, 0)
                                            else:
                                                face_color = (0, 165, 255)

                                            if candidate_conf >= MIN_MATCH_CONFIDENCE and candidate_conf > best_confidence:
                                                best_student = candidate
                                                best_confidence = candidate_conf

                                detected_faces.append({
                                    'name': face_name,
                                    'location': (top, right, bottom, left),
                                    'color': face_color,
                                    'confidence': face_conf,
                                })

                            student = best_student
                            confidence = best_confidence

                    except Exception as e:
                        print(f"  ❌ Full Mode detect error: {e}")

                    if student:
                        last_unlock = recent_unlocks.get(student.id, 0)
                        if current_time - last_unlock < FULL_MODE_PERSON_COOLDOWN_SECONDS:
                            remaining = int(FULL_MODE_PERSON_COOLDOWN_SECONDS - (current_time - last_unlock))
                            status_messages = [f"⏳ {student.name} cooldown ({remaining}s)"]
                            status_time = current_time
                            last_recognition_time = current_time
                            continue

                        votes = recognition_votes.get(student.id, 0) + 1
                        recognition_votes[student.id] = votes
                        print(f"  ✅ Recognized: {student.name}")
                        print(f"  📊 Confidence: {confidence:.1%}")
                        print(f"  🔎 Confirmation: {votes}/{REQUIRED_CONFIRM_FRAMES}")

                        if votes >= REQUIRED_CONFIRM_FRAMES:
                            print_access_granted_block(student.name, confidence)
                            self.conn.send_command(build_unlock_command(student.name))
                            save_attendance(student)
                            recent_unlocks[student.id] = current_time

                            last_result_text = f"ACCESS GRANTED: {student.name}"
                            last_result_color = (0, 200, 0)
                            result_time = current_time
                            pir_window_active = False
                            first_timeout_alert_sent = False
                            unknown_visible_since = 0
                            unknown_last_seen_time = 0
                            motion_deadline = 0
                            recognition_votes = {}
                            status_messages = [f"✅ ACCESS GRANTED: {student.name}"]
                            status_time = current_time
                    else:
                        if pir_window_active:
                            print("  ❌ Face not recognized")

                    if pir_window_active:
                        # Treat any visible-but-unverified face as unknown persistence.
                        unverified_face_visible = bool(detected_faces) and student is None
                        if unverified_face_visible:
                            if unknown_visible_since <= 0:
                                unknown_visible_since = current_time
                            unknown_last_seen_time = current_time
                        else:
                            if (
                                unknown_last_seen_time > 0 and
                                (current_time - unknown_last_seen_time) > FULL_MODE_UNKNOWN_PERSIST_GRACE_SECONDS
                            ):
                                unknown_visible_since = 0
                                unknown_last_seen_time = 0

                    last_recognition_time = current_time

                if pir_window_active and current_time >= motion_deadline:
                    if not first_timeout_alert_sent:
                        self._send_motion_timeout_alert(frame, FULL_MODE_MOTION_TIMEOUT_SECONDS)
                        self.last_motion_alert_time = current_time
                        first_timeout_alert_sent = True
                        last_result_text = "ADMIN ALERT SENT"
                        last_result_color = (0, 0, 220)
                        result_time = current_time
                        status_messages = ["⚠️ No known face detected - admin alerted"]
                        status_time = current_time

                        # Start repeat timing after the first timeout alert.
                        if unknown_visible_since <= 0:
                            unknown_visible_since = current_time
                        unknown_last_seen_time = current_time
                    else:
                        unknown_persisted = (
                            unknown_visible_since > 0 and
                            (current_time - unknown_visible_since) >= FULL_MODE_REPEAT_UNKNOWN_AFTER_SECONDS
                        )
                        cooldown_ready = (current_time - self.last_motion_alert_time) >= FULL_MODE_ALERT_COOLDOWN_SECONDS

                        if unknown_persisted and cooldown_ready:
                            self._send_motion_timeout_alert(frame, FULL_MODE_REPEAT_UNKNOWN_AFTER_SECONDS)
                            self.last_motion_alert_time = current_time
                            last_result_text = "REPEAT ADMIN ALERT SENT"
                            last_result_color = (0, 0, 220)
                            result_time = current_time
                            status_messages = ["⚠️ Unknown persists - repeat alert sent"]
                            status_time = current_time
                        elif unknown_persisted:
                            status_messages = ["ℹ️ Unknown persists - repeat alert cooldown active"]
                            status_time = current_time
                        else:
                            wait_left = int(max(0, FULL_MODE_REPEAT_UNKNOWN_AFTER_SECONDS - (current_time - unknown_visible_since))) if unknown_visible_since > 0 else int(FULL_MODE_REPEAT_UNKNOWN_AFTER_SECONDS)
                            status_messages = [f"ℹ️ Unknown must persist {wait_left}s more for repeat alert"]
                            status_time = current_time

                cv2.rectangle(display, (0, 0), (w, 90), (35, 35, 35), -1)
                cv2.putText(display, "FULL MODE - LIVE CAMERA + PIR",
                           (15, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 0), 2)

                mode_text = "Continuous face scan active"
                if pir_window_active:
                    remaining = max(0, int(motion_deadline - current_time))
                    mode_text = f"PIR active |timeout {remaining}sec|"
                cv2.putText(display, mode_text,
                           (15, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

                for face in detected_faces:
                    top, right, bottom, left = face['location']
                    color = face['color']
                    name = face['name']
                    conf = face.get('confidence', 0)

                    cv2.rectangle(display, (left, top), (right, bottom), color, 2)

                    label = name
                    if conf > 0:
                        label += f" ({conf:.0%})"

                    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
                    cv2.rectangle(
                        display,
                        (left, bottom),
                        (left + text_size[0] + 10, bottom + text_size[1] + 12),
                        color,
                        -1,
                    )
                    cv2.putText(
                        display,
                        label,
                        (left + 5, bottom + text_size[1] + 4),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 255),
                        2,
                    )

                if last_result_text and (current_time - result_time < 3):
                    cv2.rectangle(display, (0, h - 55), (w, h), last_result_color, -1)
                    cv2.putText(display, last_result_text,
                               (15, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                elif status_messages and (current_time - status_time < 3):
                    cv2.rectangle(display, (0, h - 55), (w, h), (50, 50, 50), -1)
                    cv2.putText(display, status_messages[-1],
                               (15, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 1)
                else:
                    cv2.rectangle(display, (0, h - 45), (w, h), (50, 50, 50), -1)
                    cv2.putText(display, "| R = Refresh |Q = Quit",
                               (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)

                cv2.imshow('Full Mode', display)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    self.running = False
                elif key == ord('r') or key == ord('R'):
                    print("\n🔄 Refreshing face database...")
                    try:
                        self.face_service.refresh_cache()
                        total = Student.objects.filter(is_active=True).count()
                        print(f"   ✅ Reloaded {total} students")
                        status_messages = [f"🔄 Refreshed: {total} students"]
                        status_time = current_time
                    except Exception as e:
                        print(f"   ❌ Refresh failed: {e}")
                        status_messages = ["❌ Refresh failed"]
                        status_time = current_time

        except KeyboardInterrupt:
            print("\n\n🛑 Stopping system...")

        finally:
            self.cleanup()
    
    def handle_motion(self):
        """Handle motion detection event"""
        # Check camera before processing
        if not self.conn.camera_ok:
            print("\n⚠️ Cannot process motion - camera disconnected!")
            return
        
        print("\n" + "━" * 50)
        print("  🚶 MOTION DETECTED")
        print("━" * 50)
        
        recognized_student = None
        recognized_confidence = 0
        recognition_votes = {}
        last_frame = None
        
        for attempt in range(RECOGNITION_ATTEMPTS):
            print(f"\n  📸 Capturing... (Attempt {attempt + 1}/{RECOGNITION_ATTEMPTS})")
            
            # Check camera again
            if not self.conn.camera_ok:
                print("  ❌ Camera disconnected during capture!")
                break
            
            # Capture frame
            frame = self.conn.capture_frame()
            
            if frame is None:
                print("  ❌ Capture failed!")
                break
            
            last_frame = frame
            
            # Recognize
            student, confidence = self.recognize_face(frame)
            
            if student:
                votes = recognition_votes.get(student.id, 0) + 1
                recognition_votes[student.id] = votes
                print(f"  ✅ Recognized: {student.name}")
                print(f"  📊 Confidence: {confidence:.1%}")
                print(f"  🔎 Confirmation: {votes}/{REQUIRED_CONFIRM_FRAMES}")

                if votes >= REQUIRED_CONFIRM_FRAMES:
                    recognized_student = student
                    recognized_confidence = confidence
                    break
            else:
                print("  ❌ Face not recognized")
            
            time.sleep(CAPTURE_DELAY)
        
        # Process result
        print()
        if recognized_student:
            print_access_granted_block(recognized_student.name, recognized_confidence)
            self.conn.send_command(build_unlock_command(recognized_student.name))
            print()
            save_attendance(recognized_student)
        else:
            print("  ╔════════════════════════════════════════════╗")
            print("  ║  ❌ ACCESS DENIED: Unknown Person          ║")
            print("  ╚════════════════════════════════════════════╝")
            print()
            print("  ┌──────────────────────────────────────────┐")
            print("  │  ➡️  Sending DENIED command to Arduino   │")
            print("  │  🔒 DOOR REMAINS LOCKED                  │")
            print("  └──────────────────────────────────────────┘")
            self.conn.send_command("DENIED")
            print("  🔒 Door remains LOCKED")
            log_system('warning', 'Access denied: Unknown face')
            
            # Save denied image
            if last_frame is not None:
                try:
                    denied_dir = os.path.join(PROJECT_DIR, 'media', 'denied')
                    os.makedirs(denied_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(denied_dir, f"denied_{ts}.jpg")
                    cv2.imwrite(filepath, last_frame)
                except:
                    pass
            # After saving denied image, add:
            if NOTIFICATIONS_AVAILABLE and frame is not None:
                try:
                    NotificationService.notify_unknown_person(filepath)
                except:
                    pass
        
        print("━" * 50 + "\n")
    
    def run(self):
        """Main loop"""
        if not self.initialize():
            print("\n❌ Cannot start - initialization failed!")
            return
        
        self.running = True
        self.last_check_time = time.time()
        
        print("\n🎯 System running. Waiting for motion...")
        print("   Press Ctrl+C to stop\n")
        
        try:
            while self.running:
                current_time = time.time()
                
                # ─────────────────────────────────────────────────
                # PERIODIC CONNECTION CHECK
                # ─────────────────────────────────────────────────
                if current_time - self.last_check_time >= CONNECTION_CHECK_INTERVAL:
                    errors = self.check_connections()
                    
                    if errors:
                        self.paused = True
                        
                        for device in errors:
                            print_error_box(f"{device} DISCONNECTED", f"{device} connection lost!\n\nAttempting to reconnect...")
                            log_system('error', f'{device} disconnected')
                            
                            if not self.attempt_reconnect(device):
                                print_error_box("RECONNECTION FAILED", f"Cannot reconnect {device}.\n\nPlease check the connection and restart.")
                                self.running = False
                                break
                        
                        if self.running:
                            self.paused = False
                            print("\n🎯 System resumed. Waiting for motion...\n")
                    
                    self.last_check_time = current_time
                
                # ─────────────────────────────────────────────────
                # SKIP IF PAUSED (connection issues)
                # ─────────────────────────────────────────────────
                if self.paused:
                    time.sleep(0.5)
                    continue
                
                # ─────────────────────────────────────────────────
                # READ ARDUINO
                # ─────────────────────────────────────────────────
                if self.require_arduino:
                    msg = self.conn.read_arduino()
                    
                    if msg:
                        # Print Arduino actions
                        if "MOTION" in msg:
                            print(f"\n📡 [ARDUINO] 🚶 PIR Motion Detected!")
                            self.handle_motion()
                            print("🎯 Waiting for motion...\n")
                        elif "DOOR_UNLOCKED" in msg or "unlocked" in msg.lower():
                            pass  # Already printed in handle_motion()
                        elif "DOOR_LOCKED" in msg or "locked" in msg.lower():
                            pass  # Already printed in handle_motion()
                        elif "SERVO" in msg:
                            print(f"📡 [ARDUINO] ⚙️ {msg}")
                        elif "BUZZER" in msg or "beep" in msg.lower():
                            print(f"📡 [ARDUINO] 🔊 {msg}")
                        elif "LED" in msg:
                            print(f"📡 [ARDUINO] 💡 {msg}")
                        elif "ERROR" in msg:
                            print(f"📡 [ARDUINO] ❌ {msg}")
                        elif "STATUS" in msg or "READY" in msg:
                            print(f"📡 [ARDUINO] ✅ {msg}")
                        elif "PONG" in msg or "OK" in msg:
                            pass  # Ignore ping responses
                        else:
                            print(f"📡 [ARDUINO] {msg}")
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping system...")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        print("\n🧹 Cleaning up...")
        
        if self.require_arduino and self.conn.arduino_ok:
            print("   ➡️  Sending LOCK command to Arduino...")
            self.conn.send_command("LOCK")
            print("   🔒 Door LOCKED")
        
        self.conn.cleanup()
        print("   ✅ Connections closed")
        
        log_system('info', 'Door system stopped')
        print("\n👋 Goodbye!\n")


# ═══════════════════════════════════════════════════════════════════
# LIVE VIEW
# ═══════════════════════════════════════════════════════════════════

def live_view():
    """Continuous live recognition"""
    print("\n" + "═" * 50)
    print("  🔴 LIVE VIEW MODE")
    print("═" * 50 + "\n")
    
    conn = ConnectionManager()
    
    print("📷 Connecting camera...")
    ok, msg = conn.connect_camera(CAMERA_INDEX)
    if not ok:
        print_error_box("CAMERA ERROR", msg)
        return
    print(f"   ✅ {msg}")
    
    print("\n🤖 Loading...")
    try:
        service = FaceRecognitionService(tolerance=RECOGNITION_TOLERANCE, camera_index=CAMERA_INDEX)
        service.refresh_cache()
        print("   ✅ Ready")
    except Exception as e:
        print_error_box("ERROR", str(e))
        conn.cleanup()
        return
    
    print("\n   Press Q to quit\n")
    
    cv2.namedWindow('Live View', cv2.WINDOW_NORMAL)
    
    last_time = 0
    interval = 0.8
    current_text = "Scanning..."
    current_color = (200, 200, 200)
    
    try:
        while True:
            frame = conn.capture_frame()
            
            if frame is None:
                continue
            
            frame = cv2.flip(frame, 1)
            display = frame.copy()
            
            # Recognize periodically
            now = time.time()
            if now - last_time >= interval:
                try:
                    result = service.recognize_face(frame)
                    if result['success']:
                        name = result['student'].name
                        conf = result['confidence']
                        current_text = f"{name} ({conf:.0%})"
                        current_color = (0, 220, 0)
                    else:
                        current_text = "Unknown"
                        current_color = (0, 0, 220)
                except:
                    current_text = "Error"
                    current_color = (0, 0, 220)
                last_time = now
            
            # Draw
            cv2.rectangle(display, (0, 0), (display.shape[1], 55), (0, 0, 0), -1)
            cv2.putText(display, current_text, (15, 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.1, current_color, 2)
            
            cv2.imshow('Live View', display)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    finally:
        conn.cleanup()
        print("\n👋 Done!")
        

# ═══════════════════════════════════════════════════════════════════
# LIVE CAMERA ATTENDANCE - MULTI USER (No Arduino - Auto Attendance)
# ═══════════════════════════════════════════════════════════════════

def live_camera_attendance():
    """
    Live Camera Attendance Mode - MULTI USER
    - No Arduino required
    - Detects MULTIPLE faces at once
    - Automatically marks attendance for all recognized persons
    - Individual cooldown per person
    """
    print("\n" + "═" * 58)
    print("  📷 LIVE CAMERA ATTENDANCE - MULTI USER MODE")
    print("═" * 58)
    print("  • No Arduino required")
    print("  • Detects MULTIPLE faces at once")
    print("  • Auto marks attendance for all recognized")
    print("  • 30 second cooldown per person")
    print("═" * 58 + "\n")
    
    # ─────────────────────────────────────────────────────────────
    # SETTINGS
    # ─────────────────────────────────────────────────────────────
    RECOGNITION_INTERVAL = 0.5      # Check every 0.5 seconds (faster for multi)
    ATTENDANCE_COOLDOWN = 30        # 30 seconds before same person can mark again
    MIN_CONFIDENCE = MIN_MATCH_CONFIDENCE  # Minimum confidence for attendance
    DETECTION_SCALE = float(getattr(settings, 'LIVE_DETECTION_SCALE', 0.5))
    DETECTION_UPSAMPLE = int(getattr(settings, 'LIVE_DETECTION_UPSAMPLE', 1))
    FALLBACK_DETECTION_SCALE = float(getattr(settings, 'LIVE_DETECTION_FALLBACK_SCALE', 0.8))
    FALLBACK_DETECTION_UPSAMPLE = int(getattr(settings, 'LIVE_DETECTION_FALLBACK_UPSAMPLE', 1))
    
    # Track recent attendance to prevent duplicates
    recent_attendance = {}  # {student_id: last_time}
    recent_confirms = {}    # {student_id: (count, last_seen_time)}
    
    conn = ConnectionManager()
    
    # ─────────────────────────────────────────────────────────────
    # Initialize Camera
    # ─────────────────────────────────────────────────────────────
    print("📷 Connecting camera...")
    ok, msg = conn.connect_camera(CAMERA_INDEX)
    if not ok:
        print_error_box("CAMERA NOT CONNECTED", msg + "\n\nPlease connect a USB camera.")
        return
    print(f"   ✅ {msg}")
    
    # ─────────────────────────────────────────────────────────────
    # Initialize Face Recognition
    # ─────────────────────────────────────────────────────────────
    print("\n🤖 Loading Face Recognition...")
    try:
        service = FaceRecognitionService(tolerance=RECOGNITION_TOLERANCE, camera_index=CAMERA_INDEX)
        service.refresh_cache()
        
        total = Student.objects.filter(is_active=True).count()
        print(f"   ✅ Ready ({total} registered students)")
        
        if total == 0:
            print_error_box("NO STUDENTS", "No students registered!\n\nPlease register students first.")
            conn.cleanup()
            return
            
    except Exception as e:
        print_error_box("FACE RECOGNITION ERROR", str(e))
        conn.cleanup()
        return
    
    # ─────────────────────────────────────────────────────────────
    # Get today's attendance count
    # ─────────────────────────────────────────────────────────────
    today = timezone.now().date()
    today_count = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).values('student').distinct().count()
    
    print(f"\n📊 Today's attendance: {today_count}/{total} students")
    
    # ─────────────────────────────────────────────────────────────
    # Start Live Attendance
    # ─────────────────────────────────────────────────────────────
    print("\n" + "═" * 58)
    print("  ✅ SYSTEM STARTED - MULTI USER MODE")
    print("  ─────────────────────────────────────────────────────")
    print("  • Multiple people can look at camera together")
    print("  • All recognized faces will be marked")
    print("  • Green box = Recognized")
    print("  • Red box = Unknown")
    print("  • Press R to refresh | Q to quit")
    print("═" * 58 + "\n")
    
    log_system('success', 'Live camera attendance (multi-user) started')
    
    cv2.namedWindow('Live Attendance - Multi User', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Live Attendance - Multi User', 1000, 750)
    
    last_recognition_time = 0
    detected_faces = []  # List of (name, location, color, status)
    
    # Stats
    session_marked = 0
    session_start = time.time()
    last_connection_check = time.time()
    unknown_start_time = None
    last_unknown_alert_time = 0
    last_unknown_frame = None
    last_fallback_detection_time = 0
    unauthorized_active = False
    
    # Status messages (shown at bottom)
    status_messages = []
    status_time = 0
    
    try:
        while True:
            current_time = time.time()
            
            # ─────────────────────────────────────────────────
            # Check camera connection periodically
            # ─────────────────────────────────────────────────
            if current_time - last_connection_check >= CONNECTION_CHECK_INTERVAL:
                if not conn.check_camera():
                    print_error_box("CAMERA DISCONNECTED", "Camera connection lost!")
                    
                    for attempt in range(MAX_RECONNECT_ATTEMPTS):
                        print(f"   Reconnecting... ({attempt + 1}/{MAX_RECONNECT_ATTEMPTS})")
                        ok, _ = conn.connect_camera(CAMERA_INDEX)
                        if ok:
                            print("   ✅ Camera reconnected!")
                            cv2.namedWindow('Live Attendance - Multi User', cv2.WINDOW_NORMAL)
                            break
                        time.sleep(RECONNECT_WAIT_TIME)
                    else:
                        print("   ❌ Could not reconnect. Exiting...")
                        break
                
                last_connection_check = current_time
            
            # ─────────────────────────────────────────────────
            # Capture frame
            # ─────────────────────────────────────────────────
            frame = conn.capture_frame()
            
            if frame is None:
                error_img = np.zeros((500, 800, 3), dtype=np.uint8)
                cv2.putText(error_img, "CAMERA DISCONNECTED", 
                           (200, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
                cv2.imshow('Live Attendance - Multi User', error_img)
                if cv2.waitKey(500) & 0xFF == ord('q'):
                    break
                continue
            
            # Mirror for natural view
            frame = cv2.flip(frame, 1)
            display = frame.copy()
            h, w = display.shape[:2]
            
            # ─────────────────────────────────────────────────
            # MULTI-FACE Recognition
            # ─────────────────────────────────────────────────
            if current_time - last_recognition_time >= RECOGNITION_INTERVAL:
                detected_faces = []
                status_messages = []
                unknown_detected_this_cycle = False
                
                try:
                    # Convert to RGB
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Fast pass first, then fallback pass for reliability if no faces are found.
                    small_frame = cv2.resize(rgb_frame, (0, 0), fx=DETECTION_SCALE, fy=DETECTION_SCALE)
                    scale_back = 1.0 / DETECTION_SCALE

                    face_locations = face_recognition.face_locations(
                        small_frame,
                        model='hog',
                        number_of_times_to_upsample=DETECTION_UPSAMPLE
                    )

                    should_run_fallback = (
                        not face_locations and
                        current_time - last_fallback_detection_time >= LIVE_FALLBACK_MIN_INTERVAL_SECONDS
                    )

                    if should_run_fallback:
                        fallback_frame = cv2.resize(
                            rgb_frame,
                            (0, 0),
                            fx=FALLBACK_DETECTION_SCALE,
                            fy=FALLBACK_DETECTION_SCALE
                        )
                        face_locations = face_recognition.face_locations(
                            fallback_frame,
                            model='hog',
                            number_of_times_to_upsample=FALLBACK_DETECTION_UPSAMPLE
                        )
                        if face_locations:
                            small_frame = fallback_frame
                            scale_back = 1.0 / FALLBACK_DETECTION_SCALE
                        last_fallback_detection_time = current_time
                    
                    if face_locations:
                        # Generate encodings for all faces
                        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
                        
                        # Process each face
                        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                            # Scale back to original resolution.
                            top = int(top * scale_back)
                            right = int(right * scale_back)
                            bottom = int(bottom * scale_back)
                            left = int(left * scale_back)
                            
                            # Default values
                            name = "Unknown"
                            color = (0, 0, 255)  # Red
                            status = "unknown"
                            student = None
                            confidence = 0
                            
                            # Compare with known faces
                            if service.known_face_encodings:
                                face_distances = face_recognition.face_distance(
                                    service.known_face_encodings, 
                                    face_encoding
                                )
                                
                                if len(face_distances) > 0:
                                    best_match_index = np.argmin(face_distances)
                                    best_distance = face_distances[best_match_index]
                                    sorted_distances = np.sort(face_distances)
                                    second_best_distance = sorted_distances[1] if len(sorted_distances) > 1 else 1.0
                                    distance_gap = float(second_best_distance - best_distance)
                                    is_separated = len(sorted_distances) == 1 or distance_gap >= MATCH_SEPARATION_MARGIN
                                    
                                    if best_distance <= RECOGNITION_TOLERANCE and is_separated:
                                        student = service.known_students[best_match_index]
                                        confidence = 1 - best_distance
                                        name = student.name
                                        
                                        # Check cooldown and mark attendance
                                        if confidence >= MIN_CONFIDENCE:
                                            prev_count, prev_seen = recent_confirms.get(student.id, (0, 0))
                                            if current_time - prev_seen > CONFIRM_WINDOW_SECONDS:
                                                prev_count = 0
                                            confirm_count = prev_count + 1
                                            recent_confirms[student.id] = (confirm_count, current_time)

                                            if confirm_count < REQUIRED_CONFIRM_FRAMES:
                                                color = (255, 200, 0)
                                                status = "confirming"
                                                status_messages.append(
                                                    f"🔎 {name} confirming {confirm_count}/{REQUIRED_CONFIRM_FRAMES}"
                                                )
                                                continue

                                            last_marked = recent_attendance.get(student.id, 0)
                                            
                                            if current_time - last_marked >= ATTENDANCE_COOLDOWN:
                                                # Mark attendance using shared helper (also sends notifications)
                                                if save_attendance(student, location='Camera Attendance'):
                                                    session_marked += 1
                                                    today_count += 1
                                                    
                                                    color = (0, 255, 0)  # Green
                                                    status = "marked"
                                                    
                                                    status_messages.append(f"✅ MARKED: {name}")
                                                    print(f"✅ Attendance marked: {name} ({confidence:.0%})")
                                                    
                                                    # Sound
                                                    try:
                                                        import winsound
                                                        winsound.Beep(1000, 150)
                                                    except:
                                                        pass
                                                else:
                                                    color = (0, 255, 255)  # Yellow
                                                    status = "already"
                                                    status_messages.append(f"ℹ️ {name} (Already today)")

                                                recent_confirms[student.id] = (0, current_time)
                                                
                                                recent_attendance[student.id] = current_time
                                            else:
                                                # Cooldown
                                                color = (255, 165, 0)  # Orange
                                                status = "cooldown"
                                        else:
                                            color = (0, 165, 255)  # Orange-ish
                                            status = "low_conf"
                            
                            # Add to detected faces
                            detected_faces.append({
                                'name': name,
                                'location': (top, right, bottom, left),
                                'color': color,
                                'status': status,
                                'confidence': confidence
                            })

                            if status == 'unknown':
                                unknown_detected_this_cycle = True
                                last_unknown_frame = frame.copy()

                    if unknown_detected_this_cycle:
                        if unknown_start_time is None:
                            unknown_start_time = current_time

                        if (
                            current_time - unknown_start_time >= LIVE_UNKNOWN_ALERT_SECONDS and
                            current_time - last_unknown_alert_time >= LIVE_UNKNOWN_ALERT_COOLDOWN_SECONDS
                        ):
                            notify_unknown_alert(
                                last_unknown_frame,
                                reason=(
                                    "Live Attendance: unknown person persisted for "
                                    f"{LIVE_UNKNOWN_ALERT_SECONDS:.0f}s"
                                )
                            )
                            last_unknown_alert_time = current_time
                            unknown_start_time = current_time
                            status_messages.append("⚠️ Unknown person alert sent")
                    else:
                        unknown_start_time = None
                    
                    if not face_locations:
                        status_messages = ["📷 No faces detected"]
                        unknown_start_time = None
                    
                    status_time = current_time
                    
                except Exception as e:
                    print(f"   ❌ Recognition error: {e}")
                    status_messages = [f"Error: {str(e)[:30]}"]
                
                last_recognition_time = current_time
            
            # ─────────────────────────────────────────────────
            # Draw UI - Header
            # ─────────────────────────────────────────────────
            cv2.rectangle(display, (0, 0), (w, 85), (40, 40, 40), -1)
            cv2.putText(display, "LIVE ATTENDANCE - MULTI USER", 
                       (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            # Stats
            elapsed = int(current_time - session_start)
            elapsed_str = f"{elapsed // 60}:{elapsed % 60:02d}"
            stats_text = f"Today: {today_count}/{total} | Session: {session_marked} | Faces: {len(detected_faces)} | Time: {elapsed_str}"
            cv2.putText(display, stats_text, 
                       (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            
            # Live indicator
            cv2.circle(display, (w - 25, 40), 12, (0, 0, 255), -1)
            cv2.putText(display, "LIVE", (w - 75, 45), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # ─────────────────────────────────────────────────
            # Draw face boxes and names
            # ─────────────────────────────────────────────────
            for face in detected_faces:
                top, right, bottom, left = face['location']
                color = face['color']
                name = face['name']
                conf = face.get('confidence', 0)
                
                # Draw rectangle
                cv2.rectangle(display, (left, top), (right, bottom), color, 2)
                
                # Draw name background
                name_text = f"{name}"
                if conf > 0:
                    name_text += f" ({conf:.0%})"
                
                text_size = cv2.getTextSize(name_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(display, 
                             (left, bottom), 
                             (left + text_size[0] + 10, bottom + text_size[1] + 15), 
                             color, -1)
                
                # Draw name text
                cv2.putText(display, name_text, 
                           (left + 5, bottom + text_size[1] + 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # ─────────────────────────────────────────────────
            # Draw status messages at bottom
            # ─────────────────────────────────────────────────
            if status_messages and (current_time - status_time < 3):
                # Calculate height needed
                msg_height = 35 * len(status_messages) + 15
                cv2.rectangle(display, (0, h - msg_height), (w, h), (50, 50, 50), -1)
                
                for i, msg in enumerate(status_messages[:5]):  # Max 5 messages
                    y = h - msg_height + 30 + (i * 35)
                    
                    if "MARKED" in msg:
                        color = (0, 255, 0)
                    elif "Already" in msg:
                        color = (0, 255, 255)
                    elif "Wait" in msg:
                        color = (0, 165, 255)
                    elif "Unknown" in msg or "Error" in msg:
                        color = (0, 0, 255)
                    else:
                        color = (180, 180, 180)
                    
                    cv2.putText(display, msg, (15, y), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            else:
                # Default status bar
                cv2.rectangle(display, (0, h - 45), (w, h), (50, 50, 50), -1)
                cv2.putText(display, "Looking for faces... | R = Refresh | Q = Quit", 
                           (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)
            
            cv2.imshow('Live Attendance - Multi User', display)
            
            # ─────────────────────────────────────────────────
            # Handle keyboard
            # ─────────────────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == ord('Q'):
                break
            elif key == ord('r') or key == ord('R'):
                print("\n🔄 Refreshing face database...")
                service.refresh_cache()
                total = Student.objects.filter(is_active=True).count()
                print(f"   ✅ Reloaded {total} students")
                status_messages = [f"🔄 Refreshed: {total} students"]
                status_time = current_time
                
    except KeyboardInterrupt:
        pass
    
    finally:
        # ─────────────────────────────────────────────────────────
        # Cleanup and summary
        # ─────────────────────────────────────────────────────────
        conn.cleanup()
        
        elapsed = int(time.time() - session_start)
        elapsed_str = f"{elapsed // 60} min {elapsed % 60} sec"
        
        print("\n" + "═" * 58)
        print("  📊 SESSION SUMMARY")
        print("  ─────────────────────────────────────────────────────")
        print(f"  • Duration        : {elapsed_str}")
        print(f"  • Attendance marked: {session_marked}")
        print(f"  • Total today     : {today_count}/{total}")
        print("═" * 58)
        
        log_system('info', f'Live attendance ended. Marked: {session_marked}')
        print("\n👋 Done!")


# ═══════════════════════════════════════════════════════════════════
# LIVE CAMERA + AUTO DOOR LOCK (No PIR Sensor)
# ═══════════════════════════════════════════════════════════════════

def live_camera_door_lock():
    """
    Live Camera + Auto Door Lock Mode (No PIR Sensor)
    - Arduino required for door control
    - No PIR sensor - continuous face scanning
    - Automatically unlocks door when face recognized
    - Auto marks attendance
    """
    print("\n" + "═" * 58)
    print("  🚪 LIVE CAMERA + AUTO DOOR LOCK")
    print("═" * 58)
    print("  • Arduino required (door control)")
    print("  • No PIR sensor needed")
    print("  • Continuous face scanning")
    print("  • Auto unlocks door on recognition")
    print("  • Auto marks attendance")
    print("═" * 58 + "\n")
    
    # ─────────────────────────────────────────────────────────────
    # SETTINGS
    # ─────────────────────────────────────────────────────────────
    RECOGNITION_INTERVAL = 0.5      # Check every 0.5 seconds
    UNLOCK_DURATION = LIVE_DOOR_UNLOCK_DURATION_SECONDS
    PERSON_COOLDOWN = LIVE_DOOR_PERSON_COOLDOWN_SECONDS
    MIN_CONFIDENCE = MIN_MATCH_CONFIDENCE  # Minimum confidence
    DETECTION_SCALE = float(getattr(settings, 'LIVE_DETECTION_SCALE', 0.5))
    DETECTION_UPSAMPLE = int(getattr(settings, 'LIVE_DETECTION_UPSAMPLE', 1))
    FALLBACK_DETECTION_SCALE = float(getattr(settings, 'LIVE_DETECTION_FALLBACK_SCALE', 0.8))
    FALLBACK_DETECTION_UPSAMPLE = int(getattr(settings, 'LIVE_DETECTION_FALLBACK_UPSAMPLE', 1))
    
    # Track recent unlocks to prevent repeated unlocking
    recent_unlocks = {}  # {student_id: last_unlock_time}
    recent_confirms = {} # {student_id: (count, last_seen_time)}
    door_unlock_time = 0  # When door was last unlocked
    door_is_unlocked = False
    
    conn = ConnectionManager()
    
    # ─────────────────────────────────────────────────────────────
    # Initialize Camera
    # ─────────────────────────────────────────────────────────────
    print("📷 Connecting camera...")
    ok, msg = conn.connect_camera(CAMERA_INDEX)
    if not ok:
        print_error_box("CAMERA NOT CONNECTED", msg + "\n\nPlease connect a USB camera.")
        return
    print(f"   ✅ {msg}")
    
    # ─────────────────────────────────────────────────────────────
    # Initialize Arduino
    # ─────────────────────────────────────────────────────────────
    print("\n🔌 Connecting Arduino...")
    ok, msg = conn.connect_arduino()
    if not ok:
        print_error_box("ARDUINO NOT CONNECTED", msg + "\n\nPlease connect Arduino via USB.")
        conn.cleanup()
        return
    print(f"   ✅ {msg}")
    
    # ─────────────────────────────────────────────────────────────
    # Initialize Face Recognition
    # ─────────────────────────────────────────────────────────────
    print("\n🤖 Loading Face Recognition...")
    try:
        service = FaceRecognitionService(tolerance=RECOGNITION_TOLERANCE, camera_index=CAMERA_INDEX)
        service.refresh_cache()
        
        total = Student.objects.filter(is_active=True).count()
        print(f"   ✅ Ready ({total} registered students)")
        
        if total == 0:
            print_error_box("NO STUDENTS", "No students registered!\n\nPlease register students first.")
            conn.cleanup()
            return
            
    except Exception as e:
        print_error_box("FACE RECOGNITION ERROR", str(e))
        conn.cleanup()
        return
    
    # Get today's attendance count
    today = timezone.now().date()
    today_count = Attendance.objects.filter(
        timestamp__date=today,
        entry_type='success'
    ).values('student').distinct().count()
    
    print(f"\n📊 Today's attendance: {today_count}/{total} students")
    
    # ─────────────────────────────────────────────────────────────
    # Start System
    # ─────────────────────────────────────────────────────────────
    print("\n" + "═" * 58)
    print("  ✅ SYSTEM STARTED - LIVE CAMERA + DOOR LOCK")
    print("  ─────────────────────────────────────────────────────")
    print("  • Continuously scanning for faces")
    print("  • Door unlocks automatically on recognition")
    print("  • Green box = Recognized (door unlocks)")
    print("  • Red box = Unknown (door locked)")
    print("  • Press R to refresh | Q to quit")
    print("═" * 58 + "\n")
    
    log_system('success', 'Live camera door lock started')
    
    cv2.namedWindow('Live Door Lock', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Live Door Lock', 1000, 750)
    
    last_recognition_time = 0
    detected_faces = []
    
    # Stats
    session_unlocks = 0
    session_marked = 0
    session_start = time.time()
    last_connection_check = time.time()
    unknown_start_time = None
    last_unknown_alert_time = 0
    last_unknown_frame = None
    last_fallback_detection_time = 0
    unauthorized_active = False
    
    # Status messages
    status_messages = []
    status_time = 0
    
    try:
        while True:
            current_time = time.time()

            pending = consume_runtime_command()
            if pending and pending.get('command') == 'OPEN_DOOR':
                requested_by = pending.get('requested_by') or 'admin'
                if conn.arduino_ok:
                    conn.send_command(build_unlock_command('Manual Open'))
                    door_is_unlocked = True
                    door_unlock_time = current_time
                    status_messages = [f"🔓 Manual door open by {requested_by}"]
                    status_time = current_time
                    print(f"\n🔓 Manual open requested by {requested_by}")
                    log_system('info', f'Manual open executed in Live Door Lock by {requested_by}.')
                else:
                    print(f"\n⚠️ Manual open ignored: Arduino disconnected ({requested_by})")
                    log_system('warning', f'Manual open ignored (Arduino offline) by {requested_by}.')
            
            # ─────────────────────────────────────────────────
            # Auto-lock door after UNLOCK_DURATION
            # ─────────────────────────────────────────────────
            if door_is_unlocked and (current_time - door_unlock_time >= UNLOCK_DURATION):
                conn.send_command("LOCK")
                door_is_unlocked = False
                print("   🔒 Door auto-locked")
            
            # ─────────────────────────────────────────────────
            # Check connections periodically
            # ─────────────────────────────────────────────────
            if current_time - last_connection_check >= CONNECTION_CHECK_INTERVAL:
                # Check camera
                if not conn.check_camera():
                    print_error_box("CAMERA DISCONNECTED", "Camera connection lost!")
                    for attempt in range(MAX_RECONNECT_ATTEMPTS):
                        print(f"   Reconnecting camera... ({attempt + 1}/{MAX_RECONNECT_ATTEMPTS})")
                        ok, _ = conn.connect_camera(CAMERA_INDEX)
                        if ok:
                            print("   ✅ Camera reconnected!")
                            cv2.namedWindow('Live Door Lock', cv2.WINDOW_NORMAL)
                            break
                        time.sleep(RECONNECT_WAIT_TIME)
                    else:
                        print("   ❌ Could not reconnect camera. Exiting...")
                        break
                
                # Check Arduino
                if not conn.check_arduino():
                    print_error_box("ARDUINO DISCONNECTED", "Arduino connection lost!")
                    for attempt in range(MAX_RECONNECT_ATTEMPTS):
                        print(f"   Reconnecting Arduino... ({attempt + 1}/{MAX_RECONNECT_ATTEMPTS})")
                        ok, _ = conn.connect_arduino()
                        if ok:
                            print("   ✅ Arduino reconnected!")
                            break
                        time.sleep(RECONNECT_WAIT_TIME)
                    else:
                        print("   ❌ Could not reconnect Arduino. Exiting...")
                        break
                
                last_connection_check = current_time
            
            # ─────────────────────────────────────────────────
            # Capture frame
            # ─────────────────────────────────────────────────
            frame = conn.capture_frame()
            
            if frame is None:
                error_img = np.zeros((500, 800, 3), dtype=np.uint8)
                cv2.putText(error_img, "CAMERA DISCONNECTED", 
                           (200, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
                cv2.imshow('Live Door Lock', error_img)
                if cv2.waitKey(500) & 0xFF == ord('q'):
                    break
                continue
            
            # Mirror for natural view
            frame = cv2.flip(frame, 1)
            display = frame.copy()
            h, w = display.shape[:2]
            
            # ─────────────────────────────────────────────────
            # Face Recognition
            # ─────────────────────────────────────────────────
            if current_time - last_recognition_time >= RECOGNITION_INTERVAL:
                detected_faces = []
                status_messages = []
                unknown_detected_this_cycle = False
                
                try:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    small_frame = cv2.resize(rgb_frame, (0, 0), fx=DETECTION_SCALE, fy=DETECTION_SCALE)
                    scale_back = 1.0 / DETECTION_SCALE
                    face_locations = face_recognition.face_locations(
                        small_frame,
                        model='hog',
                        number_of_times_to_upsample=DETECTION_UPSAMPLE
                    )

                    should_run_fallback = (
                        not face_locations and
                        current_time - last_fallback_detection_time >= LIVE_FALLBACK_MIN_INTERVAL_SECONDS
                    )

                    if should_run_fallback:
                        fallback_frame = cv2.resize(
                            rgb_frame,
                            (0, 0),
                            fx=FALLBACK_DETECTION_SCALE,
                            fy=FALLBACK_DETECTION_SCALE
                        )
                        face_locations = face_recognition.face_locations(
                            fallback_frame,
                            model='hog',
                            number_of_times_to_upsample=FALLBACK_DETECTION_UPSAMPLE
                        )
                        if face_locations:
                            small_frame = fallback_frame
                            scale_back = 1.0 / FALLBACK_DETECTION_SCALE
                        last_fallback_detection_time = current_time
                    
                    if face_locations:
                        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
                        
                        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                            # Scale back up
                            top = int(top * scale_back)
                            right = int(right * scale_back)
                            bottom = int(bottom * scale_back)
                            left = int(left * scale_back)
                            
                            name = "Unknown"
                            color = (0, 0, 255)  # Red
                            status = "unknown"
                            student = None
                            confidence = 0
                            
                            # Compare with known faces
                            if service.known_face_encodings:
                                face_distances = face_recognition.face_distance(
                                    service.known_face_encodings, 
                                    face_encoding
                                )
                                
                                if len(face_distances) > 0:
                                    best_match_index = np.argmin(face_distances)
                                    best_distance = face_distances[best_match_index]
                                    sorted_distances = np.sort(face_distances)
                                    second_best_distance = sorted_distances[1] if len(sorted_distances) > 1 else 1.0
                                    distance_gap = float(second_best_distance - best_distance)
                                    is_separated = len(sorted_distances) == 1 or distance_gap >= MATCH_SEPARATION_MARGIN
                                    
                                    if best_distance <= RECOGNITION_TOLERANCE and is_separated:
                                        student = service.known_students[best_match_index]
                                        confidence = 1 - best_distance
                                        name = student.name
                                        
                                        # Check if should unlock
                                        if confidence >= MIN_CONFIDENCE:
                                            prev_count, prev_seen = recent_confirms.get(student.id, (0, 0))
                                            if current_time - prev_seen > CONFIRM_WINDOW_SECONDS:
                                                prev_count = 0
                                            confirm_count = prev_count + 1
                                            recent_confirms[student.id] = (confirm_count, current_time)

                                            if confirm_count < REQUIRED_CONFIRM_FRAMES:
                                                color = (255, 200, 0)
                                                status = "confirming"
                                                status_messages.append(
                                                    f"🔎 {name} confirming {confirm_count}/{REQUIRED_CONFIRM_FRAMES}"
                                                )
                                                continue

                                            last_unlock = recent_unlocks.get(student.id, 0)
                                            
                                            if current_time - last_unlock >= PERSON_COOLDOWN:
                                                # UNLOCK DOOR
                                                conn.send_command(build_unlock_command(name))
                                                door_is_unlocked = True
                                                door_unlock_time = current_time
                                                unauthorized_active = False
                                                session_unlocks += 1
                                                
                                                recent_unlocks[student.id] = current_time
                                                
                                                color = (0, 255, 0)  # Green
                                                status = "unlocked"
                                                
                                                status_messages.append(f"🔓 DOOR UNLOCKED: {name}")
                                                print(f"\n🔓 ACCESS GRANTED: {name} ({confidence:.0%})")
                                                log_system('success', f'Door unlocked: {name}')
                                                
                                                # Mark attendance using shared helper (also sends notifications)
                                                if save_attendance(student, location='Door System'):
                                                    session_marked += 1
                                                    today_count += 1
                                                    status_messages.append(f"✅ Attendance: {name}")
                                                    print(f"   ✅ Attendance marked")
                                                else:
                                                    status_messages.append(f"ℹ️ {name} (Already today)")

                                                recent_confirms[student.id] = (0, current_time)
                                                
                                                # Sound
                                                try:
                                                    import winsound
                                                    winsound.Beep(1200, 200)
                                                except:
                                                    pass
                                            else:
                                                # While a known face remains in view, keep the door open timer alive.
                                                if door_is_unlocked:
                                                    door_unlock_time = current_time
                                                    color = (0, 255, 0)
                                                    status = "open_hold"
                                                    status_messages.append(f"🔓 Holding open: {name}")
                                                else:
                                                    remaining = int(PERSON_COOLDOWN - (current_time - last_unlock))
                                                    color = (255, 165, 0)  # Orange
                                                    status = "cooldown"
                                                    status_messages.append(f"⏳ {name} (Wait {remaining}s)")
                                        else:
                                            color = (0, 165, 255)  # Low confidence
                                            status = "low_conf"
                            
                            detected_faces.append({
                                'name': name,
                                'location': (top, right, bottom, left),
                                'color': color,
                                'status': status,
                                'confidence': confidence
                            })

                            if status == 'unknown':
                                unknown_detected_this_cycle = True
                                last_unknown_frame = frame.copy()

                    if unknown_detected_this_cycle:
                        if unknown_start_time is None:
                            unknown_start_time = current_time

                        if (
                            current_time - unknown_start_time >= LIVE_UNKNOWN_ALERT_SECONDS and
                            current_time - last_unknown_alert_time >= LIVE_UNKNOWN_ALERT_COOLDOWN_SECONDS
                        ):
                            notify_unknown_alert(
                                last_unknown_frame,
                                reason=(
                                    "Live Door Lock: unknown person persisted for "
                                    f"{LIVE_UNKNOWN_ALERT_SECONDS:.0f}s"
                                )
                            )
                            conn.send_command("DENIED_HOLD")
                            unauthorized_active = True
                            last_unknown_alert_time = current_time
                            unknown_start_time = current_time
                            status_messages.append("⚠️ Unauthenticated user detected")
                    else:
                        if unauthorized_active:
                            conn.send_command("IDLE")
                            unauthorized_active = False
                        unknown_start_time = None
                    
                    if not face_locations:
                        status_messages = ["📷 Scanning..."]
                        unknown_start_time = None
                    
                    status_time = current_time
                    
                except Exception as e:
                    print(f"   ❌ Recognition error: {e}")
                    status_messages = [f"Error: {str(e)[:30]}"]
                
                last_recognition_time = current_time
            
            # ─────────────────────────────────────────────────
            # Draw UI - Header
            # ─────────────────────────────────────────────────
            header_color = (0, 100, 0) if door_is_unlocked else (40, 40, 40)
            cv2.rectangle(display, (0, 0), (w, 85), header_color, -1)
            
            door_status = "🔓 UNLOCKED" if door_is_unlocked else "🔒 LOCKED"
            cv2.putText(display, f"LIVE DOOR LOCK - {door_status}", 
                       (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0) if door_is_unlocked else (255, 255, 255), 2)
            
            # Stats
            elapsed = int(current_time - session_start)
            elapsed_str = f"{elapsed // 60}:{elapsed % 60:02d}"
            stats_text = f"Today: {today_count}/{total} | Unlocks: {session_unlocks} | Marked: {session_marked} | Time: {elapsed_str}"
            cv2.putText(display, stats_text, 
                       (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            
            # Door status indicator
            indicator_color = (0, 255, 0) if door_is_unlocked else (0, 0, 255)
            cv2.circle(display, (w - 25, 40), 15, indicator_color, -1)
            
            # ─────────────────────────────────────────────────
            # Draw face boxes
            # ─────────────────────────────────────────────────
            for face in detected_faces:
                top, right, bottom, left = face['location']
                color = face['color']
                name = face['name']
                conf = face.get('confidence', 0)
                
                cv2.rectangle(display, (left, top), (right, bottom), color, 3)
                
                name_text = f"{name}"
                if conf > 0:
                    name_text += f" ({conf:.0%})"
                
                text_size = cv2.getTextSize(name_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(display, 
                             (left, bottom), 
                             (left + text_size[0] + 10, bottom + text_size[1] + 15), 
                             color, -1)
                cv2.putText(display, name_text, 
                           (left + 5, bottom + text_size[1] + 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # ─────────────────────────────────────────────────
            # Draw status messages
            # ─────────────────────────────────────────────────
            if unauthorized_active and not door_is_unlocked:
                cv2.rectangle(display, (0, h - 55), (w, h), (0, 0, 220), -1)
                cv2.putText(display, "UNAUTHORIZED - ACCESS BLOCKED", 
                           (15, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
            elif status_messages and (current_time - status_time < 3):
                msg_height = 35 * len(status_messages) + 15
                cv2.rectangle(display, (0, h - msg_height), (w, h), (50, 50, 50), -1)
                
                for i, msg in enumerate(status_messages[:5]):
                    y = h - msg_height + 30 + (i * 35)
                    
                    if "UNLOCKED" in msg:
                        color = (0, 255, 0)
                    elif "Attendance" in msg:
                        color = (0, 255, 0)
                    elif "Already" in msg:
                        color = (0, 255, 255)
                    elif "Wait" in msg:
                        color = (0, 165, 255)
                    else:
                        color = (180, 180, 180)
                    
                    cv2.putText(display, msg, (15, y), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            else:
                cv2.rectangle(display, (0, h - 45), (w, h), (50, 50, 50), -1)
                cv2.putText(display, "Scanning for faces... | R = Refresh | Q = Quit", 
                           (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)
            
            cv2.imshow('Live Door Lock', display)
            
            # ─────────────────────────────────────────────────
            # Handle keyboard
            # ─────────────────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == ord('Q'):
                break
            elif key == ord('r') or key == ord('R'):
                print("\n🔄 Refreshing face database...")
                service.refresh_cache()
                total = Student.objects.filter(is_active=True).count()
                print(f"   ✅ Reloaded {total} students")
                status_messages = [f"🔄 Refreshed: {total} students"]
                status_time = current_time
                
    except KeyboardInterrupt:
        pass
    
    finally:
        # Lock door before exit
        if door_is_unlocked:
            conn.send_command("LOCK")
            print("   🔒 Door locked")
        
        conn.cleanup()
        
        elapsed = int(time.time() - session_start)
        elapsed_str = f"{elapsed // 60} min {elapsed % 60} sec"
        
        print("\n" + "═" * 58)
        print("  📊 SESSION SUMMARY")
        print("  ─────────────────────────────────────────────────────")
        print(f"  • Duration        : {elapsed_str}")
        print(f"  • Door unlocks    : {session_unlocks}")
        print(f"  • Attendance marked: {session_marked}")
        print(f"  • Total today     : {today_count}/{total}")
        print("═" * 58)
        
        log_system('info', f'Live door lock ended. Unlocks: {session_unlocks}, Marked: {session_marked}')
        print("\n👋 Done!")


# ═══════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "═" * 58)
    print("║" + "  AIoT Smart Attendance & Door Lock System".center(56) + "║")
    print("═" * 58)
    print("\n  SELECT MODE:\n")
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │  1. Live View        (Continuous recognition)      │")
    print("  │  2. Live Attendance  (Auto attendance - No Arduino)│")
    print("  │  3. Live Door Lock   (Camera + Arduino - No PIR)   │")
    print("  │  4. Full Mode        (Arduino + Camera + PIR)      │")
    print("  └─────────────────────────────────────────────────────┘")
    print("\n" + "═" * 58)
    
    choice = sys.argv[1].strip() if len(sys.argv) > 1 else input("\n  Enter choice (1,2,3,4): ").strip()
    
    if choice == '1':
        print("\n  📌 Live View: Continuous face detection")
        live_view()
        
    elif choice == '2':
        print("\n  📌 Live Attendance: Auto attendance (no Arduino)")
        live_camera_attendance()
        
    elif choice == '3':
        print("\n  📌 Live Door Lock: Camera + Arduino (no PIR sensor)")
        live_camera_door_lock()
        
    elif choice == '4':
        print("\n  📌 Full Mode: Arduino + Camera + PIR required")
        DoorSystem(require_arduino=True).run_full_mode_live()
        
    else:
        print("\n  ⚠️ Invalid choice. Running Live Attendance...")
        live_camera_attendance()