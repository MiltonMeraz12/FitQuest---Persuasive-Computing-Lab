"""Publish a synthetic game_control stream for offline FitQuest game testing.

This does not run YOLO or read real hardware. It drives the same production
functions the live detector uses (``MotionAnalyzer``, ``build_body_context``,
``build_game_control_payload``) with a scripted sequence of synthetic poses,
so the browser client can be exercised end to end -- calibration, all ten
exercises (including the posture-precondition hard gates and the glove grip
gate for curl vs. hammer curl), rep counting, sensor cards, set completion,
the results screen, and the avatar's bent-over-row torso hinge -- without a
camera, ESP32, or Garmin watch attached. See
docs/12_OFFLINE_AND_PRESENTATION.md for when to reach for it.

This is the project's only synthetic data source, and it exists to exercise
the browser client, never to stand in for a measurement: every number it
publishes is generated here, so nothing it produces belongs in the paper.

Run it, then open the printed URL in a browser:

    ironquest_env\\Scripts\\python.exe -m tools.simulate_game_control_stream
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.body_context import ObjectDetection, build_body_context
from ironquest.game_controls import EventDebouncer, build_game_control_payload
from ironquest.keypoints import COCO_KEYPOINTS, PoseCandidate, pose_stream_state
from ironquest.motion_analysis import MotionAnalyzer
from ironquest.web_gateway import WebGateway

FRAME_SHAPE = (480, 640, 3)
SHOULDER_Y = 130.0
HIP_Y = 300.0
LEFT_SHOULDER = (220.0, SHOULDER_Y)
RIGHT_SHOULDER = (420.0, SHOULDER_Y)
UPPER_LENGTH = 85.0
FOREARM_LENGTH = 95.0


def to_point(origin: tuple[float, float], sign: float, length: float, degrees: float) -> np.ndarray:
    """Return a point offset from ``origin`` by an angle, mirroring the browser's toPoint()."""

    radians = math.radians(degrees)
    return np.array([origin[0] + sign * math.cos(radians) * length, origin[1] + math.sin(radians) * length])


