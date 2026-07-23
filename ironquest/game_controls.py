"""Build the universal sensor-fusion payload for future interactions.

The project is a Computer Science sensor-fusion engine. It converts raw physical
inputs into normalized digital signals, without assigning user-condition labels and
without requiring code changes for different user ability levels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SIDES = ("left", "right")

# Events that describe a discrete physical occurrence (a jump, an IMU burst)
# rather than a continuous status (e.g. CALIBRATING). Only these are subject
# to rising-edge debouncing in EventDebouncer.resolve_events.
_EDGE_TRIGGERED_EVENTS = frozenset({"BODY_JUMP_CANDIDATE", "IMU_MOTION_BURST"})


@dataclass
class EventDebouncer:
    """Stabilize frame-by-frame exercise-candidate and event flicker.

    ``build_game_control_payload`` is otherwise a pure function evaluated
    fresh every frame. A signal sitting near a threshold can flip the
    reported exercise candidate frame-to-frame, and a single physical jump or
    IMU burst can otherwise be reported on every frame the condition holds.
    This is the one piece of state a caller keeps alive across frames for one
    session, the same instantiate-once-per-session pattern already used for
    ``MotionAnalyzer``/``ObjectTemporalTracker`` in ``cli.py``.
    """

    hold_frames: int = 3
    _pending_id: str | None = field(default=None, init=False, repr=False)
    _pending_streak: int = field(default=0, init=False, repr=False)
    _confirmed: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _previous_edge_events: set[str] = field(default_factory=set, init=False, repr=False)

    def resolve_candidate(self, candidate: dict[str, Any] | None) -> dict[str, Any] | None:
        """Only switch the confirmed candidate after it holds for N frames."""

        candidate_id = candidate.get("id") if candidate else None
        if candidate_id == self._pending_id:
            self._pending_streak += 1
        else:
            self._pending_id = candidate_id
            self._pending_streak = 1
        if self._pending_streak >= self.hold_frames:
            self._confirmed = candidate
        return self._confirmed

    def resolve_events(self, events: list[str]) -> list[str]:
        """Report edge-triggered events once per rising edge, not every frame."""

        current_edge_events = {event for event in events if event in _EDGE_TRIGGERED_EVENTS}
        rising = current_edge_events - self._previous_edge_events
        self._previous_edge_events = current_edge_events
        return [event for event in events if event not in _EDGE_TRIGGERED_EVENTS or event in rising]

    def reset(self) -> None:
        """Clear session state, e.g. after a browser calibrate/reset action."""

        self._pending_id = None
        self._pending_streak = 0
        self._confirmed = None
        self._previous_edge_events = set()


def build_game_control_payload(
    motion_analysis: dict[str, Any],
    movement_payload: dict[str, Any],
    esp32_payload: dict[str, Any] | None = None,
    wearable_payload: dict[str, Any] | None = None,
    esp32_side: str = "right",
    wearable_side: str = "left",
    debouncer: EventDebouncer | None = None,
) -> dict[str, Any]:
    """Build one frame of normalized sensor-fusion state.

    The default hardware arrangement is intentionally asymmetric: an ESP32+IMU
    gym glove on one hand and a Garmin watch on the other. Both sides still get
    camera-derived pose and dumbbell association signals. Pass the same
    ``EventDebouncer`` instance across frames in one session to stabilize the
    exercise candidate and edge-triggered events; omitting it keeps this
    function's previous stateless, per-frame behavior.
    """

    esp32_payload = esp32_payload or {"status": "not_configured"}
    wearable_payload = wearable_payload or {"status": "not_configured"}
    esp32_side = _valid_side(_side_from_esp32(esp32_payload) or esp32_side, "right")
    wearable_side = _valid_side(wearable_side, "left")
    signal_metrics = motion_analysis.get("signal_metrics", {})
    user_state = _user_state(wearable_payload, wearable_side=wearable_side)
    esp32_glove = _esp32_glove(esp32_payload, mounted_side=esp32_side)
    arm_signals = _arm_signals(motion_analysis, movement_payload, esp32_glove, wearable_payload, esp32_side, wearable_side)
    axes = _axes(motion_analysis, movement_payload, esp32_glove, user_state, signal_metrics)

    exercise_candidate = _exercise_candidate(motion_analysis)
    events = _events(motion_analysis, esp32_glove)
    if debouncer is not None:
        exercise_candidate = debouncer.resolve_candidate(exercise_candidate)
        events = debouncer.resolve_events(events)

    return {
        "status": _status(motion_analysis),
        "control_mode": "sensor_fusion_engine",
        "schema_version": "2026-08-fusion-v2",
        "tokens": list(dict.fromkeys(motion_analysis.get("tokens", []))),
        "exercise_candidate": exercise_candidate,
        "axes": axes,
        "events": events,
        "body_posture": _body_posture(motion_analysis),
        "dumbbells": _dumbbell_boxes(movement_payload),
        "arm_signals": arm_signals,
        "esp32_glove": esp32_glove,
        "wearable_watch": _wearable_watch(wearable_payload, mounted_side=wearable_side, user_state=user_state),
        "user_state": user_state,
        "signal_metrics": signal_metrics,
        "calibration": signal_metrics.get("calibration", {}) if isinstance(signal_metrics, dict) else {},
        "sensor_status": {
            "vision": motion_analysis.get("status", "unknown"),
            "esp32_glove": esp32_payload.get("status", "unknown"),
            "wearable_watch": wearable_payload.get("status", "unknown"),
        },
        "mapping_note": (
            "Universal normalized signals for future interaction mapping. "
            "No heart-rate value is treated as a hard stop by this layer."
        ),
    }


def _exercise_candidate(motion_analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Expose the system's current movement candidate to presentation clients.

    The candidate is derived only from the existing calibrated pose, reach,
    elbow, and load signals. The browser does not classify arbitrary camera
    frames or invent an exercise; it receives this small, optional hint from
    the sensor-fusion layer and renders the matching interaction.
    """

    tokens = {str(token).lower() for token in motion_analysis.get("tokens", [])}
    if {"left_overhead_right_front_candidate", "right_overhead_left_front_candidate"} & tokens:
        return {"id": "combo", "confidence": 0.86, "source": "movement_signature"}
    if "both_arms_overhead" in tokens:
        return {"id": "double_press", "confidence": 0.84, "source": "movement_signature"}
    if "both_arms_front_hold_candidate" in tokens:
        return {"id": "front_hold", "confidence": 0.82, "source": "movement_signature"}
    if {"left_arm_overhead", "right_arm_overhead"} & tokens:
        return {"id": "press", "confidence": 0.76, "source": "movement_signature"}
    if {"left_front_hold_candidate", "right_front_hold_candidate"} & tokens:
        return {"id": "front_raise", "confidence": 0.72, "source": "movement_signature"}
    if {"left_dumbbell_loaded", "right_dumbbell_loaded", "both_dumbbells_loaded"} & tokens:
        return {"id": "curl", "confidence": 0.68, "source": "movement_signature"}
    return None


