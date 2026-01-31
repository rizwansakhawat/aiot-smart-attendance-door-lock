"""
Attendance Services Package
===========================
Contains core services for the Smart Attendance System.

Services:
- FaceRecognitionService: Face detection, encoding, and recognition
- CameraService: Safe camera operations (USB camera only)

Usage:
    from attendance.services import get_face_recognition_service
    
    service = get_face_recognition_service()
    result = service.recognize_face(image)
"""

from .face_recognition_service import (
    FaceRecognitionService,
    get_face_recognition_service,
    reset_face_service,
    USB_CAMERA_INDEX,
    BROKEN_CAMERA_INDEX,
    DEFAULT_CAMERA_INDEX,
)

__all__ = [
    # Main service class
    'FaceRecognitionService',
    
    # Singleton functions
    'get_face_recognition_service',
    'reset_face_service',
    
    # Camera constants
    'USB_CAMERA_INDEX',
    'BROKEN_CAMERA_INDEX', 
    'DEFAULT_CAMERA_INDEX',
]

# Package version
__version__ = '1.0.0'