def arm_points(
    side: str, upper_deg: float, forearm_deg: float, shoulder: tuple[float, float] | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return (elbow, wrist) for one side given upper-arm/forearm angles in degrees."""

    sign = -1.0 if side == "left" else 1.0
    origin = shoulder if shoulder is not None else (LEFT_SHOULDER if side == "left" else RIGHT_SHOULDER)
    elbow = to_point(origin, sign, UPPER_LENGTH, upper_deg)
    wrist = to_point(elbow, sign, FOREARM_LENGTH, forearm_deg)
    return elbow, wrist


def build_pose(
    left_upper: float,
    left_forearm: float,
    right_upper: float,
    right_forearm: float,
    torso_lean_px: float = 0.0,
) -> PoseCandidate:
    """Build a synthetic full-confidence pose from four joint angles.

    ``torso_lean_px`` shifts both shoulders forward (in x, same direction)
    relative to the fixed hips, exercising the new torso_hinge_deg/signal
    (motion_analysis.py's ``_torso_hinge_deg``) the same way a real
    bent-over row does: hips planted, shoulders no longer sitting directly
    above them.
    """

    xy = np.zeros((17, 2), dtype=float)
    conf = np.zeros(17, dtype=float)
    left_shoulder = (LEFT_SHOULDER[0] + torso_lean_px, LEFT_SHOULDER[1])
    right_shoulder = (RIGHT_SHOULDER[0] + torso_lean_px, RIGHT_SHOULDER[1])
    left_elbow, left_wrist = arm_points("left", left_upper, left_forearm, shoulder=left_shoulder)
    right_elbow, right_wrist = arm_points("right", right_upper, right_forearm, shoulder=right_shoulder)
    points = {
        "left_shoulder": left_shoulder,
        "left_elbow": tuple(left_elbow),
        "left_wrist": tuple(left_wrist),
        "left_hip": (LEFT_SHOULDER[0], HIP_Y),
        "right_shoulder": right_shoulder,
        "right_elbow": tuple(right_elbow),
        "right_wrist": tuple(right_wrist),
        "right_hip": (RIGHT_SHOULDER[0], HIP_Y),
    }
    for name, point in points.items():
        index = COCO_KEYPOINTS[name]
        xy[index] = point
        conf[index] = 0.95
    return PoseCandidate(xy=xy, conf=conf)


# Degrees follow the same convention as the browser's pointFor(): 90 points
# straight down (arm relaxed), 0 is horizontal (shoulder height), -100 is
# overhead. DOWN/BENT/UP/FRONT/OVERHEAD name the two angles (upper, forearm)
# used at each pose extreme for one side.
DOWN = (80.0, 80.0)
BENT_CURL = (75.0, -35.0)
EXTENDED_CURL = (75.0, 80.0)
FRONT_HOLD = (2.0, 6.0)
OVERHEAD = (-100.0, -95.0)
LATERAL_OUT = (0.0, 6.0)
ROW_EXTENDED = (75.0, 80.0)
ROW_BENT = (60.0, -20.0)
ROW_TORSO_LEAN_PX = 70.0
TRICEPS_UPPER_DEG = -100.0
TRICEPS_EXTENDED_FOREARM = -95.0
TRICEPS_BENT_FOREARM = -10.0


def oscillate(t: float, period_s: float) -> float:
    """Return a smooth 0..1..0 phase for a rep cycle of the given period."""

    return (math.sin((2.0 * math.pi / period_s) * t) + 1.0) / 2.0


def lerp_pair(a: tuple[float, float], b: tuple[float, float], phase: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * phase, a[1] + (b[1] - a[1]) * phase)


def script_curl(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.2)
    active = lerp_pair(EXTENDED_CURL, BENT_CURL, phase)
    return active, DOWN, True, False


def script_press(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.6)
    active = lerp_pair(DOWN, OVERHEAD, phase)
    return active, DOWN, True, False


def script_double_press(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.8)
    both = lerp_pair(DOWN, OVERHEAD, phase)
    return both, both, True, True


def script_front_raise(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.4)
    active = lerp_pair(DOWN, FRONT_HOLD, phase)
    return active, DOWN, True, False


def script_front_hold(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    return FRONT_HOLD, FRONT_HOLD, True, True


def script_combo(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.6)
    overhead_side_is_right = int(t // 6.0) % 2 == 0
    moving = lerp_pair(DOWN, OVERHEAD, phase)
    if overhead_side_is_right:
        return FRONT_HOLD, moving, True, True
    return moving, FRONT_HOLD, True, True


def script_lateral_raise(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.2)
    active = lerp_pair(DOWN, LATERAL_OUT, phase)
    return active, DOWN, True, False


def script_hammer_curl(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    # Moves the RIGHT arm specifically (the glove's mounted side by default,
    # see build_esp32_payload's "right_forearm_armband" mount) so the browser's
    # new grip hard gate actually engages -- unlike script_curl, which moves
    # the left (non-glove) arm and so never exercises that gate.
    phase = oscillate(t, 2.2)
    active = lerp_pair(EXTENDED_CURL, BENT_CURL, phase)
    return DOWN, active, False, True


def script_bent_over_row(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.4)
    active = lerp_pair(ROW_EXTENDED, ROW_BENT, phase)
    return DOWN, active, True, True


def script_overhead_triceps_extension(t: float) -> tuple[tuple[float, float], tuple[float, float], bool, bool]:
    phase = oscillate(t, 2.4)
    forearm = TRICEPS_EXTENDED_FOREARM + (TRICEPS_BENT_FOREARM - TRICEPS_EXTENDED_FOREARM) * phase
    active = (TRICEPS_UPPER_DEG, forearm)
    return DOWN, active, False, True


CALIBRATION_ANGLES = (DOWN, DOWN)

# Exercises whose posture precondition (posturePrecondition() in
# fitquest_game.html) requires a forward torso hinge -- main() shifts the
# shoulders forward in x for these labels only, so the sequence spends most
# of its time upright (matching every other exercise) and only leans for
# the row segment, the same way a real session would.
TORSO_HINGE_EXERCISES = {"bent_over_row"}

EXERCISE_SCRIPT: list[tuple[str, float, "callable"]] = [
    ("curl", 12.0, script_curl),
    ("hammer_curl", 14.0, script_hammer_curl),
    ("lateral_raise", 12.0, script_lateral_raise),
    ("press", 12.0, script_press),
    ("overhead_triceps_extension", 14.0, script_overhead_triceps_extension),
    ("bent_over_row", 14.0, script_bent_over_row),
    ("double_press", 12.0, script_double_press),
    ("front_raise", 12.0, script_front_raise),
    ("front_hold", 10.0, script_front_hold),
    ("combo", 16.0, script_combo),
]
CALIBRATION_SECONDS = 3.0


def build_esp32_payload(t: float) -> dict:
    wobble = (math.sin(t * 2.3) + 1.0) / 2.0
    # Slow oscillation (period well beyond one rep cycle) between a neutral,
    # thumbs-up roll (~0deg, correct for hammer_curl) and a rotated,
    # palms-up roll (~95deg, correct for curl) -- lets a session sit on
    # hammer_curl long enough to see the new grip hard gate both pass and
    # block within the same ~14s segment (see script_hammer_curl).
    grip_roll = 95.0 * ((math.sin(t * 0.35) + 1.0) / 2.0)
    return {
        "status": "connected",
        "transport": "auto:udp",
        "transport_summary": "WIFI",
        "connected_transports": ["wifi"],
        "latest": {
            "mount": "right_forearm_armband",
            "orientation_euler_deg": {"pitch": 4.0 * wobble, "roll": grip_roll, "yaw": 90.0 + 6.0 * wobble},
            "motion_delta_mps2": 0.4 + wobble * 1.6,
            "angular_delta_dps": 6.0 + wobble * 30.0,
            "orientation_delta_deg": 0.5 + wobble * 1.5,
            "stability_index": max(0.15, 0.9 - wobble * 0.35),
            "sample_interval_ms": 66.0,
        },
    }


def build_wearable_payload(t: float) -> dict:
    wave = (math.sin(t / 9.0) + 1.0) / 2.0
    bpm = int(round(78 + wave * 55))
    return {
        "status": "connected",
        "device": "garmin_venu_3",
        "provider": "garmin",
        "sample_type": "connect_iq_live",
        "heart_rate_bpm": bpm,
        "activity_state": "simulated_stream",
    }


def dumbbell_detections(sided_wrists: list[tuple[str, np.ndarray]]) -> list[ObjectDetection]:
    """Return boxes shaped/placed like a held dumbbell, not a wrist-worn device.

    A box too small or too centered on the wrist gets rejected by
    ``classify_wearable_false_positive`` (body_context.py) as a smartwatch
    false positive -- intentionally, since that filter exists to reject real
    watches. Offset the box outward from the wrist and size it like an actual
    dumbbell head so the simulator exercises the "real dumbbell" path.
    """

    detections = []
    for side, wrist in sided_wrists:
        sign = -1.0 if side == "left" else 1.0
        x, y = float(wrist[0]) + sign * 26.0, float(wrist[1])
        detections.append(ObjectDetection(label="dumbbell", confidence=0.88, xyxy=(x - 32, y - 20, x + 32, y + 20)))
    return detections


def build_synthetic_frame(exercise_label: str) -> np.ndarray:
    """Return a plain BGR frame with a caption, standing in for the camera feed."""

    import cv2

    frame = np.zeros(FRAME_SHAPE, dtype=np.uint8)
    frame[:, :] = (26, 18, 12)
    cv2.putText(
        frame,
        "SIMULATED FEED",
        (24, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (120, 200, 120),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        exercise_label.upper(),
        (24, 74),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (200, 230, 255),
        2,
        cv2.LINE_AA,
    )
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a synthetic FitQuest game_control stream for browser testing.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--fps", type=float, default=15.0, help="Synthetic frame rate.")
    args = parser.parse_args()

    gateway = WebGateway(host=args.host, port=args.port)
    gateway.start()
    print(f"FitQuest simulated stream running at {gateway.url}", flush=True)
    print("Open that URL in a browser and press \"Start live session\".", flush=True)

    analyzer = MotionAnalyzer(calibration_seconds=CALIBRATION_SECONDS)
    debouncer = EventDebouncer()
    frame_interval = 1.0 / max(1.0, args.fps)
    started_at = time.time()

    cycle_length = sum(duration for _, duration, _ in EXERCISE_SCRIPT)
    try:
        while True:
            elapsed = time.time() - started_at
            if elapsed < CALIBRATION_SECONDS:
                (left_upper, left_forearm), (right_upper, right_forearm) = CALIBRATION_ANGLES
                label = "calibrating"
                left_loaded = right_loaded = False
            else:
                cycle_t = (elapsed - CALIBRATION_SECONDS) % cycle_length
                running_total = 0.0
                label, segment, script = EXERCISE_SCRIPT[0]
                segment_t = cycle_t
                for name, duration, script_fn in EXERCISE_SCRIPT:
                    if cycle_t < running_total + duration:
                        label, script = name, script_fn
                        segment_t = cycle_t - running_total
                        break
                    running_total += duration
                (left_upper, left_forearm), (right_upper, right_forearm), left_loaded, right_loaded = script(segment_t)

            torso_lean_px = ROW_TORSO_LEAN_PX if label in TORSO_HINGE_EXERCISES else 0.0
            pose = build_pose(left_upper, left_forearm, right_upper, right_forearm, torso_lean_px=torso_lean_px)
            left_shoulder = (LEFT_SHOULDER[0] + torso_lean_px, LEFT_SHOULDER[1])
            right_shoulder = (RIGHT_SHOULDER[0] + torso_lean_px, RIGHT_SHOULDER[1])
            _, left_wrist = arm_points("left", left_upper, left_forearm, shoulder=left_shoulder)
            _, right_wrist = arm_points("right", right_upper, right_forearm, shoulder=right_shoulder)
            sided_wrists = []
            if left_loaded:
                sided_wrists.append(("left", left_wrist))
            if right_loaded:
                sided_wrists.append(("right", right_wrist))
            candidates = dumbbell_detections(sided_wrists)

            movement_payload = pose_stream_state(pose)
            body_payload = build_body_context(
                pose,
                object_result=candidates or None,
                image_shape=FRAME_SHAPE,
            )
            movement_payload.update(body_payload)
            motion_payload = analyzer.update(pose, body_payload)
            esp32_payload = build_esp32_payload(elapsed)
            wearable_payload = build_wearable_payload(elapsed)
            game_control = build_game_control_payload(
                motion_payload,
                movement_payload,
                esp32_payload,
                wearable_payload,
                debouncer=debouncer,
            )

            frame = build_synthetic_frame(label)
            gateway.publish({"game_control": game_control}, frame=frame)
            time.sleep(frame_interval)
    except KeyboardInterrupt:
        print("Stopping simulated FitQuest stream.")
    finally:
        gateway.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