def _status(motion_analysis: dict[str, Any]) -> str:
    """Translate analysis status into middleware readiness."""

    status = motion_analysis.get("status")
    if status == "ok":
        return "ready"
    if status == "calibrating":
        return "calibrating"
    return "waiting_for_pose"


def _body_posture(motion_analysis: dict[str, Any]) -> dict[str, Any]:
    """Return camera-derived posture arrays and side summaries."""

    sides = motion_analysis.get("sides", {})
    side_payloads: dict[str, Any] = {}
    posture_array: list[dict[str, Any]] = []
    for side in SIDES:
        payload = sides.get(side, {})
        side_payloads[side] = {
            "visible": bool(payload.get("visible", False)),
            "confidence": _safe_float(payload.get("confidence")),
            "wrist_xy": payload.get("wrist"),
            "height_zone": payload.get("height_zone", "unknown"),
            "reach_zone": payload.get("reach_zone", "unknown"),
            "elbow_state": payload.get("elbow_state", "unknown"),
            "motion_direction": payload.get("motion_direction", "unknown"),
            "loaded": payload.get("loaded"),
        }
        posture_array.append(
            {
                "side": side,
                "wrist_xy": payload.get("wrist"),
                "elbow_angle_deg": payload.get("elbow_angle"),
                "shoulder_angle_deg": payload.get("shoulder_angle"),
                "angle_range_deg": payload.get("angle_range_deg"),
                "arm_extension": payload.get("arm_extension"),
                "height_signal": payload.get("height_signal"),
                "reach_signal": payload.get("reach_signal"),
                "range_utilization": payload.get("range_utilization"),
                "motion_delta_xy": payload.get("motion_delta", [0.0, 0.0]),
            }
        )

    return {
        "status": motion_analysis.get("status", "unknown"),
        "signature": motion_analysis.get("signature", "unknown"),
        "sides": side_payloads,
        "posture_array": posture_array,
        "body": motion_analysis.get("body", {}),
        "source": "YOLO26 body pose plus session-calibrated motion signals",
    }


