"""
═══════════════════════════════════════════════════════════════════
AIoT Smart Attendance & Door Lock System
Main Door Control Script - FIXED VERSION
═══════════════════════════════════════════════���═══════════════════
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
# Serial Import (optional)
# ═══════════════════════════════════════════════════════════════════
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("⚠️ PySerial not installed. Run: pip install pyserial")

# ═══════════════════════════════════════════���═══════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
SERIAL_PORT = None
BAUD_RATE = 9600
CAMERA_INDEX = 0
RECOGNITION_TOLERANCE = 0.5
RECOGNITION_ATTEMPTS = 3
CAPTURE_DELAY = 0.5


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
        if 'arduino' in desc or 'ch340' in desc or 'usb' in desc:
            print(f"✅ Found Arduino on {port.device}")
            return port.device
    
    if ports:
        print(f"⚠️ Using first port: {ports[0].device}")
        return ports[0].device
    
    return None


def log_system(log_type, message):
    """Log to database and console"""
    print(f"[{log_type.upper()}] {message}")
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


# ═══════════════════════════════════════════════════════════════════
# DOOR SYSTEM CLASS
# ═══════════════════════════════════════════════════════════════════

class DoorSystem:
    def __init__(self):
        self.arduino = None
        self.camera = None
        self.face_service = None
        self.running = False
        
    def initialize(self):
        """Initialize all components"""
        print("\n" + "═" * 60)
        print("   AIoT Smart Attendance & Door Lock System")
        print("═" * 60 + "\n")
        
        # Face Recognition
        print("🤖 Loading Face Recognition...")
        try:
            self.face_service = FaceRecognitionService(
                tolerance=RECOGNITION_TOLERANCE,
                camera_index=CAMERA_INDEX
            )
            self.face_service.refresh_cache()
            
            total = Student.objects.filter(is_active=True).count()
            print(f"   ✅ Ready ({total} registered students)")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Camera
        print("\n📷 Initializing Camera...")
        try:
            self.camera = cv2.VideoCapture(CAMERA_INDEX)
            if self.camera.isOpened():
                ret, frame = self.camera.read()
                if ret:
                    h, w = frame.shape[:2]
                    print(f"   ✅ Camera ready ({w}x{h})")
                else:
                    print("   ❌ Camera capture failed")
                    return False
            else:
                print("   ❌ Camera open failed")
                return False
        except Exception as e:
            print(f"   ❌ Camera error: {e}")
            return False
        
        # Arduino
        print("\n🔌 Connecting to Arduino...")
        if SERIAL_AVAILABLE:
            try:
                port = SERIAL_PORT or find_arduino_port()
                if port:
                    self.arduino = serial.Serial(port, BAUD_RATE, timeout=1)
                    time.sleep(2)
                    print(f"   ✅ Connected on {port}")
                else:
                    print("   ⚠️ Not found (simulation mode)")
            except Exception as e:
                print(f"   ⚠️ Error: {e}")
        else:
            print("   ⚠️ PySerial not installed")
        
        print("\n" + "═" * 60)
        print("   ✅ System Ready!")
        print("═" * 60)
        
        log_system('success', 'Door system started')
        return True
    
    def send_command(self, cmd):
        """Send command to Arduino"""
        if self.arduino:
            try:
                self.arduino.write(f"{cmd}\n".encode())
                return True
            except:
                return False
        print(f"   [SIM] Arduino: {cmd}")
        return True
    
    def read_arduino(self):
        """Read from Arduino"""
        if self.arduino and self.arduino.in_waiting > 0:
            try:
                return self.arduino.readline().decode().strip()
            except:
                pass
        return None
    
    def recognize(self, frame):
        """
        Recognize face in frame
        Returns: (student, confidence) or (None, 0)
        """
        try:
            # recognize_face returns a dictionary!
            result = self.face_service.recognize_face(frame)
            
            if result['success']:
                student = result['student']
                confidence = result['confidence']
                return student, confidence
            else:
                error = result.get('error', 'Unknown error')
                print(f"   ℹ️ {error}")
                return None, 0
                
        except Exception as e:
            print(f"   ❌ Recognition error: {e}")
            return None, 0
    
    def handle_motion(self):
        """Handle motion detection"""
        print("\n" + "─" * 50)
        print("🚶 MOTION DETECTED!")
        print("─" * 50)
        
        student = None
        frame = None
        
        for attempt in range(RECOGNITION_ATTEMPTS):
            print(f"\n📸 Attempt {attempt + 1}/{RECOGNITION_ATTEMPTS}...")
            
            # Capture frame
            ret, frame = self.camera.read()
            if not ret:
                print("   ❌ Camera capture failed")
                continue
            
            # Recognize face
            student, confidence = self.recognize(frame)
            
            if student:
                print(f"   ✅ Recognized: {student.name}")
                print(f"   📊 Confidence: {confidence:.1%}")
                break
            else:
                print("   ❌ Not recognized")
            
            time.sleep(CAPTURE_DELAY)
        
        # Process result
        if student:
            print(f"\n{'═' * 50}")
            print(f"   ✅ ACCESS GRANTED: {student.name}")
            print(f"{'═' * 50}")
            
            self.send_command("UNLOCK")
            save_attendance(student)
            log_system('success', f"Access granted: {student.name}")
        else:
            print(f"\n{'═' * 50}")
            print(f"   ❌ ACCESS DENIED: Unknown Person")
            print(f"{'═' * 50}")
            
            self.send_command("DENIED")
            log_system('warning', 'Access denied: Unknown face')
            
            # Save denied image
            if frame is not None:
                try:
                    denied_dir = os.path.join(PROJECT_DIR, 'media', 'denied')
                    os.makedirs(denied_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(denied_dir, f"denied_{ts}.jpg")
                    cv2.imwrite(filepath, frame)
                    print(f"   📷 Saved: {filepath}")
                except:
                    pass
        
        print("─" * 50 + "\n")
    
    def run(self):
        """Main loop with Arduino"""
        if not self.initialize():
            print("\n❌ Initialization failed!")
            return
        
        self.running = True
        print("\n🎯 Waiting for motion... (Ctrl+C to stop)\n")
        
        try:
            while self.running:
                msg = self.read_arduino()
                if msg:
                    print(f"📡 Arduino: {msg}")
                    if "MOTION" in msg:
                        self.handle_motion()
                        print("🎯 Waiting for motion...\n")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping system...")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        print("\n🧹 Cleaning up...")
        
        if self.camera:
            self.camera.release()
            print("   ✅ Camera released")
        
        if self.arduino:
            self.send_command("LOCK")
            self.arduino.close()
            print("   ✅ Arduino disconnected")
        
        cv2.destroyAllWindows()
        log_system('info', 'Door system stopped')
        print("\n👋 Goodbye!")


# ═══════════════════════════════════════════════════════════════════
# SIMULATION MODE (without Arduino)
# ═══════════════════════════════════════════════════════════════════

class DoorSystemSimulation(DoorSystem):
    """Simulation without Arduino - uses keyboard"""
    
    def run(self):
        if not self.initialize():
            print("\n❌ Initialization failed!")
            return
        
        self.running = True
        
        print("\n" + "═" * 60)
        print("   🎮 SIMULATION MODE")
        print("   ─────────────────────────────────────")
        print("   SPACE  = Simulate motion detection")
        print("   Q      = Quit")
        print("═" * 60 + "\n")
        
        cv2.namedWindow('Door System - Simulation', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Door System - Simulation', 800, 600)
        
        last_result = ""
        result_time = 0
        
        try:
            while self.running:
                ret, frame = self.camera.read()
                if not ret:
                    continue
                
                # Mirror for natural view
                frame = cv2.flip(frame, 1)
                display = frame.copy()
                
                # Header overlay
                cv2.rectangle(display, (0, 0), (display.shape[1], 80), (50, 50, 50), -1)
                cv2.putText(display, "AIoT Smart Door System", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(display, "SPACE = Detect | Q = Quit", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                
                # Show last result
                if last_result and (time.time() - result_time < 3):
                    color = (0, 255, 0) if "GRANTED" in last_result else (0, 0, 255)
                    cv2.rectangle(display, (0, display.shape[0]-60), (display.shape[1], display.shape[0]), color, -1)
                    cv2.putText(display, last_result, 
                               (10, display.shape[0]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                
                cv2.imshow('Door System - Simulation', display)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord(' '):
                    # Store current frame before handle_motion
                    self.handle_motion()
                    
                    # Update result display (check last log)
                    try:
                        last_log = SystemLog.objects.order_by('-timestamp').first()
                        if last_log and 'Access granted' in last_log.message:
                            name = last_log.message.replace('Access granted: ', '')
                            last_result = f"ACCESS GRANTED: {name}"
                        else:
                            last_result = "ACCESS DENIED"
                    except:
                        last_result = ""
                    result_time = time.time()
                    
                elif key == ord('q') or key == ord('Q'):
                    self.running = False
                    
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
        finally:
            self.cleanup()


# ═══════════════════════════════════════════════════════════════════
# QUICK TEST MODE
# ═══════════════════════════════════════════════════════════════════

def quick_test():
    """Quick face recognition test"""
    print("\n" + "═" * 60)
    print("   🧪 QUICK TEST MODE")
    print("═" * 60 + "\n")
    
    # Load service
    print("🤖 Loading Face Recognition Service...")
    try:
        service = FaceRecognitionService(tolerance=0.5, camera_index=CAMERA_INDEX)
        service.refresh_cache()
        print("   ✅ Service ready")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Open camera
    print("\n📷 Opening camera...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    
    if not cap.isOpened():
        print("   ❌ Camera failed to open")
        return
    
    ret, test_frame = cap.read()
    if ret:
        h, w = test_frame.shape[:2]
        print(f"   ✅ Camera ready ({w}x{h})")
    else:
        print("   ❌ Camera capture failed")
        cap.release()
        return
    
    print("\n" + "═" * 60)
    print("   SPACE = Recognize face | Q = Quit")
    print("═" * 60 + "\n")
    
    cv2.namedWindow('Quick Test', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Quick Test', 800, 600)
    
    last_result = ""
    result_time = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Mirror
        frame = cv2.flip(frame, 1)
        display = frame.copy()
        
        # Header
        cv2.rectangle(display, (0, 0), (display.shape[1], 50), (50, 50, 50), -1)
        cv2.putText(display, "Quick Test - SPACE to Recognize | Q to Quit", 
                   (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Show result
        if last_result and (time.time() - result_time < 3):
            if "Recognized" in last_result:
                color = (0, 255, 0)
            else:
                color = (0, 0, 255)
            
            cv2.rectangle(display, (0, display.shape[0]-70), (display.shape[1], display.shape[0]), color, -1)
            cv2.putText(display, last_result, 
                       (10, display.shape[0]-25), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        
        cv2.imshow('Quick Test', display)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord(' '):
            print("\n📸 Recognizing...")
            
            try:
                # Call recognize_face - returns DICTIONARY
                result = service.recognize_face(frame)
                
                if result['success']:
                    student = result['student']
                    confidence = result['confidence']
                    
                    print(f"   ✅ Recognized: {student.name}")
                    print(f"   📊 Confidence: {confidence:.1%}")
                    
                    last_result = f"Recognized: {student.name} ({confidence:.0%})"
                else:
                    error = result.get('error', 'Not recognized')
                    print(f"   ❌ {error}")
                    last_result = f"Not Recognized: {error}"
                
                result_time = time.time()
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                import traceback
                traceback.print_exc()
        
        elif key == ord('q') or key == ord('Q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print("\n👋 Done!")


# ═══════════════════════════════════════════════════════════════════
# LIVE VIEW MODE (continuous recognition)
# ═══════════════════════════════════════════════════════════════════

def live_view():
    """Continuous live recognition (for demo)"""
    print("\n" + "═" * 60)
    print("   🔴 LIVE VIEW MODE")
    print("═" * 60 + "\n")
    
    # Load service
    print("🤖 Loading...")
    try:
        service = FaceRecognitionService(tolerance=0.5, camera_index=CAMERA_INDEX)
        service.refresh_cache()
        print("   ✅ Ready")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Open camera
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("   ❌ Camera failed")
        return
    
    print("\n   Press Q to quit\n")
    
    cv2.namedWindow('Live View', cv2.WINDOW_NORMAL)
    
    last_recognition_time = 0
    recognition_interval = 1.0  # Recognize every 1 second
    current_name = "Scanning..."
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame = cv2.flip(frame, 1)
        display = frame.copy()
        
        # Recognize periodically
        current_time = time.time()
        if current_time - last_recognition_time >= recognition_interval:
            try:
                result = service.recognize_face(frame)
                
                if result['success']:
                    student = result['student']
                    confidence = result['confidence']
                    current_name = f"{student.name} ({confidence:.0%})"
                    color = (0, 255, 0)
                else:
                    current_name = "Unknown"
                    color = (0, 0, 255)
                    
            except:
                current_name = "Error"
                color = (0, 0, 255)
            
            last_recognition_time = current_time
        
        # Draw result
        cv2.rectangle(display, (0, 0), (display.shape[1], 60), (0, 0, 0), -1)
        
        if "Unknown" in current_name or "Error" in current_name:
            color = (0, 0, 255)
        else:
            color = (0, 255, 0)
        
        cv2.putText(display, current_name, 
                   (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)
        
        cv2.imshow('Live View', display)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print("\n👋 Done!")


# ═══════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "═" * 60)
    print("   AIoT Smart Attendance & Door Lock System")
    print("═" * 60)
    print("\n   SELECT MODE:")
    print("   1. Full Mode (with Arduino)")
    print("   2. Simulation Mode (keyboard trigger)")
    print("   3. Quick Test (single recognition)")
    print("   4. Live View (continuous recognition)")
    print("\n" + "═" * 60)
    
    choice = input("\n   Enter choice (1/2/3/4): ").strip()
    
    if choice == '1':
        system = DoorSystem()
        system.run()
    elif choice == '2':
        system = DoorSystemSimulation()
        system.run()
    elif choice == '3':
        quick_test()
    elif choice == '4':
        live_view()
    else:
        print("\n   Invalid choice. Running Simulation Mode...")
        system = DoorSystemSimulation()
        system.run()