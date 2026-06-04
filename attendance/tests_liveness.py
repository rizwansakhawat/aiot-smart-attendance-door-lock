import time
import unittest

from attendance.services.liveness_service import (
    LivenessChallenge,
    LivenessConfig,
    LIVENESS_CHALLENGE_ACTIVE,
    LIVENESS_PASS,
    LIVENESS_TIMEOUT,
    blink_detection,
    head_turn_detection,
)


class LivenessChallengeTests(unittest.TestCase):
    def test_blink_then_turn_sequence_passes(self):
        config = LivenessConfig(min_blinks=1, ear_consecutive_frames=2, timeout_seconds=5)
        challenge = LivenessChallenge(config)

        self.assertEqual(challenge.update(True, False), LIVENESS_CHALLENGE_ACTIVE)
        self.assertEqual(challenge.update(True, False), LIVENESS_CHALLENGE_ACTIVE)
        self.assertEqual(challenge.update(False, False), LIVENESS_CHALLENGE_ACTIVE)
        self.assertEqual(challenge.phase, "turn")
        self.assertEqual(challenge.update(False, True), LIVENESS_PASS)

    def test_challenge_times_out(self):
        config = LivenessConfig(timeout_seconds=0.01)
        challenge = LivenessChallenge(config)
        time.sleep(0.02)
        self.assertEqual(challenge.update(False, False), LIVENESS_TIMEOUT)

    def test_detection_helpers(self):
        left_eye = [(0, 0), (1, 1), (2, 1), (3, 0), (2, -1), (1, -1)]
        right_eye = [(10, 0), (11, 1), (12, 1), (13, 0), (12, -1), (11, -1)]
        blink = blink_detection(left_eye, right_eye, ear_threshold=0.8)
        self.assertTrue(blink['eyes_closed'])

        turn = head_turn_detection(yaw_angle=14, min_angle=12)
        self.assertTrue(turn['turned'])


if __name__ == "__main__":
    unittest.main()