def _arm_signals(
    motion_analysis: dict[str, Any],
    movement_payload: dict[str, Any],
    esp32_glove: dict[str, Any],
    wearable_payload: dict[str, Any],
    esp32_side: str,
    wearable_side: str,
) -> dict[str, Any]:
    """Fuse pose, object association, and asymmetric hardware by side."""

    sides = motion_analysis.get("sides", {})
    associations = _dumbbell_boxes(movement_payload).get("associations", {})
    fused: dict[str, Any] = {}
    for side in SIDES:
        pose = sides.get(side, {})
        hardware: dict[str, Any] = {}
        if side == esp32_side:
            hardware["esp32_glove"] = esp32_glove
        if side == wearable_side:
            hardware["wearable_watch"] = {
                "status": wearable_payload.get("status", "not_configured"),
                "device": wearable_payload.get("device", "garmin_venu_3"),
                "heart_rate_bpm": wearable_payload.get("heart_rate_bpm"),
                "heart_rate_contact": wearable_payload.get("heart_rate_contact"),
                "mounted_side": wearable_side,
                "watch_motion_state": wearable_payload.get("watch_motion_state"),
                "watch_motion_delta_mg": wearable_payload.get("watch_motion_delta_mg"),
                "acceleration_magnitude_mg": wearable_payload.get("acceleration_magnitude_mg"),
                "acceleration_unit": wearable_payload.get("acceleration_unit"),
            }
        fused[side] = {
            "pose": {
                "visible": bool(pose.get("visible", False)),
                "arm_extension": pose.get("arm_extension"),
                "height_signal": pose.get("height_signal"),
                "reach_signal": pose.get("reach_signal"),
                "range_utilization": pose.get("range_utilization"),
                "motion_speed": pose.get("motion_speed"),
                "motion_direction": pose.get("motion_direction"),
            },
            "dumbbell": associations.get(side, {}),
            "hardware": hardware,
            "available_signal_sources": [
                name
                for name, available in {
                    "camera_pose": bool(pose.get("visible", False)),
                    "dumbbell_detector": bool(associations.get(side)),
                    "esp32_glove": side == esp32_side and esp32_glove.get("status") != "not_configured",
                    "wearable_watch": side == wearable_side and wearable_payload.get("status") != "not_configured",
                }.items()
                if available
            ],
        }
    return fused


def _dumbbell_boxes(movement_payload: dict[str, Any]) -> dict[str, Any]:
    """Return accepted dumbbell/weight boxes and left/right association."""

    object_payload = movement_payload.get("object_detection", {})
    limbs_payload = movement_payload.get("limbs", {})
    boxes: list[dict[str, Any]] = []
    for index, detection in enumerate(object_payload.get("detections", [])):
        boxes.append(
            {
                "index": index,
                "label": detection.get("label"),
                "confidence": detection.get("confidence"),
                "xyxy": detection.get("xyxy"),
                "center_xy": detection.get("center"),
                "track_id": detection.get("track_id"),
                "tracking_state": detection.get("tracking_state"),
            }
        )

    associations: dict[str, Any] = {}
    for side in SIDES:
        side_payload = limbs_payload.get("sides", {}).get(side, {})
        nearest = side_payload.get("nearest_weight")
        associations[side] = {
            "loaded": bool(side_payload.get("dumbbell_near_wrist_or_forearm", False)),
            "nearest_box_index": None if not isinstance(nearest, dict) else nearest.get("candidate_index"),
            "nearest_distance_px": None if not isinstance(nearest, dict) else nearest.get("distance"),
            "pseudo_depth": None if not isinstance(nearest, dict) else nearest.get("z_distance"),
        }

    return {
        "status": object_payload.get("status", "not_run"),
        "boxes": boxes,
        "associations": associations,
        "accepted_count": object_payload.get("accepted_count", len(boxes)),
    }


