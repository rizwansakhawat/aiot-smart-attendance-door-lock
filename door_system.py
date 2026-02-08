"""
═══════════════════════════════════════════════════════════════════
AIoT Smart Attendance & Door Lock System
Main Door Control Script - IMPROVED VERSION
═══════════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import cv2
import numpy as np
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

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
SERIAL_PORT = None
BAUD_RATE = 9600
CAMERA_INDEX = 0
RECOGNITION_TOLERANCE = 0.5
RECOGNITION_ATTEMPTS = 3
CAPTURE_DELAY = 0.5

# Connection settings
CONNECTION_CHECK_INTERVAL = 3  # Check every 3 seconds
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_WAIT_TIME = 2  # Wait 2 seconds between attempts


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


def log_system(log_type, message):
    """Log to database and console"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{log_type.upper()}] {message}")
    try:
        SystemLog.objects.create(log_type=log_type, message=message)
    except:
        pass


def save_attendance(student, entry_type='success'):
    """Save attendance record"""
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
        
        Attendance.objects.create(
            student=student,
            entry_type=entry_type,
            location='Main Door'
        )
        log_system('success', f"Attendance saved: {student.name}")
        return True
    except Exception as e:
        log_system('error', f"Attendance error: {e}")
        return False


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
            self.camera = cv2.VideoCapture(index)
            
            if not self.camera.isOpened():
                self.camera_ok = False
                return False, "Camera cannot be opened"
            
            # Test capture
            ret, frame = self.camera.read()
            if not ret or frame is None:
                self.camera_ok = False
                return False, "Camera opened but cannot capture"
            
            h, w = frame.shape[:2]
            self.camera_ok = True
            return True, f"Camera ready ({w}x{h})"
            
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
            
            ret, frame = self.camera.read()
            self.camera_ok = (ret and frame is not None)
            return self.camera_ok
        except:
            self.camera_ok = False
            return False
    
    def capture_frame(self):
        """Capture a frame from camera"""
        if not self.camera_ok:
            return None
        
        try:
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
                # Filter out repetitive status messages
                if line in ['RESPONSE:DOOR_LOCKED', 'RESPONSE:DOOR_UNLOCKED', 'INFO:Door locked', 'INFO:Door unlocked']:
                    return None  # Ignore these
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
                print(f"  ✅ Recognized: {student.name}")
                print(f"  📊 Confidence: {confidence:.1%}")
                recognized_student = student
                break
            else:
                print("  ❌ Face not recognized")
            
            time.sleep(CAPTURE_DELAY)
        
        # Process result
        print()
        if recognized_student:
            print("  ╔════════════════════════════════════════════╗")
            print(f"  ║  ✅ ACCESS GRANTED: {recognized_student.name[:25].ljust(25)}║")
            print("  ╚════════════════════════════════════════════╝")
            
            self.conn.send_command("UNLOCK")
            save_attendance(recognized_student)
        else:
            print("  ╔════════════════════════════════════════════╗")
            print("  ║  ❌ ACCESS DENIED: Unknown Person          ║")
            print("  ╚════════════════════════════════════════════╝")
            
            self.conn.send_command("DENIED")
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
                        # Only print important messages
                        if "MOTION" in msg:
                            self.handle_motion()
                            print("🎯 Waiting for motion...\n")
                        elif "ERROR" in msg or "STATUS:READY" in msg:
                            print(f"📡 Arduino: {msg}")
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping system...")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        print("\n🧹 Cleaning up...")
        
        if self.require_arduino and self.conn.arduino_ok:
            self.conn.send_command("LOCK")
            print("   ✅ Door locked")
        
        self.conn.cleanup()
        print("   ✅ Connections closed")
        
        log_system('info', 'Door system stopped')
        print("\n👋 Goodbye!\n")


# ═══════════════════════════════════════════════════════════════════
# SIMULATION MODE
# ═══════════════════════════════════════════════════════════════════

