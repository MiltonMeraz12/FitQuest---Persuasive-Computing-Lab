"""Fast middleware-level pose tracking state.

The older version of this module tried to classify gym exercises and count
repetitions.  Iron Quest 3D now uses the OpenCV window as a game-engine sensor
bridge, so this module only reports whether the pose stream is alive and leaves
semantic movement interpretation to ``motion_analysis`` and ``game_control``.
"""

from __future__ import annotations

from time import time
from typing import Any

from .keypoints import PoseCandidate, extract_primary_pose


class MovementClassifier:
    """Compatibility tracker that emits lightweight middleware pose state.

        The stream no longer carries exercise-specific state. It only exposes
        whether a pose is present, how many joints are visible, and the mean
        visible-joint confidence.
    """

    def __init__(self, *_, **__):
        self.frames_seen = 0

    def reset(self) -> None:
        """Reset lightweight stream counters when a session is reacquired."""

        self.frames_seen = 0

    def update_from_result(self, result: object) -> dict[str, Any]:
        """Extract the primary pose from a YOLO result and return middleware state."""

        return self.update_from_pose(extract_primary_pose(result))

    def update_from_pose(self, pose: PoseCandidate | None) -> dict[str, Any]:
        """Return one lightweight payload for the current pose frame."""

        self.frames_seen += 1
        if pose is None:
            return self._payload(
                valid=False,
                movement_state="no_person_detected",
                confidence=0.0,
                visible_joints=0,
            )

        visible_joints = count_visible_joints(pose)
        confidence = pose_confidence(pose)
        state = "tracking_pose" if visible_joints > 0 else "required_joints_not_visible"
        return self._payload(
            valid=visible_joints > 0,
            movement_state=state,
            confidence=confidence,
            visible_joints=visible_joints,
        )

    def _payload(
        self,
        valid: bool,
        movement_state: str,
        confidence: float,
        visible_joints: int,
    ) -> dict[str, Any]:
        """Build the stable payload shape expected by the rest of the pipeline."""

        return {
            "timestamp": round(time(), 3),
            "valid": valid,
            "detection_mode": "middleware",
            "movement_state": movement_state,
            "phase": "streaming" if valid else "waiting",
            "visible_joints": visible_joints,
            "pose_confidence": round(confidence, 3),
            "confidence": round(confidence, 3),
        }


def count_visible_joints(pose: PoseCandidate) -> int:
    """Count keypoints with a non-zero coordinate and positive confidence."""

    count = 0
    for point, confidence in zip(pose.xy, pose.conf, strict=False):
        if confidence > 0 and (point[0] != 0 or point[1] != 0):
            count += 1
    return count


def pose_confidence(pose: PoseCandidate) -> float:
    """Average confidence across visible keypoints."""

    values = [
        float(confidence)
        for point, confidence in zip(pose.xy, pose.conf, strict=False)
        if confidence > 0 and (point[0] != 0 or point[1] != 0)
    ]
    if not values:
        return 0.0
    return sum(values) / len(values)