def _esp32_glove(esp32_payload: dict[str, Any], mounted_side: str) -> dict[str, Any]:
    """Return the latest ESP32 glove sample in universal signal language."""

    status = str(esp32_payload.get("status", "not_configured")).lower()
    latest = esp32_payload.get("latest") if isinstance(esp32_payload.get("latest"), dict) else {}
    has_live_sample = status == "connected" and bool(latest)
    if not has_live_sample:
        latest = {}
    motion_delta = _optional_float(latest.get("motion_delta_mps2", latest.get("accel_delta_mps2")))
    angular_delta = _optional_float(latest.get("angular_delta_dps", latest.get("gyro_delta_dps")))
    orientation_delta = _optional_float(latest.get("orientation_delta_deg"))
    sample_interval_ms = _optional_float(latest.get("sample_interval_ms"))
    motion_intensity = _imu_motion_intensity(motion_delta, angular_delta, orientation_delta) if has_live_sample else None
    motion_state = _imu_motion_state(motion_intensity) if motion_intensity is not None else (
        "stale" if status == "stale" else "waiting"
    )
    return {
        "status": status,
        "transport": esp32_payload.get("transport", "serial" if esp32_payload.get("port") else None),
        "transport_summary": esp32_payload.get("transport_summary"),
        "connected_transports": esp32_payload.get("connected_transports", []),
        "sources": esp32_payload.get("sources", {}),
        "remote": esp32_payload.get("remote"),
        "mounted_side": mounted_side,
        "device_id": latest.get("device_id"),
        "mount": latest.get("mount", "gym_glove"),
        "timestamp_ms": latest.get("timestamp_ms"),
        "orientation_euler_deg": latest.get("orientation_euler_deg")
        or {"pitch": None, "roll": None, "yaw": None},
        "quaternion": latest.get("quaternion"),
        "accel_mps2": latest.get("accel_mps2"),
        "gyro_dps": latest.get("gyro_dps"),
        "motion_delta_mps2": motion_delta,
        "angular_delta_dps": angular_delta,
        "orientation_delta_deg": orientation_delta,
        "motion_intensity": motion_intensity,
        "rotation_intensity": None if angular_delta is None else _clamp01(angular_delta / 120.0),
        "motion_state": motion_state,
        "stability_index": latest.get("stability_index"),
        "sample_interval_ms": sample_interval_ms,
        "sample_rate_hz": None if not sample_interval_ms or sample_interval_ms <= 0 else round(1000.0 / sample_interval_ms, 2),
        "sequence": latest.get("sequence"),
        "sample_age_seconds": esp32_payload.get("sample_age_seconds"),
        "source": "ESP32 USB/Wi-Fi JSON from gym glove IMU",
    }