class DoorSystemSimulation(DoorSystem):
    """Simulation mode - camera required, keyboard trigger"""
    
    def __init__(self):
        super().__init__(require_arduino=False)
    
    def run(self):
        if not self.initialize():
            return
        
        self.running = True
        self.last_check_time = time.time()
        
        print("\n" + "═" * 50)
        print("  🎮 SIMULATION MODE")
        print("  ─────────────────────────────────────────")
        print("  SPACE = Simulate motion")
        print("  Q     = Quit")
        print("═" * 50 + "\n")
        
        cv2.namedWindow('Door System', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Door System', 800, 600)
        
        last_result = ""
        result_time = 0
        
        try:
            while self.running:
                current_time = time.time()
                
                # Check camera periodically
                if current_time - self.last_check_time >= CONNECTION_CHECK_INTERVAL:
                    if not self.conn.check_camera():
                        print_error_box("CAMERA DISCONNECTED", "Camera connection lost!")
                        
                        if not self.attempt_reconnect("CAMERA"):
                            self.running = False
                            break
                        
                        # Recreate window
                        cv2.namedWindow('Door System', cv2.WINDOW_NORMAL)
                        cv2.resizeWindow('Door System', 800, 600)
                    
                    self.last_check_time = current_time
                
                # Capture frame
                frame = self.conn.capture_frame()
                
                if frame is None:
                    # Show error screen
                    error_img = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(error_img, "CAMERA DISCONNECTED", 
                               (120, 220), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.putText(error_img, "Attempting to reconnect...", 
                               (150, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    cv2.imshow('Door System', error_img)
                    
                    key = cv2.waitKey(500) & 0xFF
                    if key == ord('q'):
                        self.running = False
                    continue
                
                # Prepare display
                frame = cv2.flip(frame, 1)
                display = frame.copy()
                
                # Header
                cv2.rectangle(display, (0, 0), (display.shape[1], 70), (40, 40, 40), -1)
                cv2.putText(display, "Smart Door System - SIMULATION", 
                           (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(display, "SPACE = Detect  |  Q = Quit", 
                           (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
                
                # Status indicator
                cv2.circle(display, (display.shape[1] - 30, 35), 10, (0, 255, 0), -1)
                
                # Show result
                if last_result and (current_time - result_time < 3):
                    color = (0, 200, 0) if "GRANTED" in last_result else (0, 0, 200)
                    cv2.rectangle(display, (0, display.shape[0]-55), (display.shape[1], display.shape[0]), color, -1)
                    cv2.putText(display, last_result, 
                               (15, display.shape[0]-18), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                
                cv2.imshow('Door System', display)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord(' '):
                    self.handle_motion()
                    
                    # Update display result
                    try:
                        last_log = SystemLog.objects.order_by('-timestamp').first()
                        if last_log and 'granted' in last_log.message.lower():
                            name = last_log.message.split(': ')[-1]
                            last_result = f"ACCESS GRANTED: {name}"
                        else:
                            last_result = "ACCESS DENIED"
                    except:
                        pass
                    result_time = time.time()
                    
                elif key == ord('q'):
                    self.running = False
                    
        except KeyboardInterrupt:
            pass
        
        finally:
            self.cleanup()


# ═══════════════════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════════════════

def quick_test():
    """Quick face recognition test"""
    print("\n" + "═" * 50)
    print("  🧪 QUICK TEST MODE")
    print("═" * 50 + "\n")
    
    conn = ConnectionManager()
    
    # Connect camera
    print("📷 Connecting camera...")
    ok, msg = conn.connect_camera(CAMERA_INDEX)
    if not ok:
        print_error_box("CAMERA ERROR", msg)
        return
    print(f"   ✅ {msg}")
    
    # Load face recognition
    print("\n🤖 Loading face recognition...")
    try:
        service = FaceRecognitionService(tolerance=0.5, camera_index=CAMERA_INDEX)
        service.refresh_cache()
        print("   ✅ Ready")
    except Exception as e:
        print_error_box("ERROR", str(e))
        conn.cleanup()
        return
    
    print("\n" + "═" * 50)
    print("  SPACE = Recognize  |  Q = Quit")
    print("═" * 50 + "\n")
    
    cv2.namedWindow('Quick Test', cv2.WINDOW_NORMAL)
    
    last_result = ""
    result_time = 0
    
    try:
        while True:
            frame = conn.capture_frame()
            
            if frame is None:
                error_img = np.zeros((400, 600, 3), dtype=np.uint8)
                cv2.putText(error_img, "CAMERA ERROR", (180, 200), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.imshow('Quick Test', error_img)
                if cv2.waitKey(1000) & 0xFF == ord('q'):
                    break
                continue
            
            frame = cv2.flip(frame, 1)
            display = frame.copy()
            
            # Header
            cv2.rectangle(display, (0, 0), (display.shape[1], 45), (40, 40, 40), -1)
            cv2.putText(display, "SPACE = Recognize | Q = Quit", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            
            # Result
            if last_result and (time.time() - result_time < 2.5):
                color = (0, 200, 0) if "✅" in last_result else (0, 0, 200)
                cv2.rectangle(display, (0, display.shape[0]-50), (display.shape[1], display.shape[0]), color, -1)
                cv2.putText(display, last_result, (10, display.shape[0]-15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            cv2.imshow('Quick Test', display)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord(' '):
                print("\n📸 Recognizing...")
                result = service.recognize_face(frame)
                
                if result['success']:
                    name = result['student'].name
                    conf = result['confidence']
                    print(f"   ✅ {name} ({conf:.0%})")
                    last_result = f"✅ {name} ({conf:.0%})"
                else:
                    print(f"   ❌ {result.get('error', 'Unknown')}")
                    last_result = "❌ Not recognized"
                
                result_time = time.time()
                
            elif key == ord('q'):
                break
                
    finally:
        conn.cleanup()
        print("\n👋 Done!")


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
        service = FaceRecognitionService(tolerance=0.5, camera_index=CAMERA_INDEX)
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
    MIN_CONFIDENCE = 0.45           # Minimum confidence for attendance
    
    # Track recent attendance to prevent duplicates
    recent_attendance = {}  # {student_id: last_time}
    
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
                
                try:
                    # Convert to RGB
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Import face_recognition for multi-face detection
                    import face_recognition
                    
                    # Resize for faster processing
                    small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
                    
                    # Detect ALL faces
                    face_locations = face_recognition.face_locations(small_frame, model='hog')
                    
                    if face_locations:
                        # Generate encodings for all faces
                        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
                        
                        # Process each face
                        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                            # Scale back up (we resized by 0.5)
                            top *= 2
                            right *= 2
                            bottom *= 2
                            left *= 2
                            
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
                                    
                                    if best_distance <= RECOGNITION_TOLERANCE:
                                        student = service.known_students[best_match_index]
                                        confidence = 1 - best_distance
                                        name = student.name
                                        
                                        # Check cooldown and mark attendance
                                        if confidence >= MIN_CONFIDENCE:
                                            last_marked = recent_attendance.get(student.id, 0)
                                            
                                            if current_time - last_marked >= ATTENDANCE_COOLDOWN:
                                                # Check if already marked today
                                                already_today = Attendance.objects.filter(
                                                    student=student,
                                                    timestamp__date=today,
                                                    entry_type='success'
                                                ).exists()
                                                
                                                if not already_today:
                                                    # Mark attendance
                                                    Attendance.objects.create(
                                                        student=student,
                                                        entry_type='success',
                                                        location='Camera Attendance'
                                                    )
                                                    
                                                    session_marked += 1
                                                    today_count += 1
                                                    
                                                    color = (0, 255, 0)  # Green
                                                    status = "marked"
                                                    
                                                    status_messages.append(f"✅ MARKED: {name}")
                                                    print(f"✅ Attendance marked: {name} ({confidence:.0%})")
                                                    log_system('success', f'Attendance: {name}')
                                                    
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
                                                
                                                recent_attendance[student.id] = current_time
                                            else:
                                                # Cooldown
                                                remaining = int(ATTENDANCE_COOLDOWN - (current_time - last_marked))
                                                color = (255, 165, 0)  # Orange
                                                status = "cooldown"
                                                status_messages.append(f"⏳ {name} (Wait {remaining}s)")
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
                    
                    if not face_locations:
                        status_messages = ["📷 No faces detected"]
                    
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
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "═" * 58)
    print("║" + "  AIoT Smart Attendance & Door Lock System".center(56) + "║")
    print("═" * 58)
    print("\n  SELECT MODE:\n")
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │  1. Full Mode        (Arduino + Camera + Door)     │")
    print("  │  2. Simulation       (Camera + Keyboard trigger)   │")
    print("  │  3. Quick Test       (Single face recognition)     │")
    print("  │  4. Live View        (Continuous recognition)      │")
    print("  │  5. Live Attendance  (Auto attendance - No Arduino)│")
    print("  └─────────────────────────────────────────────────────┘")
    print("\n" + "═" * 58)
    
    choice = input("\n  Enter choice (1-5): ").strip()
    
    if choice == '1':
        print("\n  📌 Full Mode: Arduino + Camera required")
        DoorSystem(require_arduino=True).run()
        
    elif choice == '2':
        print("\n  📌 Simulation: Camera required, keyboard trigger")
        DoorSystemSimulation().run()
        
    elif choice == '3':
        print("\n  📌 Quick Test: Single recognition test")
        quick_test()
        
    elif choice == '4':
        print("\n  📌 Live View: Continuous face detection")
        live_view()
        
    elif choice == '5':
        print("\n  📌 Live Attendance: Auto attendance (no Arduino)")
        live_camera_attendance()
        
    else:
        print("\n  ⚠️ Invalid choice. Running Live Attendance...")
        live_camera_attendance()