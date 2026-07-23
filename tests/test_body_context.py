"""Regression checks for body/dumbbell association."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.body_context import ObjectDetection, build_body_context
from ironquest.keypoints import COCO_KEYPOINTS, PoseCandidate


def _pose(left_wrist: tuple[float, float], right_wrist: tuple[float, float]) -> PoseCandidate:
    xy = np.zeros((17, 2), dtype=float)
    conf = np.zeros(17, dtype=float)
    points = {
        "left_shoulder": (100.0, 100.0),
        "left_elbow": (110.0, 150.0),
        "left_wrist": left_wrist,
        "right_shoulder": (220.0, 100.0),
        "right_elbow": (210.0, 150.0),
        "right_wrist": right_wrist,
    }
    for name, point in points.items():
        index = COCO_KEYPOINTS[name]
        xy[index] = point
        conf[index] = 0.95
    return PoseCandidate(xy=xy, conf=conf)


def test_one_dumbbell_between_close_wrists_is_claimed_by_only_one_side() -> None:
    # Both wrists brought close together (e.g. the top of a curl, or brief
    # pose jitter); one real dumbbell sits clearly closer to the left wrist.
    # Before the fix, both sides independently claimed the same detection.
    pose = _pose(left_wrist=(160.0, 200.0), right_wrist=(170.0, 200.0))
    detection = ObjectDetection(label="dumbbell", confidence=0.8, xyxy=(154.0, 194.0, 168.0, 206.0))

    context = build_body_context(pose, object_result=[detection], min_confidence=0.25)

    left = context["limbs"]["sides"]["left"]
    right = context["limbs"]["sides"]["right"]
    assert left["dumbbell_near_wrist_or_forearm"] is True
    assert right["dumbbell_near_wrist_or_forearm"] is False
    assert context["limbs"]["usage"] == "left"


def test_two_separated_dumbbells_are_each_claimed_by_their_own_side() -> None:
    pose = _pose(left_wrist=(90.0, 200.0), right_wrist=(330.0, 200.0))
    left_detection = ObjectDetection(label="dumbbell", confidence=0.8, xyxy=(80.0, 190.0, 100.0, 210.0))
    right_detection = ObjectDetection(label="dumbbell", confidence=0.8, xyxy=(320.0, 190.0, 340.0, 210.0))

    context = build_body_context(pose, object_result=[left_detection, right_detection], min_confidence=0.25)

    assert context["limbs"]["sides"]["left"]["dumbbell_near_wrist_or_forearm"] is True
    assert context["limbs"]["sides"]["right"]["dumbbell_near_wrist_or_forearm"] is True
    assert context["limbs"]["usage"] == "both"


if __name__ == "__main__":
    test_one_dumbbell_between_close_wrists_is_claimed_by_only_one_side()
    test_two_separated_dumbbells_are_each_claimed_by_their_own_side()
    print("body context association tests passed")