def _wearable_watch(
    wearable_payload: dict[str, Any],
    mounted_side: str,
    user_state: dict[str, Any],
) -> dict[str, Any]:
    """Return the Garmin watch sample without interpreting it as a hard constraint."""

    return {
        "status": wearable_payload.get("status", "not_configured"),
        "mounted_side": mounted_side,
        "device": wearable_payload.get("device", "garmin_venu_3"),
        "device_name": wearable_payload.get("device_name"),
        "device_address": wearable_payload.get("device_address"),
        "provider": wearable_payload.get("provider", "garmin"),
        "sample_type": wearable_payload.get("sample_type", "ble_heart_rate"),
        "heart_rate_bpm": wearable_payload.get("heart_rate_bpm"),
        "heart_rate_contact": wearable_payload.get("heart_rate_contact"),
        "resting_heart_rate_bpm": wearable_payload.get("resting_heart_rate_bpm"),
        "max_heart_rate_bpm": wearable_payload.get("max_heart_rate_bpm"),
        "rr_intervals_ms": wearable_payload.get("rr_intervals_ms"),
        "energy_expended_kj": wearable_payload.get("energy_expended_kj"),
        "stress": wearable_payload.get("stress"),
        "body_battery": wearable_payload.get("body_battery"),
        "respiration_rate": wearable_payload.get("respiration_rate"),
        "pulse_ox": wearable_payload.get("pulse_ox"),
        "steps": wearable_payload.get("steps"),
        "calories": wearable_payload.get("calories"),
        "hrv_ms": wearable_payload.get("hrv_ms"),
        "exertion_level": user_state.get("exertion_level"),
        "intensity_zone": user_state.get("intensity_zone"),
        "activity_state": wearable_payload.get("activity_state"),
        "battery": wearable_payload.get("battery"),
        "battery_unit": wearable_payload.get("battery_unit"),
        "acceleration": wearable_payload.get("acceleration"),
        "acceleration_unit": wearable_payload.get("acceleration_unit"),
        "acceleration_magnitude_mg": wearable_payload.get("acceleration_magnitude_mg"),
        "watch_motion_delta_mg": wearable_payload.get("watch_motion_delta_mg"),
        "watch_motion_state": wearable_payload.get("watch_motion_state"),
        "gyroscope": wearable_payload.get("gyroscope"),
        "gyroscope_unit": wearable_payload.get("gyroscope_unit"),
        "location": wearable_payload.get("location"),
        "latitude": wearable_payload.get("latitude"),
        "longitude": wearable_payload.get("longitude"),
        "altitude_m": wearable_payload.get("altitude_m"),
        "speed_mps": wearable_payload.get("speed_mps"),
        "distance_m": wearable_payload.get("distance_m"),
        "heading_deg": wearable_payload.get("heading_deg"),
        "timestamp": wearable_payload.get("timestamp"),
        "received_at": wearable_payload.get("received_at"),
        "source": wearable_payload.get("source"),
        "ingest_source": wearable_payload.get("ingest_source"),
        "sequence": wearable_payload.get("sequence"),
        "sent_count": wearable_payload.get("sent_count"),
        "sample_interval_ms": wearable_payload.get("sample_interval_ms"),
        "age_seconds": wearable_payload.get("age_seconds"),
        "sample_age_seconds": wearable_payload.get("sample_age_seconds"),
        "endpoint_mode": wearable_payload.get("endpoint_mode"),
        "last_http_code": wearable_payload.get("last_http_code"),
    }


def _user_state(wearable_payload: dict[str, Any], wearable_side: str) -> dict[str, Any]:
    """Map wearable physiology into neutral normalized user-state signals."""

    heart_rate = _optional_float(wearable_payload.get("heart_rate_bpm"))
    min_ref = _optional_float(
        wearable_payload.get("resting_heart_rate_bpm", wearable_payload.get("hr_min_bpm"))
    )
    max_ref = _optional_float(
        wearable_payload.get("max_heart_rate_bpm", wearable_payload.get("hr_max_bpm"))
    )
    min_ref = 60.0 if min_ref is None else min_ref
    max_ref = 180.0 if max_ref is None else max(max_ref, min_ref + 1.0)
    exertion_level = None if heart_rate is None else _clamp01((heart_rate - min_ref) / (max_ref - min_ref))

    return {
        "wearable_side": wearable_side,
        "heart_rate_bpm": heart_rate,
        "heart_rate_reference": {
            "min_bpm": round(min_ref, 1),
            "max_bpm": round(max_ref, 1),
            "source": "wearable_payload_or_generic_signal_range",
        },
        "exertion_level": None if exertion_level is None else round(exertion_level, 3),
        "intensity_zone": _intensity_zone(exertion_level),
        "activity_state": wearable_payload.get("activity_state"),
        "note": "Heart rate is exposed as a neutral intensity signal, not as a stop condition.",
    }


