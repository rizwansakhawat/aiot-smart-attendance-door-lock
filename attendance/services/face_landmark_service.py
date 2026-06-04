"""
Face Landmark Service
=====================
Thin wrapper around MediaPipe face landmark extraction helpers.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    cv2 = None
    mp = None
    MEDIAPIPE_AVAILABLE = False


Point = Tuple[float, float]
FaceLocation = Tuple[int, int, int, int]


class FaceLandmarkService:
    """Extract and cache facial landmarks and helper geometry."""

    LEFT_EYE_INDICES = (33, 160, 158, 133, 153, 144)
    RIGHT_EYE_INDICES = (362, 385, 387, 263, 373, 380)
    LEFT_CHEEK_INDEX = 234
    RIGHT_CHEEK_INDEX = 454
    NOSE_TIP_INDEX = 1

    def __init__(self, cache_ttl_seconds: float = 0.12):
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache_key: Optional[Tuple[int, FaceLocation]] = None
        self._cache_time: float = 0.0
        self._cache_landmarks: Optional[List[Point]] = None
        self._mesh = None

        if MEDIAPIPE_AVAILABLE:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

    def _normalize_face_location(self, frame: np.ndarray, face_location: Optional[FaceLocation]) -> FaceLocation:
        if face_location is not None:
            return tuple(face_location)
        h, w = frame.shape[:2]
        return (0, w, h, 0)

    def extract_landmarks(self, frame: np.ndarray, face_location: Optional[FaceLocation] = None) -> Optional[List[Point]]:
        """Extract 468 normalized 2D landmarks for the selected face."""
        if frame is None or self._mesh is None or cv2 is None:
            return None

        loc = self._normalize_face_location(frame, face_location)
        cache_key = (id(frame), loc)
        now = time.time()
        if self._cache_key == cache_key and (now - self._cache_time) <= self.cache_ttl_seconds:
            return self._cache_landmarks

        top, right, bottom, left = loc
        h, w = frame.shape[:2]
        top = max(0, min(h, int(top)))
        bottom = max(0, min(h, int(bottom)))
        left = max(0, min(w, int(left)))
        right = max(0, min(w, int(right)))
        if bottom <= top or right <= left:
            return None

        face_crop = frame[top:bottom, left:right]
        if face_crop.size == 0:
            return None

        rgb_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb_crop)
        if not result.multi_face_landmarks:
            return None

        crop_h, crop_w = face_crop.shape[:2]
        points = [
            (left + lm.x * crop_w, top + lm.y * crop_h)
            for lm in result.multi_face_landmarks[0].landmark
        ]

        self._cache_key = cache_key
        self._cache_time = now
        self._cache_landmarks = points
        return points

    def get_eye_coordinates(self, landmarks: List[Point]) -> Dict[str, List[Point]]:
        """Return left/right eye landmark points used by EAR."""
        if not landmarks or len(landmarks) < 468:
            return {'left_eye': [], 'right_eye': []}

        left_eye = [landmarks[idx] for idx in self.LEFT_EYE_INDICES]
        right_eye = [landmarks[idx] for idx in self.RIGHT_EYE_INDICES]
        return {'left_eye': left_eye, 'right_eye': right_eye}

    def calculate_head_pose(self, landmarks: List[Point]) -> Dict[str, float]:
        """
        Return rough yaw/pitch/roll proxies from landmarks.
        Values are in degrees and intended for threshold checks, not calibration-grade pose.
        """
        if not landmarks or len(landmarks) < 468:
            return {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0}

        left_cheek = np.array(landmarks[self.LEFT_CHEEK_INDEX], dtype=float)
        right_cheek = np.array(landmarks[self.RIGHT_CHEEK_INDEX], dtype=float)
        nose = np.array(landmarks[self.NOSE_TIP_INDEX], dtype=float)
        face_center = (left_cheek + right_cheek) / 2.0

        face_width = float(np.linalg.norm(right_cheek - left_cheek))
        if face_width <= 1e-6:
            return {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0}

        yaw = float(((nose[0] - face_center[0]) / (face_width / 2.0)) * 30.0)
        roll = float(math.degrees(math.atan2(right_cheek[1] - left_cheek[1], right_cheek[0] - left_cheek[0])))
        pitch = 0.0
        return {'yaw': yaw, 'pitch': pitch, 'roll': roll}
