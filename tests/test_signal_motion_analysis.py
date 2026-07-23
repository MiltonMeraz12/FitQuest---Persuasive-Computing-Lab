"""Universal signal checks for the camera motion analyzer."""

from __future__ import annotations

import sys
from time import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.keypoints import COCO_KEYPOINTS, PoseCandidate
from ironquest.motion_analysis import MotionAnalyzer


def _pose(left_wrist: tuple[float, float], right_wrist: tuple[float, float]) -> PoseCandidate:
    xy = np.zeros((17, 2), dtype=float)
    conf = np.zeros(17, dtype=float)
    points = {
        "left_shoulder": (100.0, 100.0),
        "left_elbow": (100.0, 150.0),
        "left_wrist": left_wrist,
        "left_hip": (100.0, 250.0),
        "right_shoulder": (220.0, 100.0),
        "right_elbow": (220.0, 150.0),
        "right_wrist": right_wrist,
        "right_hip": (220.0, 250.0),
    }
    for name, point in points.items():
        index = COCO_KEYPOINTS[name]
        xy[index] = point
        conf[index] = 0.95
    return PoseCandidate(xy=xy, conf=conf)


def test_motion_analyzer_auto_calibrates_normalized_signals() -> None:
    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    poses = [
        _pose(left_wrist=(100.0, 210.0), right_wrist=(270.0, 150.0)),
        _pose(left_wrist=(120.0, 190.0), right_wrist=(260.0, 160.0)),
        _pose(left_wrist=(140.0, 170.0), right_wrist=(250.0, 170.0)),
        _pose(left_wrist=(150.0, 150.0), right_wrist=(240.0, 180.0)),
        _pose(left_wrist=(130.0, 180.0), right_wrist=(250.0, 170.0)),
        _pose(left_wrist=(110.0, 205.0), right_wrist=(265.0, 155.0)),
    ]

    payload = {}
    for pose in poses:
        payload = analyzer.update(pose)

    signals = payload["signal_metrics"]
    left = payload["sides"]["left"]
    right = payload["sides"]["right"]

    assert signals["calibration"]["state"] == "tracking"
    assert left["angle_range_deg"] > right["angle_range_deg"]
    assert 0.0 <= left["arm_extension"] <= 1.0
    assert 0.0 <= left["height_signal"] <= 1.0
    assert 0.0 <= signals["bilateral"]["symmetry_score"] <= 1.0
    assert signals["bilateral"]["symmetry_score"] < 1.0
    assert payload["body"]["position"] == "seated_assumed"


def test_partial_pose_does_not_start_calibration() -> None:
    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    partial = PoseCandidate(xy=np.zeros((17, 2), dtype=float), conf=np.zeros(17, dtype=float))

    payload = analyzer.update(partial)

    assert payload["status"] == "arms_not_visible"
    assert payload["signal_metrics"]["calibration"]["state"] == "waiting_for_pose"


def test_reacquisition_resets_calibration_after_sustained_visibility_loss() -> None:
    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    for _ in range(6):
        analyzer.update(_pose(left_wrist=(120.0, 190.0), right_wrist=(260.0, 160.0)))
    assert analyzer.calibration_state == "tracking"

    analyzer.loss_started_at = time() - analyzer.config.reacquire_timeout_seconds - 0.1
    payload = analyzer.update(None)

    assert payload["status"] == "no_person_detected"
    assert payload["signal_metrics"]["calibration"]["state"] == "waiting_for_pose"
    assert analyzer.side_calibration_samples == {"left": 0, "right": 0}