def _axes(
    motion_analysis: dict[str, Any],
    movement_payload: dict[str, Any],
    esp32_glove: dict[str, Any],
    user_state: dict[str, Any],
    signal_metrics: dict[str, Any],
) -> dict[str, float]:
    """Keep compact normalized values for the UI and early mapping experiments."""

    sides = motion_analysis.get("sides", {})
    orientation = esp32_glove.get("orientation_euler_deg") if isinstance(esp32_glove.get("orientation_euler_deg"), dict) else {}
    bilateral = signal_metrics.get("bilateral", {}) if isinstance(signal_metrics, dict) else {}
    return {
        "left_arm_extension": _side_axis(sides, "left", "arm_extension"),
        "right_arm_extension": _side_axis(sides, "right", "arm_extension"),
        "left_height_signal": _side_axis(sides, "left", "height_signal"),
        "right_height_signal": _side_axis(sides, "right", "height_signal"),
        "left_range_utilization": _side_axis(sides, "left", "range_utilization"),
        "right_range_utilization": _side_axis(sides, "right", "range_utilization"),
        "left_wrist_speed": _side_axis(sides, "left", "motion_speed"),
        "right_wrist_speed": _side_axis(sides, "right", "motion_speed"),
        "symmetry_score": _safe_float(bilateral.get("symmetry_score")),
        "body_vertical_delta": _safe_float(motion_analysis.get("body", {}).get("vertical_delta")),
        "pose_confidence": _safe_float(movement_payload.get("pose_confidence", movement_payload.get("confidence"))),
        "imu_pitch_deg": _safe_float(orientation.get("pitch")),
        "imu_roll_deg": _safe_float(orientation.get("roll")),
        "imu_yaw_deg": _safe_float(orientation.get("yaw")),
        "imu_motion_intensity": _safe_float(esp32_glove.get("motion_intensity")),
        "imu_rotation_intensity": _safe_float(esp32_glove.get("rotation_intensity")),
        "stability_index": _safe_float(esp32_glove.get("stability_index")),
        "exertion_level": _safe_float(user_state.get("exertion_level")),
    }


def _events(motion_analysis: dict[str, Any], esp32_glove: dict[str, Any]) -> list[str]:
    """Return high-level event labels that do not impose medical decisions."""

    events = []
    if motion_analysis.get("body", {}).get("jump_candidate"):
        events.append("BODY_JUMP_CANDIDATE")
    if motion_analysis.get("status") == "calibrating":
        events.append("CALIBRATING")
    motion_state = esp32_glove.get("motion_state")
    if motion_state == "active":
        events.append("IMU_ACTIVE_MOTION")
    elif motion_state == "burst":
        events.append("IMU_MOTION_BURST")
    return events


def _side_from_esp32(esp32_payload: dict[str, Any]) -> str | None:
    """Infer side from ESP32 mount metadata when firmware provides it."""

    latest = esp32_payload.get("latest") if isinstance(esp32_payload.get("latest"), dict) else {}
    mount = str(latest.get("mount", "")).lower()
    if "left" in mount:
        return "left"
    if "right" in mount:
        return "right"
    return None


def _valid_side(value: Any, default: str) -> str:
    """Return a valid side label."""

    text = str(value).lower()
    return text if text in SIDES else default


def _side_axis(sides: dict[str, Any], side: str, key: str) -> float:
    """Read one side-specific numeric axis with a safe default."""

    return _safe_float(sides.get(side, {}).get(key, 0.0))


def _intensity_zone(exertion_level: float | None) -> str:
    """Convert normalized exertion into neutral zones for dashboards or mapping."""

    if exertion_level is None:
        return "unknown"
    if exertion_level < 0.33:
        return "low"
    if exertion_level < 0.66:
        return "moderate"
    if exertion_level < 0.85:
        return "high"
    return "peak"


def _optional_float(value: Any) -> float | None:
    """Convert optional scalars."""

    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert optional scalar values without crashing on missing sensors."""

    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: float) -> float:
    """Clamp a numeric value to the universal signal interval."""

    return max(0.0, min(1.0, float(value)))


def _imu_motion_intensity(
    motion_delta_mps2: float | None,
    angular_delta_dps: float | None,
    orientation_delta_deg: float | None,
) -> float:
    """Map real BNO08X deltas to a compact 0-1 movement signal.

    The denominators are grounded in the first desk captures: tilt sweeps sit
    around the middle of the range while deliberate motion bursts saturate.
    """

    accel_score = 0.0 if motion_delta_mps2 is None else motion_delta_mps2 / 8.0
    gyro_score = 0.0 if angular_delta_dps is None else angular_delta_dps / 180.0
    orientation_score = 0.0 if orientation_delta_deg is None else orientation_delta_deg / 24.0
    return round(_clamp01(max(accel_score, gyro_score, orientation_score)), 3)


def _imu_motion_state(motion_intensity: float) -> str:
    """Convert normalized IMU movement into a stable dashboard label."""

    if motion_intensity < 0.08:
        return "steady"
    if motion_intensity < 0.28:
        return "small_motion"
    if motion_intensity < 0.72:
        return "active"
    return "burst"
