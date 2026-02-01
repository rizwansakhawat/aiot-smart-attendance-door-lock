"""
Face Recognition Service
========================
Core service for face detection, encoding, and recognition.
Used by student registration and door access system.

Author: Your Name
Project: AIoT-Based Smart Attendance and Door Lock System

⚠️ IMPORTANT: This version is configured for USB camera (Index 1)
   Laptop camera (Index 0) is disabled due to blue screen issues
"""

import face_recognition
import cv2
import numpy as np
import json
import os
import time
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

# ═══════════════════════════════════════════════════════════════════
# CAMERA CONFIGURATION - IMPORTANT!
# ═══════════════════════════════════════════════════════════════════
# Your laptop camera (index 1) causes blue screen errors
# Only USB camera (index 0) should be used

BROKEN_CAMERA_INDEX = 0
WORKING_CAMERA_INDEX = 0 # No broken camera
USB_CAMERA_INDEX = 0      # ✅ Your working camera
DEFAULT_CAMERA_INDEX = 0  # ✅ Use Camera 0

# ═══════════════════════════════════════════════════════════════════

# Try to import Django settings
try:
    from django.conf import settings
    DJANGO_SETTINGS_AVAILABLE = True
except:
    DJANGO_SETTINGS_AVAILABLE = False

# Import models (will be used when called from Django)
try:
    from attendance.models import Student, Attendance, SystemLog
    DJANGO_AVAILABLE = True
except:
    DJANGO_AVAILABLE = False
    print("⚠️ Running in standalone mode (Django not available)")


def get_camera_index() -> int:
    """
    Get the safe camera index to use
    
    Returns:
        Camera index (always USB camera = 1)
    """
    # Try to get from Django settings
    if DJANGO_SETTINGS_AVAILABLE:
        try:
            configured_index = getattr(settings, 'CAMERA_INDEX', USB_CAMERA_INDEX)
            # Safety check: never use broken laptop camera
            if configured_index == BROKEN_CAMERA_INDEX:
                print("⚠️ WARNING: Camera index 0 is disabled (laptop camera broken)")
                print("   Automatically using USB camera (index 1)")
                return USB_CAMERA_INDEX
            return configured_index
        except:
            pass
    
    return USB_CAMERA_INDEX


