"""Open-ended motion analysis for Iron Quest 3D.

This module is intentionally different from the removed rule-based exercise
tracker. That older code asked "which known exercise is this?". This module asks a more
game-friendly question: "what is each side of the body doing right now?"

That matters because Iron Quest 3D may use invented movements, mixed arm
positions, jumps, or dumbbell gestures that are not standard gym exercises.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import time
from typing import Any

import numpy as np

from .keypoints import PoseCandidate, average_confidence, calculate_angle, get_point


SIDES = ("left", "right")


@dataclass
class MotionAnalysisConfig:
    """Calibration constants for camera-derived universal motion primitives."""

    calibration_seconds: float = 7.0
    calibration_min_samples: int = 6
    calibration_min_span: float = 1e-3
    direction_threshold: float = 0.08
    elbow_extended_angle: float = 150.0
    elbow_bent_angle: float = 85.0
    overhead_offset_torso: float = 0.35
    shoulder_height_offset_torso: float = 0.25
    torso_height_offset_torso: float = 0.25
    lateral_reach_offset_torso: float = 0.35
    fallback_torso_scale_px: float = 100.0
    max_height_score: float = 1.5
    body_motion_threshold: float = 0.12
    jump_delta_threshold: float = 0.16
    jump_speed_threshold: float = 0.08
    reacquire_timeout_seconds: float = 3.0


MOTION_CONFIG = MotionAnalysisConfig()


def _round_point(point: np.ndarray | None) -> list[float] | None:
    """Return a JSON-friendly point or ``None``."""

    if point is None:
        return None
    return [round(float(point[0]), 2), round(float(point[1]), 2)]


def _safe_norm(vector: np.ndarray) -> float:
    """Return vector length without exposing NumPy scalar types in payloads."""

    return float(np.linalg.norm(vector))


def _clamp01(value: float | None) -> float | None:
    """Clamp a normalized analog value into the 0.0-1.0 range."""

    if value is None:
        return None
    return float(np.clip(value, 0.0, 1.0))


def _ratio_score(first: float | None, second: float | None) -> float | None:
    """Return a bilateral similarity score where 1.0 means both sides match."""

    if first is None or second is None:
        return None
    first_abs = abs(float(first))
    second_abs = abs(float(second))
    larger = max(first_abs, second_abs)
    if larger <= 1e-6:
        return 1.0
    return float(np.clip(min(first_abs, second_abs) / larger, 0.0, 1.0))


def _direction_from_delta(delta: np.ndarray, threshold: float = MOTION_CONFIG.direction_threshold) -> str:
    """Convert a normalized 2D motion vector into a readable direction.

    Image coordinates use positive Y downward, so negative Y means "up".
    """

    dx, dy = float(delta[0]), float(delta[1])
    labels: list[str] = []
    if dy < -threshold:
        labels.append("up")
    elif dy > threshold:
        labels.append("down")
    if dx < -threshold:
        labels.append("left")
    elif dx > threshold:
        labels.append("right")
    return "_".join(labels) if labels else "steady"


def _elbow_state(angle: float | None, config: MotionAnalysisConfig = MOTION_CONFIG) -> str:
    """Convert an elbow angle into a simple readable bend state."""

    if angle is None:
        return "unknown"
    if angle >= config.elbow_extended_angle:
        return "extended"
    if angle <= config.elbow_bent_angle:
        return "bent"
    return "mid"


def _height_zone(
    wrist: np.ndarray,
    shoulder: np.ndarray,
    hip: np.ndarray,
    torso_scale: float,
    config: MotionAnalysisConfig = MOTION_CONFIG,
) -> str:
    """Classify wrist height relative to the body.

    This is a 2D camera estimate. It says where the wrist appears in the image,
    not the true 3D position of the dumbbell.
    """

    if wrist[1] < shoulder[1] - config.overhead_offset_torso * torso_scale:
        return "overhead"
    if wrist[1] < shoulder[1] + config.shoulder_height_offset_torso * torso_scale:
        return "shoulder_height"
    if wrist[1] < hip[1] + config.torso_height_offset_torso * torso_scale:
        return "torso_height"
    return "low"


def _reach_zone(
    side: str,
    wrist: np.ndarray,
    left_shoulder: np.ndarray | None,
    right_shoulder: np.ndarray | None,
    torso_scale: float,
    config: MotionAnalysisConfig = MOTION_CONFIG,
) -> str:
    """Classify lateral wrist position.

    A single 2D webcam cannot truly prove "in front of the body". The
    ``front_candidate`` token means the wrist is near the torso/shoulder height
    with an extended arm, which is a useful proxy for future game controls.
    """

    own_shoulder = left_shoulder if side == "left" else right_shoulder
    other_shoulder = right_shoulder if side == "left" else left_shoulder
    if own_shoulder is None:
        return "unknown"

    if side == "left" and wrist[0] < own_shoulder[0] - config.lateral_reach_offset_torso * torso_scale:
        return "outside_left"
    if side == "right" and wrist[0] > own_shoulder[0] + config.lateral_reach_offset_torso * torso_scale:
        return "outside_right"
    if other_shoulder is not None:
        if side == "left" and wrist[0] > other_shoulder[0]:
            return "cross_body"
        if side == "right" and wrist[0] < other_shoulder[0]:
            return "cross_body"
    return "centerline"


@dataclass(frozen=True)
class CalibrationFeature:
    """Observed min/max bounds for one user-specific signal."""

    minimum: float | None = None
    maximum: float | None = None
    samples: int = 0

    def update(self, value: float | None) -> "CalibrationFeature":
        """Return a new bound expanded by one observed value."""

        if value is None:
            return self
        numeric = float(value)
        return CalibrationFeature(
            minimum=numeric if self.minimum is None else min(self.minimum, numeric),
            maximum=numeric if self.maximum is None else max(self.maximum, numeric),
            samples=self.samples + 1,
        )

    @property
    def span(self) -> float | None:
        """Return the observed range for this feature."""

        if self.minimum is None or self.maximum is None:
            return None
        return float(self.maximum - self.minimum)

    def normalise(self, value: float | None, min_span: float) -> float | None:
        """Map a raw value into the calibrated 0.0-1.0 interval."""

        if value is None or self.minimum is None or self.maximum is None:
            return None
        span = self.maximum - self.minimum
        if abs(span) < min_span:
            return 0.0
        return _clamp01((float(value) - self.minimum) / span)

    def as_payload(self) -> dict[str, Any]:
        """Return bounds in a JSON-friendly form."""

        return {
            "min": None if self.minimum is None else round(self.minimum, 4),
            "max": None if self.maximum is None else round(self.maximum, 4),
            "span": None if self.span is None else round(self.span, 4),
            "samples": self.samples,
        }


@dataclass(frozen=True)
class BodyMotion:
    """Whole-body motion estimate used for jump-like controls."""

    vertical_delta: float = 0.0
    motion_direction: str = "steady"
    jump_candidate: bool = False
    vertical_speed: float | None = None
    position: str = "unknown"

    def as_payload(self) -> dict[str, Any]:
        """Convert body motion into the detector payload."""

        payload: dict[str, Any] = {
            "vertical_delta": round(self.vertical_delta, 3),
            "motion_direction": self.motion_direction,
            "jump_candidate": self.jump_candidate,
            "position": self.position,
        }
        if self.vertical_speed is not None:
            payload["vertical_speed"] = round(self.vertical_speed, 3)
        return payload


@dataclass(frozen=True)
class MotionAnalysisPayload:
    """Typed open-ended motion payload for one frame."""

    status: str
    signature: str
    tokens: list[str]
    sides: dict[str, "SideMotion"]
    body: BodyMotion
    signal_metrics: dict[str, Any]
    note: str

    def as_payload(self) -> dict[str, Any]:
        """Return the dictionary shape consumed by UI and game controls."""

        return {
            "status": self.status,
            "signature": self.signature,
            "tokens": self.tokens,
            "sides": {side: signal.as_payload() for side, signal in self.sides.items()},
            "body": self.body.as_payload(),
            "signal_metrics": self.signal_metrics,
            "note": self.note,
        }


@dataclass
class SideMotion:
    """Camera-derived universal signal state for one side of the body."""

    side: str
    visible: bool
    confidence: float
    wrist: list[float] | None
    elbow_angle: float | None
    shoulder_angle: float | None
    angle_range_deg: float | None
    arm_extension: float | None
    height_signal: float | None
    reach_signal: float | None
    range_utilization: float | None
    height_zone: str
    reach_zone: str
    elbow_state: str
    loaded: bool | None
    z_distance: float | None
    height_score: float
    motion_direction: str
    motion_speed: float
    motion_delta: list[float]
    tokens: list[str]

    def as_payload(self) -> dict[str, Any]:
        """Convert one side's analysis into the detector JSON payload."""

        return {
            "visible": self.visible,
            "confidence": round(self.confidence, 3),
            "wrist": self.wrist,
            "elbow_angle": None if self.elbow_angle is None else round(self.elbow_angle, 2),
            "shoulder_angle": None if self.shoulder_angle is None else round(self.shoulder_angle, 2),
            "angle_range_deg": None if self.angle_range_deg is None else round(self.angle_range_deg, 2),
            "arm_extension": None if self.arm_extension is None else round(self.arm_extension, 3),
            "height_signal": None if self.height_signal is None else round(self.height_signal, 3),
            "reach_signal": None if self.reach_signal is None else round(self.reach_signal, 3),
            "range_utilization": None if self.range_utilization is None else round(self.range_utilization, 3),
            "height_zone": self.height_zone,
            "reach_zone": self.reach_zone,
            "elbow_state": self.elbow_state,
            "loaded": self.loaded,
            "z_distance": None if self.z_distance is None else round(self.z_distance, 3),
            "height_score": round(self.height_score, 3),
            "motion_direction": self.motion_direction,
            "motion_speed": round(self.motion_speed, 3),
            "motion_delta": [round(value, 3) for value in self.motion_delta],
            "tokens": self.tokens,
        }


