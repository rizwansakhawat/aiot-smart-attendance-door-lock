"""
Liveness Detection Service
==========================
Blink + head-turn challenge flow to reduce spoofing attempts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .face_landmark_service import FaceLandmarkService

try:
    from django.conf import settings
    DJANGO_SETTINGS_AVAILABLE = True
except Exception:  # pragma: no cover - standalone mode
    DJANGO_SETTINGS_AVAILABLE = False


Point = Tuple[float, float]

LIVENESS_CHALLENGE_ACTIVE = "liveness_challenge_active"
LIVENESS_PASS = "liveness_pass"
LIVENESS_FAIL = "liveness_fail"
LIVENESS_TIMEOUT = "liveness_timeout"


def _distance(a: Point, b: Point) -> float:
    return float(np.linalg.norm(np.array(a, dtype=float) - np.array(b, dtype=float)))


def _eye_aspect_ratio(eye_points: List[Point]) -> float:
    if len(eye_points) != 6:
        return 0.0
    p1, p2, p3, p4, p5, p6 = eye_points
    horizontal = _distance(p1, p4)
    if horizontal <= 1e-6:
        return 0.0
    vertical = _distance(p2, p6) + _distance(p3, p5)
    return float(vertical / (2.0 * horizontal))


def blink_detection(left_eye: List[Point], right_eye: List[Point], ear_threshold: float) -> Dict[str, float]:
    """Return EAR and closed-eye decision."""
    left_ear = _eye_aspect_ratio(left_eye)
    right_ear = _eye_aspect_ratio(right_eye)
    ear = (left_ear + right_ear) / 2.0 if (left_ear > 0 and right_ear > 0) else 0.0
    return {
        'left_ear': left_ear,
        'right_ear': right_ear,
        'ear': ear,
        'eyes_closed': ear > 0 and ear < float(ear_threshold),
    }


def head_turn_detection(yaw_angle: float, min_angle: float) -> Dict[str, float]:
    """Return yaw and whether turn threshold is met."""
    yaw = float(yaw_angle)
    return {
        'yaw': yaw,
        'turned': abs(yaw) >= float(min_angle),
    }


@dataclass
class LivenessConfig:
    enabled: bool = True
    timeout_seconds: float = 8.0
    min_blinks: int = 1
    ear_threshold: float = 0.21
    ear_consecutive_frames: int = 2
    head_turn_min_angle: float = 12.0
    required_sequence: str = "BLINK_THEN_TURN"
    fail_cooldown_seconds: float = 3.0
    debug_overlay: bool = False
    pass_grace_seconds: float = 3.0


class LivenessChallenge:
    """Simple sequential liveness challenge: blink -> turn."""

    def __init__(self, config: LivenessConfig):
        self.config = config
        self.start_time = time.time()
        self.phase = "blink"
        self.blinks_count = 0
        self.closed_eye_frames = 0
        self.passed = False
        self.failed = False
        self.timed_out = False

    def update(self, blink_closed: bool, head_turned: bool, now: Optional[float] = None) -> str:
        now = now if now is not None else time.time()
        if (now - self.start_time) > self.config.timeout_seconds:
            self.timed_out = True
            return LIVENESS_TIMEOUT

        if self.phase == "blink":
            if blink_closed:
                self.closed_eye_frames += 1
            else:
                if self.closed_eye_frames >= self.config.ear_consecutive_frames:
                    self.blinks_count += 1
                self.closed_eye_frames = 0

            if self.blinks_count >= self.config.min_blinks:
                self.phase = "turn"

        if self.phase == "turn":
            if head_turned:
                self.passed = True
                return LIVENESS_PASS

        return LIVENESS_CHALLENGE_ACTIVE


class LivenessService:
    """Orchestrates landmark extraction and challenge progression."""

    def __init__(self, config: Optional[LivenessConfig] = None):
        self.config = config or self._load_config()
        self.landmark_service = FaceLandmarkService()
        self.challenge: Optional[LivenessChallenge] = None
        self.last_failure_time = 0.0
        self.last_pass_time = 0.0

    def _load_config(self) -> LivenessConfig:
        if not DJANGO_SETTINGS_AVAILABLE:
            return LivenessConfig()

        return LivenessConfig(
            enabled=bool(getattr(settings, "LIVENESS_ENABLED", True)),
            timeout_seconds=float(getattr(settings, "LIVENESS_CHALLENGE_TIMEOUT_SECONDS", 8)),
            min_blinks=int(getattr(settings, "LIVENESS_MIN_BLINKS", 1)),
            ear_threshold=float(getattr(settings, "LIVENESS_EAR_THRESHOLD", 0.21)),
            ear_consecutive_frames=int(getattr(settings, "LIVENESS_EAR_CONSEC_FRAMES", 2)),
            head_turn_min_angle=float(getattr(settings, "LIVENESS_HEAD_TURN_MIN_ANGLE", 12)),
            required_sequence=str(getattr(settings, "LIVENESS_REQUIRED_SEQUENCE", "BLINK_THEN_TURN")),
            fail_cooldown_seconds=float(getattr(settings, "LIVENESS_FAIL_COOLDOWN_SECONDS", 3)),
            debug_overlay=bool(getattr(settings, "LIVENESS_DEBUG_OVERLAY", False)),
        )

    def reset(self) -> None:
        self.challenge = None

    def verify_liveness(self, frame: np.ndarray, face_location: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, object]:
        now = time.time()
        response: Dict[str, object] = {
            'passed': False,
            'status': LIVENESS_CHALLENGE_ACTIVE,
            'message': 'Liveness challenge in progress',
            'blink_count': 0,
            'phase': 'blink',
            'ear': 0.0,
            'yaw': 0.0,
        }

        if not self.config.enabled:
            response.update({'passed': True, 'status': LIVENESS_PASS, 'message': 'Liveness disabled'})
            return response

        if (now - self.last_pass_time) <= self.config.pass_grace_seconds:
            response.update({'passed': True, 'status': LIVENESS_PASS, 'message': 'Liveness pass (grace)'})
            return response

        if (now - self.last_failure_time) <= self.config.fail_cooldown_seconds:
            response.update({
                'status': LIVENESS_FAIL,
                'message': 'Liveness cooldown active',
            })
            return response

        if self.challenge is None:
            self.challenge = LivenessChallenge(self.config)

        landmarks = self.landmark_service.extract_landmarks(frame, face_location)
        if not landmarks:
            response.update({'message': 'Face landmarks not available'})
            response['blink_count'] = self.challenge.blinks_count
            response['phase'] = self.challenge.phase
            return response

        eye_points = self.landmark_service.get_eye_coordinates(landmarks)
        blink = blink_detection(eye_points['left_eye'], eye_points['right_eye'], self.config.ear_threshold)
        pose = self.landmark_service.calculate_head_pose(landmarks)
        turn = head_turn_detection(pose['yaw'], self.config.head_turn_min_angle)

        status = self.challenge.update(blink['eyes_closed'], turn['turned'], now=now)
        response.update({
            'status': status,
            'phase': self.challenge.phase,
            'blink_count': self.challenge.blinks_count,
            'ear': blink['ear'],
            'yaw': pose['yaw'],
        })

        if status == LIVENESS_PASS:
            self.last_pass_time = now
            self.challenge = None
            response.update({'passed': True, 'message': 'Liveness verified'})
        elif status == LIVENESS_TIMEOUT:
            self.last_failure_time = now
            self.challenge = None
            response.update({'message': 'Liveness challenge timed out'})
        else:
            response.update({'message': 'Please blink then turn your head'})

        return response
