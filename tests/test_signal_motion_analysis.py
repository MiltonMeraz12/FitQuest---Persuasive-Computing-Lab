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
    # shoulder_width (120px, both shoulders at y=100) / torso_scale (150px,
    # mean shoulder-to-hip distance) -- a dimensionless ratio used only to
    # scale the 3D avatar toward the player's own proportions.
    assert payload["body"]["build_ratio"] == 0.8


def test_calibration_bounds_keep_expanding_after_tracking_starts() -> None:
    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    poses = [
        _pose(left_wrist=(100.0, 210.0), right_wrist=(270.0, 150.0)),
        _pose(left_wrist=(120.0, 190.0), right_wrist=(260.0, 160.0)),
        _pose(left_wrist=(140.0, 170.0), right_wrist=(250.0, 170.0)),
        _pose(left_wrist=(150.0, 150.0), right_wrist=(240.0, 180.0)),
        _pose(left_wrist=(130.0, 180.0), right_wrist=(250.0, 170.0)),
        _pose(left_wrist=(110.0, 205.0), right_wrist=(265.0, 155.0)),
    ]
    for pose in poses:
        analyzer.update(pose)
    assert analyzer.calibration_state == "tracking"
    locked_span = analyzer.calibration_bounds["left"]["elbow_angle"].span

    # A movement bigger than anything seen in the fixed calibration window
    # should still widen the bounds instead of permanently clamping at
    # 0.0/1.0 for the rest of the session.
    payload = analyzer.update(_pose(left_wrist=(100.0, 100.0), right_wrist=(265.0, 155.0)))
    expanded_span = analyzer.calibration_bounds["left"]["elbow_angle"].span

    assert expanded_span > locked_span
    assert payload["signal_metrics"]["calibration"]["state"] == "tracking"
    assert payload["sides"]["left"]["arm_extension"] in (0.0, 1.0)


def test_partial_pose_does_not_start_calibration() -> None:
    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    partial = PoseCandidate(xy=np.zeros((17, 2), dtype=float), conf=np.zeros(17, dtype=float))

    payload = analyzer.update(partial)

    assert payload["status"] == "arms_not_visible"
    assert payload["signal_metrics"]["calibration"]["state"] == "waiting_for_pose"


def test_upper_arm_angle_signal_distinguishes_arm_at_side_from_overhead() -> None:
    """shoulder_angle (hip-shoulder-elbow) is the upper-arm-to-torso angle;
    curl/hammer curl keep it low (arm close to the body) while overhead
    triceps extension keeps it high (arm raised away from the body) even
    though both reuse the same elbow-bend (arm_extension) signal."""

    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    at_side = _pose(left_wrist=(100.0, 205.0), right_wrist=(220.0, 205.0))
    overhead = _pose(left_wrist=(100.0, 20.0), right_wrist=(220.0, 205.0))
    overhead.xy[COCO_KEYPOINTS["left_elbow"]] = (100.0, 20.0)

    for pose in (at_side, overhead, at_side):
        payload = analyzer.update(pose)
    payload = analyzer.update(overhead)

    assert payload["sides"]["left"]["upper_arm_angle_signal"] == 1.0


def test_torso_hinge_signal_reports_forward_lean() -> None:
    """A body-wide (not per-side) signal so bent-over row can require a
    hinged torso instead of only reusing the elbow-bend signal curl uses."""

    upright_analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    upright = _pose(left_wrist=(100.0, 150.0), right_wrist=(220.0, 150.0))
    upright_payload = upright_analyzer.update(upright)
    assert upright_payload["body"]["torso_hinge_deg"] == 0.0

    bent_analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    bent = _pose(left_wrist=(100.0, 150.0), right_wrist=(220.0, 150.0))
    # Shift both shoulders forward (in x) relative to the hips to simulate a
    # forward hinge -- the shoulder-hip line is no longer vertical.
    bent.xy[COCO_KEYPOINTS["left_shoulder"]] = (160.0, 100.0)
    bent.xy[COCO_KEYPOINTS["right_shoulder"]] = (280.0, 100.0)
    bent_payload = bent_analyzer.update(bent)

    assert bent_payload["body"]["torso_hinge_deg"] > 20.0
    assert 0.0 <= bent_payload["body"]["torso_hinge_signal"] <= 1.0


def test_calibration_quality_flags_a_barely_moving_warm_up() -> None:
    """Calibration can technically "complete" (timer + sample-count gates)
    even if the user barely moved -- quality should say so instead of
    silently producing a near-degenerate 0.0/1.0-saturated signal."""

    analyzer = MotionAnalyzer(window=6, min_confidence=0.25, calibration_seconds=0.0)
    payload = {}
    for index in range(8):
        jitter = 0.3 * (index % 2)
        payload = analyzer.update(_pose(left_wrist=(100.0 + jitter, 205.0 + jitter), right_wrist=(265.0, 155.0)))

    calibration = payload["signal_metrics"]["calibration"]
    assert calibration["state"] == "tracking"
    assert calibration["sides"]["left"]["quality"] == "insufficient"


def test_calibration_quality_is_good_for_a_wide_range_of_motion() -> None:
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

    assert payload["signal_metrics"]["calibration"]["sides"]["left"]["quality"] == "good"


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