class MotionAnalyzer:
    """Analyze arbitrary body/dumbbell motion primitives over time.

    The output is designed for three future uses:

    1. Explaining what the camera sees.
    2. Creating labeled training data for later action recognition.
    3. Mapping body/dumbbell states to game controls before the game exists.
    """

    def __init__(
        self,
        window: int = 12,
        min_confidence: float = 0.25,
        config: MotionAnalysisConfig = MOTION_CONFIG,
        calibration_seconds: float | None = None,
    ):
        """Create rolling histories used to compare current and past motion."""

        self.window = max(int(window), 2)
        self.min_confidence = float(min_confidence)
        self.config = MotionAnalysisConfig(
            calibration_seconds=max(
                float(config.calibration_seconds if calibration_seconds is None else calibration_seconds),
                0.0,
            ),
            calibration_min_samples=config.calibration_min_samples,
            calibration_min_span=config.calibration_min_span,
            direction_threshold=config.direction_threshold,
            elbow_extended_angle=config.elbow_extended_angle,
            elbow_bent_angle=config.elbow_bent_angle,
            overhead_offset_torso=config.overhead_offset_torso,
            shoulder_height_offset_torso=config.shoulder_height_offset_torso,
            torso_height_offset_torso=config.torso_height_offset_torso,
            lateral_reach_offset_torso=config.lateral_reach_offset_torso,
            fallback_torso_scale_px=config.fallback_torso_scale_px,
            max_height_score=config.max_height_score,
            body_motion_threshold=config.body_motion_threshold,
            jump_delta_threshold=config.jump_delta_threshold,
            jump_speed_threshold=config.jump_speed_threshold,
            reacquire_timeout_seconds=max(float(config.reacquire_timeout_seconds), 0.5),
        )
        self.calibration_started_at: float | None = None
        self.calibration_state = "waiting_for_pose"
        self.loss_started_at: float | None = None
        self.calibration_bounds: dict[str, dict[str, CalibrationFeature]] = {}
        self.side_calibration_samples: dict[str, int] = {}
        self.side_history: dict[str, deque[tuple[float, np.ndarray]]] = {}
        self.angle_history: dict[str, deque[tuple[float, float]]] = {}
        self.body_history: deque[tuple[float, np.ndarray]] = deque(maxlen=self.window)
        self.reset()

    def reset(self) -> None:
        """Clear session calibration and rolling state for a fresh acquisition.

        The camera pipeline can stay open while this is called. The next frame
        with a complete shoulder/elbow/wrist chain starts a new calibration
        window, which makes first-use and post-disconnect recovery equivalent.
        """

        self.calibration_started_at = None
        self.calibration_state = "waiting_for_pose"
        self.loss_started_at = None
        self.calibration_bounds = {
            side: {
                "elbow_angle": CalibrationFeature(),
                "height_score": CalibrationFeature(),
                "reach_x": CalibrationFeature(),
            }
            for side in SIDES
        }
        self.side_calibration_samples = {side: 0 for side in SIDES}
        self.side_history = {side: deque(maxlen=self.window) for side in SIDES}
        self.angle_history = {side: deque(maxlen=self.window) for side in SIDES}
        self.body_history = deque(maxlen=self.window)

    def update(self, pose: PoseCandidate | None, body_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return open-ended motion analysis for one frame."""

        timestamp = time()
        if pose is None:
            self._update_visibility_recovery(False, timestamp)
            return MotionAnalysisPayload(
                status="no_person_detected",
                signature="no_person",
                tokens=[],
                sides={},
                body=BodyMotion(jump_candidate=False),
                signal_metrics=self._empty_signal_metrics("no_pose", timestamp),
                note="No pose was available for this frame.",
            ).as_payload()

        body_context = body_context or {}
        torso_scale = self._torso_scale(pose)
        left_shoulder = get_point(pose, "shoulder", "left", self.min_confidence)
        right_shoulder = get_point(pose, "shoulder", "right", self.min_confidence)
        torso_center = self._torso_center(pose)
        if torso_center is not None:
            self.body_history.append((timestamp, torso_center))

        sides: dict[str, SideMotion] = {}
        tokens: list[str] = []
        for side in SIDES:
            side_motion = self._analyze_side(
                pose=pose,
                side=side,
                torso_scale=torso_scale,
                left_shoulder=left_shoulder,
                right_shoulder=right_shoulder,
                body_context=body_context,
                timestamp=timestamp,
            )
            sides[side] = side_motion
            tokens.extend(side_motion.tokens)

        body_motion = self._analyze_body_motion(pose, torso_scale)
        if body_motion.jump_candidate:
            tokens.append("body_jump_candidate")

        combo_tokens = self._combination_tokens(sides)
        tokens.extend(combo_tokens)
        signature = self._signature(sides, body_motion)
        arms_visible = any(side.visible for side in sides.values())
        self._update_visibility_recovery(arms_visible, timestamp)
        if arms_visible:
            self._start_calibration_if_needed(timestamp)
        self._finish_calibration_if_ready(timestamp)
        signal_metrics = self._signal_metrics(sides, timestamp)
        status = "ok" if any(side.visible for side in sides.values()) else "arms_not_visible"
        if status == "ok" and self.calibration_state == "calibrating":
            status = "calibrating"

        return MotionAnalysisPayload(
            status=status,
            signature=signature,
            tokens=tokens,
            sides=sides,
            body=body_motion,
            signal_metrics=signal_metrics,
            note=(
                "2D camera signals are normalized through session calibration. "
                "ESP32/IMU and wearable data add complementary signals without changing model code."
            ),
        ).as_payload()

    def _torso_scale(self, pose: PoseCandidate) -> float:
        """Estimate a body-size normalization factor in pixels."""

        distances: list[float] = []
        for side in SIDES:
            shoulder = get_point(pose, "shoulder", side, self.min_confidence)
            hip = get_point(pose, "hip", side, self.min_confidence)
            if shoulder is not None and hip is not None:
                distances.append(_safe_norm(shoulder - hip))
        return max(float(np.mean(distances)) if distances else self.config.fallback_torso_scale_px, 1.0)

    def _torso_center(self, pose: PoseCandidate) -> np.ndarray | None:
        """Average visible shoulder/hip points for body motion."""

        points: list[np.ndarray] = []
        for side in SIDES:
            for joint in ("shoulder", "hip"):
                point = get_point(pose, joint, side, self.min_confidence)
                if point is not None:
                    points.append(point)
        if not points:
            return None
        return np.mean(points, axis=0)

    def _analyze_side(
        self,
        pose: PoseCandidate,
        side: str,
        torso_scale: float,
        left_shoulder: np.ndarray | None,
        right_shoulder: np.ndarray | None,
        body_context: dict[str, Any],
        timestamp: float,
    ) -> SideMotion:
        """Analyze pose visibility, arm position, dumbbell load, and motion for one side."""

        shoulder = get_point(pose, "shoulder", side, self.min_confidence)
        elbow = get_point(pose, "elbow", side, self.min_confidence)
        wrist = get_point(pose, "wrist", side, self.min_confidence)
        hip = get_point(pose, "hip", side, self.min_confidence)
        visible = shoulder is not None and elbow is not None and wrist is not None
        confidence = average_confidence(pose, ("shoulder", "elbow", "wrist"), side, self.min_confidence)
        z_distance = self._side_z_distance(body_context, side)

        if not visible:
            return SideMotion(
                side=side,
                visible=False,
                confidence=confidence,
                wrist=_round_point(wrist),
                elbow_angle=None,
                shoulder_angle=None,
                angle_range_deg=None,
                arm_extension=None,
                height_signal=None,
                reach_signal=None,
                range_utilization=None,
                height_zone="unknown",
                reach_zone="unknown",
                elbow_state="unknown",
                loaded=self._loaded_state(body_context, side),
                z_distance=z_distance,
                height_score=0.0,
                motion_direction="unknown",
                motion_speed=0.0,
                motion_delta=[0.0, 0.0],
                tokens=[],
            )

        # Upper-body webcam framing often hides the hips. When that happens we
        # estimate a hip point below the shoulder so arm-height primitives still
        # work. The payload remains a camera estimate, not biomechanical truth.
        height_reference_hip = hip if hip is not None else shoulder + np.array([0.0, torso_scale])
        self.side_history[side].append((timestamp, wrist))
        first_time, first_wrist = self.side_history[side][0]
        elapsed = max(timestamp - first_time, 1e-6)
        delta = (wrist - first_wrist) / torso_scale
        speed = _safe_norm(delta) / elapsed

        elbow_angle = calculate_angle(shoulder, elbow, wrist)
        shoulder_angle = calculate_angle(hip, shoulder, elbow) if hip is not None else None
        height_zone = _height_zone(wrist, shoulder, height_reference_hip, torso_scale, self.config)
        reach_zone = _reach_zone(side, wrist, left_shoulder, right_shoulder, torso_scale, self.config)
        elbow_state = _elbow_state(elbow_angle, self.config)
        loaded = self._loaded_state(body_context, side)
        shoulder_to_hip = max(float(height_reference_hip[1] - shoulder[1]), 1.0)
        height_score = float(
            np.clip((height_reference_hip[1] - wrist[1]) / shoulder_to_hip, 0.0, self.config.max_height_score)
            / self.config.max_height_score
        )
        reach_x = float((wrist[0] - shoulder[0]) / torso_scale)
        # Bounds only ever widen (CalibrationFeature.update never shrinks an
        # existing min/max), so it is safe to keep observing after the
        # initial warm-up window locks in the "tracking" status label. This
        # lets range-of-motion signals keep expanding instead of clamping at
        # 0.0/1.0 for the rest of the session once a user moves beyond what
        # they happened to demonstrate in the first few seconds.
        self._update_calibration(side, elbow_angle, height_score, reach_x)
        direction = _direction_from_delta(delta, self.config.direction_threshold)
        tokens = self._side_tokens(side, height_zone, reach_zone, elbow_state, loaded, direction)
        if elbow_angle is not None:
            self.angle_history[side].append((timestamp, elbow_angle))
        angle_range = self._side_rom(side)
        arm_extension = self._normalise_signal(side, "elbow_angle", elbow_angle)
        height_signal = self._normalise_signal(side, "height_score", height_score)
        reach_signal = self._normalise_signal(side, "reach_x", reach_x)
        range_utilization = self._range_utilization(side, angle_range)

        return SideMotion(
            side=side,
            visible=True,
            confidence=confidence,
            wrist=_round_point(wrist),
            elbow_angle=elbow_angle,
            shoulder_angle=shoulder_angle,
            angle_range_deg=angle_range,
            arm_extension=arm_extension,
            height_signal=height_signal,
            reach_signal=reach_signal,
            range_utilization=range_utilization,
            height_zone=height_zone,
            reach_zone=reach_zone,
            elbow_state=elbow_state,
            loaded=loaded,
            z_distance=z_distance,
            height_score=height_score,
            motion_direction=direction,
            motion_speed=speed,
            motion_delta=[float(delta[0]), float(delta[1])],
            tokens=tokens,
        )

    def _side_rom(self, side: str) -> float:
        """Return observed active elbow range of motion in the rolling window."""

        angles = [angle for _, angle in self.angle_history[side]]
        if len(angles) < 2:
            return 0.0
        return float(max(angles) - min(angles))

    def _start_calibration_if_needed(self, timestamp: float) -> None:
        """Start calibration only after a complete arm chain is available."""

        if self.calibration_started_at is None:
            self.calibration_started_at = timestamp
            self.calibration_state = "calibrating"

    def _update_visibility_recovery(self, visible: bool, timestamp: float) -> None:
        """Restart acquisition after a sustained loss of usable arm landmarks."""

        if visible:
            self.loss_started_at = None
            return
        if self.calibration_state == "waiting_for_pose":
            return
        if self.loss_started_at is None:
            self.loss_started_at = timestamp
            return
        if timestamp - self.loss_started_at >= self.config.reacquire_timeout_seconds:
            self.reset()

    def _update_calibration(
        self,
        side: str,
        elbow_angle: float | None,
        height_score: float | None,
        reach_x: float | None,
    ) -> None:
        """Record per-user signal bounds during the calibration phase."""

        self.calibration_bounds[side]["elbow_angle"] = self.calibration_bounds[side]["elbow_angle"].update(elbow_angle)
        self.calibration_bounds[side]["height_score"] = self.calibration_bounds[side]["height_score"].update(height_score)
        self.calibration_bounds[side]["reach_x"] = self.calibration_bounds[side]["reach_x"].update(reach_x)
        self.side_calibration_samples[side] += 1

    def _finish_calibration_if_ready(self, timestamp: float) -> None:
        """Lock calibration after the configured warm-up window has elapsed."""

        if self.calibration_started_at is None or self.calibration_state == "tracking":
            return
        elapsed = timestamp - self.calibration_started_at
        total_samples = sum(self.side_calibration_samples.values())
        if elapsed >= self.config.calibration_seconds and total_samples >= self.config.calibration_min_samples:
            self.calibration_state = "tracking"

    def _calibration_elapsed(self, timestamp: float) -> float:
        """Return seconds since calibration started."""

        if self.calibration_started_at is None:
            return 0.0
        return max(0.0, float(timestamp - self.calibration_started_at))

    def _normalise_signal(self, side: str, key: str, value: float | None) -> float | None:
        """Normalize a raw per-side signal using the current session bounds."""

        feature = self.calibration_bounds[side][key]
        return feature.normalise(value, self.config.calibration_min_span)

    def _range_utilization(self, side: str, angle_range: float | None) -> float | None:
        """Normalize rolling angle range against the user's calibrated angle span."""

        feature = self.calibration_bounds[side]["elbow_angle"]
        span = feature.span
        if angle_range is None or span is None or abs(span) < self.config.calibration_min_span:
            return None
        return _clamp01(angle_range / span)

    def _empty_signal_metrics(self, status: str, timestamp: float) -> dict[str, Any]:
        """Return a stable signal section when pose data is unavailable."""

        return {
            "status": status,
            "calibration": self._calibration_payload(timestamp),
            "sides": {},
            "bilateral": {
                "symmetry_score": None,
                "range_symmetry_score": None,
                "speed_symmetry_score": None,
            },
            "note": "Signal metrics require visible shoulder, elbow, and wrist keypoints.",
        }

    def _signal_metrics(self, sides: dict[str, SideMotion], timestamp: float) -> dict[str, Any]:
        """Build normalized sensor-fusion signals for logging and future mapping."""

        side_payloads: dict[str, dict[str, Any]] = {}
        for side in SIDES:
            signal = sides[side]
            side_payloads[side] = {
                "visible": signal.visible,
                "elbow_angle_deg": None
                if signal.elbow_angle is None
                else round(signal.elbow_angle, 2),
                "angle_range_deg": None
                if signal.angle_range_deg is None
                else round(signal.angle_range_deg, 2),
                "arm_extension": None if signal.arm_extension is None else round(signal.arm_extension, 3),
                "height_signal": None if signal.height_signal is None else round(signal.height_signal, 3),
                "reach_signal": None if signal.reach_signal is None else round(signal.reach_signal, 3),
                "range_utilization": None
                if signal.range_utilization is None
                else round(signal.range_utilization, 3),
                "movement_speed": round(signal.motion_speed, 4),
                "loaded": signal.loaded,
            }

        left = sides["left"]
        right = sides["right"]
        range_score = _ratio_score(left.angle_range_deg, right.angle_range_deg)
        speed_score = _ratio_score(left.motion_speed, right.motion_speed)
        available_scores = [score for score in (range_score, speed_score) if score is not None]
        symmetry_score = float(np.mean(available_scores)) if available_scores else None

        return {
            "status": "ok" if any(side.visible for side in sides.values()) else "arms_not_visible",
            "calibration": self._calibration_payload(timestamp),
            "sides": side_payloads,
            "bilateral": {
                "symmetry_score": None if symmetry_score is None else round(symmetry_score, 3),
                "range_symmetry_score": None if range_score is None else round(range_score, 3),
                "speed_symmetry_score": None if speed_score is None else round(speed_score, 3),
                "interpretation": "1.0 means matched left/right signal behavior; lower values indicate asymmetry.",
            },
            "note": (
                "Signals are normalized from the user's own calibration window, "
                "so the same output contract works across different ability levels."
            ),
        }

    def _calibration_payload(self, timestamp: float) -> dict[str, Any]:
        """Return the current calibration state and observed per-side bounds."""

        elapsed = self._calibration_elapsed(timestamp)
        return {
            "state": self.calibration_state,
            "elapsed_seconds": round(elapsed, 2),
            "target_seconds": round(self.config.calibration_seconds, 2),
            "complete": self.calibration_state == "tracking",
            "instruction": (
                "Move into view so both arm chains can be acquired."
                if self.calibration_state == "waiting_for_pose"
                else "Move through your comfortable range."
                if self.calibration_state == "calibrating"
                else "Signals are normalized from the locked session bounds."
            ),
            "sides": {
                side: {
                    "samples": self.side_calibration_samples[side],
                    "bounds": {
                        name: feature.as_payload()
                        for name, feature in self.calibration_bounds[side].items()
                    },
                }
                for side in SIDES
            },
        }

    def _loaded_state(self, body_context: dict[str, Any], side: str) -> bool | None:
        """Return whether a dumbbell appears linked to this side.

        ``None`` means the object detector was not run, so the camera cannot
        confirm whether a dumbbell is present.
        """

        object_status = body_context.get("object_detection", {}).get("status")
        if object_status == "not_run" or object_status is None:
            return None
        side_context = body_context.get("limbs", {}).get("sides", {}).get(side, {})
        return bool(side_context.get("dumbbell_near_wrist_or_forearm", False))

    def _side_z_distance(self, body_context: dict[str, Any], side: str) -> float | None:
        """Return the pseudo-depth for the dumbbell nearest to one side."""

        side_context = body_context.get("limbs", {}).get("sides", {}).get(side, {})
        nearest_weight = side_context.get("nearest_weight") or {}
        raw_value = nearest_weight.get("z_distance")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        return value if value >= 0.0 else None

    def _side_tokens(
        self,
        side: str,
        height_zone: str,
        reach_zone: str,
        elbow_state: str,
        loaded: bool | None,
        direction: str,
    ) -> list[str]:
        """Create readable primitive tokens for one side."""

        tokens = [f"{side}_arm_{height_zone}", f"{side}_arm_{elbow_state}"]
        if reach_zone not in {"unknown", "centerline"}:
            tokens.append(f"{side}_arm_{reach_zone}")
        if loaded is True:
            tokens.append(f"{side}_dumbbell_loaded")
        elif loaded is False:
            tokens.append(f"{side}_dumbbell_not_loaded")
        if direction != "steady" and direction != "unknown":
            tokens.append(f"{side}_wrist_moving_{direction}")
        if height_zone in {"shoulder_height", "torso_height"} and elbow_state == "extended":
            tokens.append(f"{side}_front_hold_candidate")
        return tokens

    def _analyze_body_motion(self, pose: PoseCandidate, torso_scale: float) -> BodyMotion:
        """Estimate whole-body vertical motion for jump-like game actions."""

        position = self._infer_body_position(pose, torso_scale)
        if len(self.body_history) < 2:
            return BodyMotion(position=position)
        first_time, first_center = self.body_history[0]
        current_time, current_center = self.body_history[-1]
        elapsed = max(current_time - first_time, 1e-6)
        delta_y = float((first_center[1] - current_center[1]) / torso_scale)
        speed = abs(delta_y) / elapsed
        if delta_y > self.config.body_motion_threshold:
            direction = "up"
        elif delta_y < -self.config.body_motion_threshold:
            direction = "down"
        else:
            direction = "steady"
        return BodyMotion(
            vertical_delta=delta_y,
            vertical_speed=speed,
            motion_direction=direction,
            jump_candidate=delta_y > self.config.jump_delta_threshold and speed > self.config.jump_speed_threshold,
            position=position,
        )

    def _infer_body_position(self, pose: PoseCandidate, torso_scale: float) -> str:
        """Infer a seated/standing state from visible lower-body geometry.

        The game is designed for upper-body camera framing. If the lower body is
        outside the frame, the safest deterministic assumption for this session is
        seated; a visible hip-to-knee separation identifies a standing posture.
        """

        hips = [get_point(pose, "hip", side, self.min_confidence) for side in SIDES]
        knees = [get_point(pose, "knee", side, self.min_confidence) for side in SIDES]
        visible_pairs = [(hip, knee) for hip, knee in zip(hips, knees) if hip is not None and knee is not None]
        if visible_pairs:
            normalized_gap = float(np.mean([(knee[1] - hip[1]) / max(torso_scale, 1.0) for hip, knee in visible_pairs]))
            if normalized_gap >= 0.68:
                return "standing"
            if normalized_gap <= 0.48:
                return "seated"
        if any(hip is not None for hip in hips):
            return "seated_assumed"
        return "unknown"

    def _combination_tokens(self, sides: dict[str, SideMotion]) -> list[str]:
        """Create tokens that require both arms."""

        left = sides["left"]
        right = sides["right"]
        tokens: list[str] = []
        if left.loaded is True and right.loaded is True:
            tokens.append("both_dumbbells_loaded")
        if left.height_zone == "overhead" and right.height_zone == "overhead":
            tokens.append("both_arms_overhead")
        if left.height_zone in {"shoulder_height", "torso_height"} and right.height_zone in {
            "shoulder_height",
            "torso_height",
        }:
            if left.elbow_state == "extended" and right.elbow_state == "extended":
                tokens.append("both_arms_front_hold_candidate")
        if left.height_zone == "overhead" and right.height_zone in {"shoulder_height", "torso_height"}:
            tokens.append("left_overhead_right_front_candidate")
        if right.height_zone == "overhead" and left.height_zone in {"shoulder_height", "torso_height"}:
            tokens.append("right_overhead_left_front_candidate")
        return tokens

    def _signature(self, sides: dict[str, SideMotion], body_motion: BodyMotion) -> str:
        """Build a compact human-readable movement signature."""

        parts: list[str] = []
        for side in SIDES:
            signal = sides[side]
            if not signal.visible:
                parts.append(f"{side}:not_visible")
                continue
            load = "loaded" if signal.loaded is True else "unloaded" if signal.loaded is False else "load_unknown"
            parts.append(
                f"{side}:{signal.height_zone}:{signal.reach_zone}:{signal.elbow_state}:{load}:{signal.motion_direction}"
            )
        if body_motion.jump_candidate:
            parts.append("body:jump_candidate")
        return " | ".join(parts)