class FaceRecognitionService:
    """
    Main Face Recognition Service Class
    
    Features:
    - Face detection in images/video frames
    - Face encoding generation
    - Face matching/recognition
    - In-memory caching for fast recognition
    - Performance optimization (Level 1)
    - USB Camera support (laptop camera disabled)
    
    Usage:
        service = FaceRecognitionService()
        service.load_registered_faces()
        result = service.recognize_face(image)
    """
    
    def __init__(self, tolerance: float = 0.6, model: str = 'hog', camera_index: int = None):
        """
        Initialize Face Recognition Service
        """
        self.tolerance = tolerance
        self.model = model
        
        # Camera configuration - Use Camera 0
        if camera_index is None:
            self.camera_index = 0  # ✅ Default to Camera 0
        else:
            self.camera_index = camera_index
        
        
        # Cache for registered faces (Level 1 Optimization)
        self.known_face_encodings: List[np.ndarray] = []
        self.known_face_names: List[str] = []
        self.known_face_ids: List[int] = []
        self.known_students: List[Any] = []
        
        # Performance tracking
        self.last_recognition_time: float = 0
        self.total_recognitions: int = 0
        self.successful_recognitions: int = 0
        
        # Settings
        self.min_face_size = 100  # Minimum face size in pixels
        self.max_image_size = (640, 480)  # Resize large images for speed
        
        print("=" * 50)
        print("🧠 Face Recognition Service initialized")
        print("=" * 50)
        print(f"   Tolerance: {self.tolerance}")
        print(f"   Model: {self.model}")
        print(f"   📷 Camera Index: {self.camera_index} (USB Camera)")
        print(f"   ⚠️ Laptop camera (index 0) is DISABLED")
        print("=" * 50)
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 1: FACE DETECTION
    # ═══════════════════════════════════════════════════════════════
    
    def detect_faces(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces in an image
        
        Args:
            image: Image as numpy array (BGR or RGB)
        
        Returns:
            List of face locations as (top, right, bottom, left) tuples
        
        Example:
            faces = service.detect_faces(image)
            for (top, right, bottom, left) in faces:
                cv2.rectangle(image, (left, top), (right, bottom), (0, 255, 0), 2)
        """
        # Convert BGR to RGB if needed (OpenCV uses BGR, face_recognition uses RGB)
        if len(image.shape) == 3 and image.shape[2] == 3:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            rgb_image = image
        
        # Resize image if too large (for speed)
        rgb_image = self._resize_image(rgb_image)
        
        # Detect faces using selected model
        face_locations = face_recognition.face_locations(
            rgb_image,
            model=self.model,
            number_of_times_to_upsample=1
        )
        
        return face_locations
    
    def detect_single_face(self, image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Detect the largest/closest face in an image
        
        Args:
            image: Image as numpy array
        
        Returns:
            Face location as (top, right, bottom, left) or None if no face found
        """
        face_locations = self.detect_faces(image)
        
        if not face_locations:
            return None
        
        if len(face_locations) == 1:
            return face_locations[0]
        
        # Multiple faces: return the largest one (likely closest to camera)
        largest_face = max(
            face_locations,
            key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3])  # height * width
        )
        
        return largest_face
    
    def is_face_valid(self, face_location: Tuple[int, int, int, int]) -> bool:
        """
        Check if detected face meets quality requirements
        
        Args:
            face_location: (top, right, bottom, left)
        
        Returns:
            True if face is valid, False otherwise
        """
        top, right, bottom, left = face_location
        width = right - left
        height = bottom - top
        
        # Check minimum size
        if width < self.min_face_size or height < self.min_face_size:
            return False
        
        return True
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 2: FACE ENCODING
    # ═══════════════════════════════════════════════════════════════
    
    def generate_encoding(self, image: np.ndarray, 
                         face_location: Optional[Tuple] = None) -> Optional[np.ndarray]:
        """
        Generate face encoding (128-dimensional vector) from an image
        
        Args:
            image: Image as numpy array
            face_location: Optional pre-detected face location
        
        Returns:
            Face encoding as numpy array (128 dimensions) or None
        """
        # Convert BGR to RGB
        if len(image.shape) == 3 and image.shape[2] == 3:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            rgb_image = image
        
        rgb_image = self._resize_image(rgb_image)
        
        # Detect face if location not provided
        if face_location is None:
            face_locations = face_recognition.face_locations(rgb_image, model=self.model)
            if not face_locations:
                return None
            face_location = face_locations[0]
        
        # Generate encoding
        encodings = face_recognition.face_encodings(rgb_image, [face_location])
        
        if encodings:
            return encodings[0]
        return None
    
    def generate_encodings_from_multiple_images(self, images: List[np.ndarray]) -> List[np.ndarray]:
        """
        Generate encodings from multiple images (for registration)
        
        Args:
            images: List of images as numpy arrays
        
        Returns:
            List of face encodings
        
        Example:
            # Capture 10 images during registration
            encodings = service.generate_encodings_from_multiple_images(captured_images)
            # Store encodings in database
        """
        encodings = []
        
        print(f"\n🧬 Generating encodings from {len(images)} images...")
        
        for i, image in enumerate(images):
            encoding = self.generate_encoding(image)
            if encoding is not None:
                encodings.append(encoding)
                print(f"   ✅ Image {i+1}/{len(images)}: Encoding generated")
            else:
                print(f"   ❌ Image {i+1}/{len(images)}: No face detected")
        
        print(f"\n📊 Result: {len(encodings)}/{len(images)} successful encodings")
        return encodings
    
    def encodings_to_json(self, encodings: List[np.ndarray]) -> str:
        """
        Convert list of encodings to JSON string for database storage
        
        Args:
            encodings: List of numpy arrays
        
        Returns:
            JSON string
        """
        encodings_list = [enc.tolist() for enc in encodings]
        return json.dumps(encodings_list)
    
    def json_to_encodings(self, json_string: str) -> List[np.ndarray]:
        """
        Convert JSON string from database to list of encodings
        
        Args:
            json_string: JSON string from database
        
        Returns:
            List of numpy arrays
        """
        encodings_list = json.loads(json_string)
        return [np.array(enc) for enc in encodings_list]
    
    def calculate_average_encoding(self, encodings: List[np.ndarray]) -> np.ndarray:
        """
        Calculate average encoding from multiple encodings
        (Level 1 Optimization - reduces comparison time)
        
        Args:
            encodings: List of face encodings
        
        Returns:
            Single average encoding
        """
        return np.mean(encodings, axis=0)
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 3: FACE RECOGNITION / MATCHING
    # ═══════════════════════════════════════════════════════════════
    
    def load_registered_faces(self) -> int:
        """
        Load all registered faces from database into memory cache
        (Level 1 Optimization - cache in RAM)
        
        Returns:
            Number of students loaded
        
        Call this:
        - When system starts
        - After new student registration
        - After student deletion
        """
        if not DJANGO_AVAILABLE:
            print("⚠️ Django not available, cannot load from database")
            return 0
        
        print("\n📂 Loading registered faces from database...")
        
        # Clear existing cache
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        self.known_students = []
        
        # Load active students from database
        students = Student.objects.filter(is_active=True)
        
        for student in students:
            try:
                # Parse encodings from JSON
                encodings = self.json_to_encodings(student.face_encoding)
                
                if encodings:
                    # Calculate average encoding (Level 1 Optimization)
                    avg_encoding = self.calculate_average_encoding(encodings)
                    
                    # Add to cache
                    self.known_face_encodings.append(avg_encoding)
                    self.known_face_names.append(student.name)
                    self.known_face_ids.append(student.id)
                    self.known_students.append(student)
                    
                    print(f"   ✅ Loaded: {student.name} ({len(encodings)} encodings)")
                    
            except Exception as e:
                print(f"   ⚠️ Error loading {student.name}: {e}")
        
        print(f"\n✅ Loaded {len(self.known_face_encodings)} registered faces into cache")
        return len(self.known_face_encodings)
    
    def recognize_face(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Recognize a face in an image
        
        Args:
            image: Image as numpy array (BGR)
        
        Returns:
            Dictionary with recognition result:
            {
                'success': bool,
                'student_id': int or None,
                'student_name': str or None,
                'student': Student object or None,
                'confidence': float (0-1, lower is better),
                'distance': float (face distance),
                'time_ms': float (processing time),
                'face_location': tuple or None,
                'error': str or None
            }
        
        Example:
            result = service.recognize_face(captured_image)
            if result['success']:
                print(f"Recognized: {result['student_name']}")
                print(f"Confidence: {(1-result['distance'])*100:.1f}%")
            else:
                print("Unknown person")
        """
        start_time = time.time()
        self.total_recognitions += 1
        
        # Default result
        result = {
            'success': False,
            'student_id': None,
            'student_name': None,
            'student': None,
            'confidence': 0,
            'distance': 1.0,
            'time_ms': 0,
            'face_location': None,
            'error': None
        }
        
        try:
            # Check if we have registered faces
            if not self.known_face_encodings:
                result['error'] = 'No registered faces in cache'
                return self._finalize_result(result, start_time)
            
            # Convert to RGB
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            rgb_image = self._resize_image(rgb_image)
            
            # Detect face
            face_locations = face_recognition.face_locations(rgb_image, model=self.model)
            
            if not face_locations:
                result['error'] = 'No face detected'
                return self._finalize_result(result, start_time)
            
            # Use the largest face
            face_location = max(
                face_locations,
                key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3])
            )
            result['face_location'] = face_location
            
            # Validate face
            if not self.is_face_valid(face_location):
                result['error'] = 'Face too small or invalid'
                return self._finalize_result(result, start_time)
            
            # Generate encoding for unknown face
            encodings = face_recognition.face_encodings(rgb_image, [face_location])
            
            if not encodings:
                result['error'] = 'Could not generate face encoding'
                return self._finalize_result(result, start_time)
            
            unknown_encoding = encodings[0]
            
            # Compare with known faces (vectorized - Level 1 Optimization)
            face_distances = face_recognition.face_distance(
                self.known_face_encodings,
                unknown_encoding
            )
            
            # Find best match
            best_match_index = np.argmin(face_distances)
            best_distance = face_distances[best_match_index]
            
            # Check if match is within tolerance
            if best_distance <= self.tolerance:
                result['success'] = True
                result['student_id'] = self.known_face_ids[best_match_index]
                result['student_name'] = self.known_face_names[best_match_index]
                result['student'] = self.known_students[best_match_index]
                result['distance'] = float(best_distance)
                result['confidence'] = float(1 - best_distance)
                self.successful_recognitions += 1
            else:
                result['error'] = 'No match found'
                result['distance'] = float(best_distance)
            
        except Exception as e:
            result['error'] = str(e)
        
        return self._finalize_result(result, start_time)
    
    def _finalize_result(self, result: Dict, start_time: float) -> Dict:
        """Add timing information to result"""
        elapsed_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        result['time_ms'] = round(elapsed_time, 2)
        self.last_recognition_time = elapsed_time
        return result
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 4: CAMERA OPERATIONS (USB CAMERA ONLY)
    # ═══════════════════════════════════════════════════════════════
    
    def _get_safe_camera_index(self, requested_index: int = None) -> int:
        """
        Get safe camera index
        """
        if requested_index is None:
            return 0  # ✅ Always use Camera 0
        return requested_index
    
    def capture_from_camera(self, camera_index: int = None, num_frames: int = 1) -> List[np.ndarray]:
        """
        Capture images from camera
        """
        images = []
        
        # Always use Camera 0
        if camera_index is None:
            camera_index = 0
        
        print(f"\n📷 Opening camera {camera_index}...")
        
        cap = cv2.VideoCapture(camera_index)
        

        
        if not cap.isOpened():
            print(f"❌ Cannot open camera (index {camera_index})")
            print("\n🔧 Troubleshooting:")
            print("   1. Check USB camera is connected")
            print("   2. Try unplugging and reconnecting")
            print("   3. Check if another app is using the camera")
            return images
        
        print("✅ USB camera opened successfully")
        
        # Set camera resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Warm up camera (discard first few frames)
        print("   Warming up camera...")
        for _ in range(5):
            cap.read()
        
        # Capture frames
        print(f"   Capturing {num_frames} frame(s)...")
        for i in range(num_frames):
            ret, frame = cap.read()
            if ret:
                images.append(frame)
                print(f"   ✅ Frame {i+1}/{num_frames} captured")
            else:
                print(f"   ❌ Frame {i+1}/{num_frames} failed")
            time.sleep(0.1)  # Small delay between captures
        
        cap.release()
        print(f"📷 Camera closed. Captured {len(images)} images.")
        
        return images
    
    def capture_registration_images(self, camera_index: int = None, 
                                   num_images: int = 10,
                                   delay: float = 0.5) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        Capture multiple images for registration with face detection preview
        
        ⚠️ NOTE: Laptop camera (index 0) is disabled
        
        Args:
            camera_index: Camera device index (default: USB camera = 1)
            num_images: Number of images to capture
            delay: Delay between captures (seconds)
        
        Returns:
            Tuple of (captured_images, face_crops)
        """
        images = []
        face_crops = []
        
        # Get safe camera index (always USB camera)
        safe_index = self._get_safe_camera_index(camera_index)
        
        print("\n" + "=" * 50)
        print("📸 REGISTRATION IMAGE CAPTURE")
        print("=" * 50)
        print(f"   Camera: USB Camera (index {safe_index})")
        print(f"   Images to capture: {num_images}")
        print("=" * 50)
        
        cap = cv2.VideoCapture(safe_index)
        
        if not cap.isOpened():
            print(f"❌ Cannot open USB camera (index {safe_index})")
            print("\n🔧 Troubleshooting:")
            print("   1. Check USB camera is connected")
            print("   2. Try unplugging and reconnecting")
            print("   3. Close any other apps using the camera")
            return images, face_crops
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        print("\n✅ USB camera opened successfully!")
        print("\n📋 Instructions:")
        print("   1. Look at the camera")
        print("   2. Slowly turn your head left and right")
        print("   3. Green box = Face detected (will capture)")
        print("   4. Yellow box = Move closer")
        print("   5. Press 'Q' to cancel")
        print("\n" + "-" * 50)
        
        captured = 0
        frames_without_face = 0
        
        while captured < num_images:
            ret, frame = cap.read()
            if not ret:
                print("❌ Failed to grab frame")
                continue
            
            # Detect face
            face_location = self.detect_single_face(frame)
            
            # Draw rectangle on preview
            preview = frame.copy()
            height, width = preview.shape[:2]
            
            # Add header text
            cv2.rectangle(preview, (0, 0), (width, 40), (50, 50, 50), -1)
            cv2.putText(preview, f"USB Camera | Captured: {captured}/{num_images}", 
                       (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            if face_location:
                top, right, bottom, left = face_location
                frames_without_face = 0
                
                if self.is_face_valid(face_location):
                    # Valid face - green rectangle
                    cv2.rectangle(preview, (left, top), (right, bottom), (0, 255, 0), 3)
                    cv2.putText(preview, "Face OK! Capturing...", 
                               (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    
                    # Capture this frame
                    images.append(frame.copy())
                    
                    # Crop face
                    face_crop = frame[top:bottom, left:right]
                    face_crops.append(face_crop)
                    
                    captured += 1
                    print(f"   ✅ Image {captured}/{num_images} captured")
                    
                    # Flash effect
                    flash = np.ones_like(preview) * 255
                    cv2.imshow('Registration - USB Camera (Press Q to cancel)', flash)
                    cv2.waitKey(100)
                    
                    time.sleep(delay)
                else:
                    # Face too small - yellow rectangle
                    cv2.rectangle(preview, (left, top), (right, bottom), (0, 255, 255), 3)
                    cv2.putText(preview, "Move CLOSER!", 
                               (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                # No face detected
                frames_without_face += 1
                cv2.putText(preview, "No face detected - Look at the camera", 
                           (50, height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Add footer instructions
            cv2.rectangle(preview, (0, height - 25), (width, height), (50, 50, 50), -1)
            cv2.putText(preview, "Press 'Q' to cancel | Turn head slowly for better results", 
                       (10, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            # Show preview
            cv2.imshow('Registration - USB Camera (Press Q to cancel)', preview)
            
            # Check for cancel
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                print("\n❌ Registration cancelled by user")
                break
        
        cap.release()
        cv2.destroyAllWindows()
        
        print("\n" + "=" * 50)
        print("📊 CAPTURE SUMMARY")
        print("=" * 50)
        print(f"   Total images captured: {len(images)}")
        print(f"   Face crops saved: {len(face_crops)}")
        if len(images) >= 5:
            print("   Status: ✅ Sufficient images for registration")
        else:
            print("   Status: ⚠️ Need at least 5 images for reliable recognition")
        print("=" * 50)
        
        return images, face_crops
    
    def live_camera_preview(self, camera_index: int = None, 
                           show_face_detection: bool = True) -> None:
        """
        Show live camera preview with optional face detection
        
        ⚠️ NOTE: Only USB camera is used
        
        Args:
            camera_index: Camera index (default: USB camera)
            show_face_detection: Whether to detect and draw faces
        
        Controls:
            Q - Quit
            S - Save screenshot
            F - Toggle face detection
        """
        safe_index = self._get_safe_camera_index(camera_index)
        
        print("\n" + "=" * 50)
        print("📹 LIVE CAMERA PREVIEW")
        print("=" * 50)
        print(f"   Camera: USB Camera (index {safe_index})")
        print("\n   Controls:")
        print("   Q - Quit")
        print("   S - Save screenshot")
        print("   F - Toggle face detection")
        print("=" * 50)
        
        cap = cv2.VideoCapture(safe_index)
        
        if not cap.isOpened():
            print("❌ Cannot open USB camera")
            return
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        print("\n✅ Camera opened. Press 'Q' to quit.\n")
        
        frame_count = 0
        start_time = time.time()
        detect_faces = show_face_detection
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            display = frame.copy()
            height, width = display.shape[:2]
            
            # Calculate FPS
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            
            # Face detection
            if detect_faces:
                face_locations = self.detect_faces(frame)
                for (top, right, bottom, left) in face_locations:
                    if self.is_face_valid((top, right, bottom, left)):
                        cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 0), 2)
                        cv2.putText(display, "Face Detected", 
                                   (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    else:
                        cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 255), 2)
                        cv2.putText(display, "Move Closer", 
                                   (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
            # Add info overlay
            cv2.rectangle(display, (0, 0), (width, 35), (0, 0, 0), -1)
            info_text = f"USB Camera | FPS: {fps:.1f} | Face Detection: {'ON' if detect_faces else 'OFF'}"
            cv2.putText(display, info_text, (10, 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Footer
            cv2.rectangle(display, (0, height - 25), (width, height), (0, 0, 0), -1)
            cv2.putText(display, "Q=Quit | S=Screenshot | F=Toggle Face Detection", 
                       (10, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            cv2.imshow('Live Preview - USB Camera', display)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == ord('Q'):
                break
            elif key == ord('s') or key == ord('S'):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"screenshot_{timestamp}.jpg"
                cv2.imwrite(filename, frame)
                print(f"📸 Screenshot saved: {filename}")
            elif key == ord('f') or key == ord('F'):
                detect_faces = not detect_faces
                status = "ON" if detect_faces else "OFF"
                print(f"🔍 Face detection: {status}")
        
        cap.release()
        cv2.destroyAllWindows()
        print("\n✅ Camera preview closed")
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 5: UTILITY FUNCTIONS
    # ═══════════════════════════════════════════════════════════════
    
    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """
        Resize image if too large (for speed optimization)
        """
        height, width = image.shape[:2]
        max_width, max_height = self.max_image_size
        
        if width > max_width or height > max_height:
            scale = min(max_width / width, max_height / height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            return cv2.resize(image, (new_width, new_height))
        
        return image
    
    def draw_face_box(self, image: np.ndarray, 
                     face_location: Tuple[int, int, int, int],
                     name: str = None,
                     color: Tuple[int, int, int] = (0, 255, 0)) -> np.ndarray:
        """
        Draw rectangle and name on image around face
        
        Args:
            image: Image to draw on
            face_location: (top, right, bottom, left)
            name: Name to display (optional)
            color: BGR color tuple
        
        Returns:
            Image with drawing
        """
        result = image.copy()
        top, right, bottom, left = face_location
        
        # Draw rectangle
        cv2.rectangle(result, (left, top), (right, bottom), color, 2)
        
        # Draw name
        if name:
            cv2.rectangle(result, (left, bottom - 25), (right, bottom), color, cv2.FILLED)
            cv2.putText(result, name, (left + 6, bottom - 6), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        return result
    
    def save_captured_image(self, image: np.ndarray, 
                           filename: str = None,
                           folder: str = 'captured') -> str:
        """
        Save captured image to media folder
        
        Args:
            image: Image to save
            filename: Optional filename (auto-generated if not provided)
            folder: Subfolder in media directory
        
        Returns:
            Path to saved image
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"capture_{timestamp}.jpg"
        
        # Create folder if needed
        if DJANGO_SETTINGS_AVAILABLE:
            try:
                save_folder = os.path.join(settings.MEDIA_ROOT, folder)
            except:
                save_folder = os.path.join('media', folder)
        else:
            save_folder = os.path.join('media', folder)
        
        os.makedirs(save_folder, exist_ok=True)
        
        # Save image
        filepath = os.path.join(save_folder, filename)
        cv2.imwrite(filepath, image)
        print(f"💾 Image saved: {filepath}")
        
        return filepath
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Returns:
            Dictionary with stats
        """
        success_rate = 0
        if self.total_recognitions > 0:
            success_rate = (self.successful_recognitions / self.total_recognitions) * 100
        
        return {
            'total_recognitions': self.total_recognitions,
            'successful_recognitions': self.successful_recognitions,
            'success_rate': round(success_rate, 2),
            'last_recognition_time_ms': round(self.last_recognition_time, 2),
            'registered_faces': len(self.known_face_encodings),
            'tolerance': self.tolerance,
            'model': self.model,
            'camera_index': self.camera_index
        }
    
    def refresh_cache(self) -> int:
        """
        Alias for load_registered_faces() - refresh the cache
        
        Call after:
        - New student registration
        - Student deletion
        - Student update
        """
        return self.load_registered_faces()


# ═══════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════

# Global instance for use across the application
_face_service_instance: Optional[FaceRecognitionService] = None

def get_face_recognition_service() -> FaceRecognitionService:
    """
    Get the singleton Face Recognition Service instance
    
    Usage:
        from attendance.services.face_recognition_service import get_face_recognition_service
        
        service = get_face_recognition_service()
        result = service.recognize_face(image)
    """
    global _face_service_instance
    
    if _face_service_instance is None:
        _face_service_instance = FaceRecognitionService()
        _face_service_instance.load_registered_faces()
    
    return _face_service_instance


def reset_face_service():
    """Reset the singleton instance (useful for testing)"""
    global _face_service_instance
    _face_service_instance = None


# ═══════════════════════════════════════════════════════════════════
# TESTING (Run this file directly to test)
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🧪 FACE RECOGNITION SERVICE TEST (USB Camera)")
    print("=" * 60)
    print("⚠️  NOTE: Laptop camera (index 0) is DISABLED")
    print("   Only USB camera (index 1) will be used")
    print("=" * 60)
    
    # Create service instance
    service = FaceRecognitionService()
    
    # Menu
    print("\n📋 SELECT TEST:")
    print("1. Quick capture test (1 frame)")
    print("2. Face detection test")
    print("3. Live camera preview")
    print("4. Registration simulation (10 images)")
    print("5. All tests")
    print("Q. Quit")
    
    choice = input("\nEnter choice (1-5 or Q): ").strip().lower()
    
    if choice == 'q':
        print("👋 Goodbye!")
        exit()
    
    if choice in ['1', '5']:
        print("\n" + "-" * 50)
        print("📸 TEST 1: Quick Capture (USB Camera)")
        print("-" * 50)
        
        images = service.capture_from_camera(num_frames=1)
        
        if images:
            print(f"✅ Captured {len(images)} image(s)")
            image = images[0]
            print(f"   Image size: {image.shape}")
        else:
            print("❌ Could not capture from USB camera")
    
    if choice in ['2', '5']:
        print("\n" + "-" * 50)
        print("🔍 TEST 2: Face Detection")
        print("-" * 50)
        
        images = service.capture_from_camera(num_frames=1)
        
        if images:
            image = images[0]
            faces = service.detect_faces(image)
            print(f"   Found {len(faces)} face(s)")
            
            if faces:
                # Test encoding
                encoding = service.generate_encoding(image)
                if encoding is not None:
                    print(f"   ✅ Encoding generated: {encoding.shape}")
                
                # Show image with face
                for (top, right, bottom, left) in faces:
                    cv2.rectangle(image, (left, top), (right, bottom), (0, 255, 0), 2)
                
                cv2.imshow('Detected Face - Press any key', image)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
        else:
            print("❌ Could not capture image")
    
    if choice in ['3', '5']:
        print("\n" + "-" * 50)
        print("📹 TEST 3: Live Camera Preview")
        print("-" * 50)
        
        service.live_camera_preview()
    
    if choice in ['4', '5']:
        print("\n" + "-" * 50)
        print("📝 TEST 4: Registration Simulation")
        print("-" * 50)
        
        images, face_crops = service.capture_registration_images(num_images=5)
        
        if images:
            encodings = service.generate_encodings_from_multiple_images(images)
            
            if encodings:
                print(f"\n✅ Generated {len(encodings)} encodings")
                
                # Convert to JSON
                json_data = service.encodings_to_json(encodings)
                print(f"   JSON size: {len(json_data)} bytes")
                
                # Verify JSON conversion
                loaded_encodings = service.json_to_encodings(json_data)
                print(f"   Loaded back: {len(loaded_encodings)} encodings")
                
                # Calculate average
                avg = service.calculate_average_encoding(loaded_encodings)
                print(f"   Average encoding shape: {avg.shape}")
                
                print("\n✅ Registration simulation successful!")
                print("   This data can be stored in database for recognition")
    
    # Performance stats
    print("\n" + "-" * 50)
    print("📊 PERFORMANCE STATS")
    print("-" * 50)
    stats = service.get_performance_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ TESTS COMPLETED!")
    print("=" * 60)