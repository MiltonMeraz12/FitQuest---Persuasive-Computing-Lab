"""Premium OpenCV HUD rendering for the Iron Quest 3D tracking monitor.

This module is intentionally a monitor, not the future game UI.  The game will
run on a separate display later; this window is the developer-facing sensor and
vision bridge.  Clean mode keeps the camera feed visually dominant, while debug
mode exposes structured control, ESP32/IMU, and wearable telemetry in a fixed
glass panel.

OpenCV uses BGR color order, not RGB.  Every color tuple in this file follows
that convention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .body_context import extract_object_detections
from .keypoints import COCO_KEYPOINTS, PoseCandidate, is_visible


WINDOW_NAME = "Iron Quest 3D - Unified Detector"


@dataclass(frozen=True)
class Rect:
    """Small rectangle helper for consistent OpenCV layout math."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def inset(self, amount: int) -> "Rect":
        return Rect(
            self.x + amount,
            self.y + amount,
            max(0, self.w - amount * 2),
            max(0, self.h - amount * 2),
        )

    def inset_xy(self, x_amount: int, y_amount: int) -> "Rect":
        return Rect(
            self.x + x_amount,
            self.y + y_amount,
            max(0, self.w - x_amount * 2),
            max(0, self.h - y_amount * 2),
        )


@dataclass(frozen=True)
class Theme:
    """Centralized HUD geometry, typography, alpha, and color tokens."""

    margin: int = 18
    padding: int = 16
    gap: int = 12
    radius: int = 12
    top_bar_height: int = 88
    debug_panel_width: int = 520
    clean_panel_alpha: float = 0.58
    debug_panel_alpha: float = 0.76
    caption_scale: float = 0.36
    body_scale: float = 0.45
    value_scale: float = 0.58
    title_scale: float = 0.72
    mono_scale: float = 0.36
    line_height: int = 21
    colors: dict[str, tuple[int, int, int]] = field(
        default_factory=lambda: {
            # Deep neutral base, matching the requested #111111 glass.
            "glass": (17, 17, 17),
            "glass_edge": (64, 73, 82),
            "ink": (5, 7, 10),
            "shadow": (0, 0, 0),
            "text": (244, 248, 252),
            "muted": (156, 166, 176),
            "faint": (86, 96, 108),
            # Neon accents. BGR order: cyan is high blue + high green.
            "cyan": (255, 245, 35),
            "blue": (255, 118, 36),
            "yellow": (32, 245, 255),
            "green": (92, 255, 132),
            "magenta": (255, 82, 242),
            "red": (72, 82, 255),
            "white": (255, 255, 255),
            "bone_left": (48, 228, 255),
            "bone_right": (255, 220, 48),
            "bone_center": (245, 248, 252),
            "target": (38, 244, 255),
            "bar_bg": (42, 48, 56),
        }
    )


THEME = Theme()
COLORS = THEME.colors


@dataclass(frozen=True)
class LetterboxResult:
    """Rendered frame plus the active video viewport inside the output canvas."""

    canvas: np.ndarray
    viewport: Rect


POSE_EDGES = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
]


@dataclass(frozen=True)
class DashboardViewModel:
    """Frame-ready state for the clean HUD and the debug telemetry panel."""

    payload: dict[str, Any]
    detail: str
    debug: bool
    fps: float
    mode: str
    state: str
    state_color: tuple[int, int, int]
    esp32: dict[str, Any]
    esp32_status: str
    esp32_label: str
    esp32_color: tuple[int, int, int]
    wearable: dict[str, Any]
    wearable_status: str
    wearable_label: str
    wearable_color: tuple[int, int, int]
    game_control: dict[str, Any]
    esp32_glove: dict[str, Any]
    axes: dict[str, Any]
    tokens: list[str]
    events: list[str]
    imu_signals: dict[str, Any]
    esp32_vectors: list[tuple[str, str, str, str]]
    esp32_detail: dict[str, Any]
    wearable_signals: dict[str, Any]
    esp32_raw_json: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any], detail: str = "clean") -> "DashboardViewModel":
        """Normalize one detector payload into values that are cheap to draw.

        The renderer should not dig through nested dictionaries repeatedly.
        This view model also enforces the product rule that clean mode never
        exposes raw telemetry or token logs.
        """

        normalized_detail = "debug" if detail == "debug" else "clean"
        game_control = as_dict(payload.get("game_control"))
        esp32 = as_dict(payload.get("esp32"))
        wearable = as_dict(payload.get("wearable"))
        runtime = as_dict(payload.get("runtime"))
        axes = as_dict(game_control.get("axes"))
        esp32_glove = as_dict(game_control.get("esp32_glove"))
        tokens = [str(token) for token in game_control.get("tokens", []) if token is not None]
        events = [str(event) for event in game_control.get("events", []) if event is not None]
        state = operator_state(payload)

        return cls(
            payload=payload,
            detail=normalized_detail,
            debug=normalized_detail == "debug",
            fps=safe_float(runtime.get("fps"), default=0.0),
            mode=str(payload.get("detection_mode", "auto")),
            state=state,
            state_color=operator_color(state),
            esp32=esp32,
            esp32_status=str(esp32.get("status", "not_configured")),
            esp32_label=esp32_sensor_label(esp32),
            esp32_color=sensor_color(esp32.get("status")),
            wearable=wearable,
            wearable_status=str(wearable.get("status", "not_configured")),
            wearable_label=sensor_label(wearable.get("status")),
            wearable_color=sensor_color(wearable.get("status")),
            game_control=game_control,
            esp32_glove=esp32_glove,
            axes=axes,
            tokens=tokens,
            events=events,
            imu_signals=format_imu_signals(esp32_glove, axes),
            esp32_vectors=format_esp32_vectors(esp32),
            esp32_detail=format_esp32_detail(esp32, esp32_glove),
            wearable_signals=format_wearable_signals(wearable, game_control),
            esp32_raw_json=compact_json(esp32.get("latest") or esp32, max_chars=1400),
        )


def as_dict(value: object) -> dict[str, Any]:
    """Return ``value`` when it is a dictionary, otherwise an empty dict."""

    return value if isinstance(value, dict) else {}


def safe_float(value: object, default: float = 0.0) -> float:
    """Parse a float without letting malformed sensor data crash the UI."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def optional_float(value: object) -> float | None:
    """Parse a float and preserve missing/non-numeric values as ``None``."""

    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, low: float, high: float) -> float:
    """Clamp numeric UI values into a closed range."""

    return max(low, min(high, value))


def clamp_rect(rect: Rect, width: int, height: int) -> Rect:
    """Keep a rectangle inside the current frame."""

    x = max(0, min(rect.x, max(0, width - 1)))
    y = max(0, min(rect.y, max(0, height - 1)))
    right = max(x, min(rect.right, width))
    bottom = max(y, min(rect.bottom, height))
    return Rect(x, y, right - x, bottom - y)


def readable_state(value: object) -> str:
    """Convert internal state strings into compact human-readable labels."""

    return str(value or "unknown").replace("_", " ")


def ellipsize(value: object, max_chars: int = 28) -> str:
    """Shorten text before OpenCV draws it past a fixed HUD boundary."""

    text = str(value)
    if len(text) <= max_chars:
        return text
    return f"{text[: max(0, max_chars - 3)]}..."


def format_number(value: object, decimals: int = 1, suffix: str = "", missing: str | None = "--") -> str | None:
    """Return a compact human-facing number label."""

    number = optional_float(value)
    if number is None:
        return missing
    if decimals <= 0:
        text = f"{number:.0f}"
    else:
        text = f"{number:.{decimals}f}"
    return f"{text}{suffix}"


def format_duration(seconds: object, missing: str = "--") -> str:
    """Return a compact age label such as 2.3s, 4m 12s, or 1h 05m."""

    value = optional_float(seconds)
    if value is None:
        return missing
    value = max(0.0, value)
    if value < 10:
        return f"{value:.1f}s"
    if value < 60:
        return f"{value:.0f}s"
    minutes = int(value // 60)
    if minutes < 60:
        return f"{minutes}m {int(value % 60):02d}s"
    hours = minutes // 60
    return f"{hours}h {minutes % 60:02d}m"


def compact_json(value: object, max_chars: int = 900) -> str:
    """Return compact JSON for the debug panel."""

    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        text = json.dumps(str(value))
    if len(text) <= max_chars:
        return text
    return f"{text[: max(0, max_chars - 3)]}..."


def wrap_fixed(text: str, max_chars: int, max_lines: int) -> list[str]:
    """Wrap debug text into a fixed number of non-scrolling lines."""

    if max_chars <= 0 or max_lines <= 0:
        return []
    lines: list[str] = []
    cursor = 0
    while cursor < len(text) and len(lines) < max_lines:
        lines.append(text[cursor : cursor + max_chars])
        cursor += max_chars
    return lines


def sensor_label(status: object) -> str:
    """Return a short LED label for optional hardware sources."""

    status_text = str(status or "not_configured")
    if status_text == "connected":
        return "ONLINE"
    if status_text in {"connected_waiting_for_data", "listening_waiting_for_data"}:
        return "WAITING"
    if status_text in {"connected_non_json_data", "listening_non_json_data", "bad_json"}:
        return "BAD DATA"
    if status_text == "not_configured":
        return "OFFLINE"
    if status_text == "stale":
        return "STALE"
    if status_text == "missing_file":
        return "NO DATA"
    if status_text == "no_serial_port_found":
        return "NO USB"
    if status_text in {
        "serial_disconnected",
        "serial_open_failed",
        "udp_read_failed",
        "udp_bind_failed",
        "read_failed",
        "pyserial_missing",
    }:
        return "RECONNECT"
    return ellipsize(readable_state(status_text).upper(), 12)


def esp32_sensor_label(esp32: dict[str, Any]) -> str:
    """Return a transport-aware label for the ESP32 status chip."""

    if esp32.get("status") != "connected":
        return sensor_label(esp32.get("status"))
    summary = esp32.get("transport_summary")
    if summary:
        return ellipsize(str(summary).upper(), 12)
    transport = str(esp32.get("transport") or "")
    if "udp" in transport:
        return "WIFI"
    if "serial" in transport:
        return "USB"
    return "ONLINE"


def sensor_color(status: object) -> tuple[int, int, int]:
    """Pick a LED color for ESP32 and wearable status."""

    status_text = str(status or "not_configured")
    if status_text == "connected":
        return COLORS["green"]
    if status_text in {"connected_waiting_for_data", "connected_non_json_data"}:
        return COLORS["cyan"]
    if status_text in {"listening_waiting_for_data", "listening_non_json_data"}:
        return COLORS["cyan"]
    if status_text == "not_configured":
        return COLORS["faint"]
    if status_text in {"stale", "missing_file", "bad_json", "no_serial_port_found"}:
        return COLORS["yellow"]
    return COLORS["red"]


def format_esp32_vectors(esp32: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """Extract exact X/Y/Z telemetry rows for the debug panel."""

    if str(esp32.get("status") or "").lower() != "connected":
        return []
    latest = as_dict(esp32.get("latest"))
    rows: list[tuple[str, str, str, str]] = []
    for key, label in (
        ("accel_mps2", "ACCEL"),
        ("gyro_dps", "GYRO"),
        ("magnetometer_ut", "MAG"),
    ):
        vector = as_dict(latest.get(key))
        if not vector:
            continue
        rows.append(
            (
                label,
                f"X {safe_float(vector.get('x')):+.4f}",
                f"Y {safe_float(vector.get('y')):+.4f}",
                f"Z {safe_float(vector.get('z')):+.4f}",
            )
        )
    return rows


def format_imu_signals(esp32_glove: dict[str, Any], axes: dict[str, Any]) -> dict[str, Any]:
    """Extract human-readable IMU control signals for the debug panel."""

    status = str(esp32_glove.get("status") or "unknown").lower()
    transport = esp32_glove.get("transport_summary") or esp32_glove.get("transport") or "serial"
    if status != "connected":
        return {
            "state": "stale" if status == "stale" else "waiting",
            "transport": transport,
            "connected_transports": [],
            "remote": esp32_glove.get("remote"),
            "motion_intensity": None,
            "rotation_intensity": None,
            "stability_index": None,
            "sample_rate_hz": None,
        }

    sample_rate = esp32_glove.get("sample_rate_hz")
    if sample_rate is None:
        interval_ms = safe_float(esp32_glove.get("sample_interval_ms"), default=0.0)
        sample_rate = None if interval_ms <= 0 else round(1000.0 / interval_ms, 2)
    motion_intensity = safe_float(
        esp32_glove.get("motion_intensity", axes.get("imu_motion_intensity")),
        default=-1.0,
    )
    if motion_intensity < 0.0:
        motion_intensity = estimate_imu_motion_intensity(esp32_glove)
    rotation_intensity = safe_float(
        esp32_glove.get("rotation_intensity", axes.get("imu_rotation_intensity")),
        default=-1.0,
    )
    if rotation_intensity < 0.0:
        rotation_intensity = clamp(safe_float(esp32_glove.get("angular_delta_dps")) / 120.0, 0.0, 1.0)
    state = esp32_glove.get("motion_state")
    if not state or state == "unknown":
        state = estimate_imu_motion_state(motion_intensity)
    return {
        "state": state,
        "transport": transport,
        "connected_transports": esp32_glove.get("connected_transports", []),
        "remote": esp32_glove.get("remote"),
        "motion_intensity": motion_intensity,
        "rotation_intensity": rotation_intensity,
        "stability_index": safe_float(esp32_glove.get("stability_index"), default=0.0),
        "sample_rate_hz": sample_rate,
    }


def format_esp32_detail(esp32: dict[str, Any], esp32_glove: dict[str, Any]) -> dict[str, Any]:
    """Return demo-friendly ESP32/IMU details for the debug panel."""

    status = str(esp32.get("status", esp32_glove.get("status", "unknown")) or "unknown").lower()
    latest = as_dict(esp32.get("latest"))
    live_latest = latest if status == "connected" else {}
    orientation = as_dict(esp32_glove.get("orientation_euler_deg") or live_latest.get("orientation_euler_deg"))
    return {
        "status": status,
        "transport": esp32_glove.get("transport_summary") or esp32.get("transport_summary") or esp32_glove.get("transport"),
        "connected_transports": esp32_glove.get("connected_transports") or esp32.get("connected_transports") or [],
        "remote": esp32_glove.get("remote") or esp32.get("remote"),
        "sample_rate_hz": esp32_glove.get("sample_rate_hz"),
        "sample_interval_ms": esp32_glove.get("sample_interval_ms"),
        "sequence": esp32_glove.get("sequence") or live_latest.get("sequence"),
        "motion_delta_mps2": esp32_glove.get("motion_delta_mps2"),
        "angular_delta_dps": esp32_glove.get("angular_delta_dps"),
        "orientation_delta_deg": esp32_glove.get("orientation_delta_deg"),
        "sample_age_seconds": esp32.get("sample_age_seconds") or esp32_glove.get("sample_age_seconds"),
        "pitch": orientation.get("pitch"),
        "roll": orientation.get("roll"),
        "yaw": orientation.get("yaw"),
        "battery_v": live_latest.get("battery_v"),
        "temperature_c": live_latest.get("temperature_c"),
    }


def format_wearable_signals(wearable: dict[str, Any], game_control: dict[str, Any]) -> dict[str, Any]:
    """Return demo-friendly Garmin/smartwatch context for the debug panel."""

    watch = as_dict(game_control.get("wearable_watch"))
    user_state = as_dict(game_control.get("user_state"))
    rr_intervals = wearable.get("rr_intervals_ms") or watch.get("rr_intervals_ms") or []
    if not isinstance(rr_intervals, list):
        rr_intervals = []
    device_name = wearable.get("device_name") or watch.get("device_name") or wearable.get("device") or watch.get("device")
    heart_rate = wearable.get("heart_rate_bpm", watch.get("heart_rate_bpm", user_state.get("heart_rate_bpm")))
    exertion = user_state.get("exertion_level", watch.get("exertion_level"))
    return {
        "status": wearable.get("status", watch.get("status", "unknown")),
        "device": device_name or "garmin_venu_3",
        "mounted_side": watch.get("mounted_side", wearable.get("mounted_side")),
        "provider": wearable.get("provider", watch.get("provider", "garmin")),
        "sample_type": wearable.get("sample_type", watch.get("sample_type", "ble_heart_rate")),
        "source": wearable.get("source", watch.get("source")),
        "heart_rate_bpm": heart_rate,
        "heart_rate_contact": wearable.get("heart_rate_contact", watch.get("heart_rate_contact")),
        "heart_rate_confidence": wearable.get("heart_rate_confidence"),
        "exertion_level": exertion,
        "intensity_zone": user_state.get("intensity_zone", watch.get("intensity_zone", "unknown")),
        "resting_heart_rate_bpm": wearable.get("resting_heart_rate_bpm", watch.get("resting_heart_rate_bpm")),
        "max_heart_rate_bpm": wearable.get("max_heart_rate_bpm", watch.get("max_heart_rate_bpm")),
        "rr_interval_ms": rr_intervals[-1] if rr_intervals else None,
        "rr_count": len(rr_intervals),
        "energy_expended_kj": wearable.get("energy_expended_kj", watch.get("energy_expended_kj")),
        "stress": wearable.get("stress", watch.get("stress")),
        "body_battery": wearable.get("body_battery", watch.get("body_battery")),
        "respiration_rate": wearable.get("respiration_rate", watch.get("respiration_rate")),
        "pulse_ox": wearable.get("pulse_ox", watch.get("pulse_ox")),
        "steps": wearable.get("steps", watch.get("steps")),
        "calories": wearable.get("calories", watch.get("calories")),
        "hrv_ms": wearable.get("hrv_ms", watch.get("hrv_ms")),
        "battery": wearable.get("battery", watch.get("battery")),
        "battery_unit": wearable.get("battery_unit", watch.get("battery_unit")),
        "acceleration": wearable.get("acceleration", watch.get("acceleration")),
        "acceleration_unit": wearable.get("acceleration_unit", watch.get("acceleration_unit")),
        "acceleration_magnitude_mg": wearable.get(
            "acceleration_magnitude_mg",
            watch.get("acceleration_magnitude_mg"),
        ),
        "watch_motion_delta_mg": wearable.get("watch_motion_delta_mg", watch.get("watch_motion_delta_mg")),
        "watch_motion_state": wearable.get("watch_motion_state", watch.get("watch_motion_state")),
        "gyroscope": wearable.get("gyroscope", watch.get("gyroscope")),
        "gyroscope_unit": wearable.get("gyroscope_unit", watch.get("gyroscope_unit")),
        "location": wearable.get("location", watch.get("location")),
        "latitude": wearable.get("latitude", watch.get("latitude")),
        "longitude": wearable.get("longitude", watch.get("longitude")),
        "altitude_m": wearable.get("altitude_m", watch.get("altitude_m")),
        "speed_mps": wearable.get("speed_mps", watch.get("speed_mps")),
        "distance_m": wearable.get("distance_m", watch.get("distance_m")),
        "heading_deg": wearable.get("heading_deg", watch.get("heading_deg")),
        "ingest_source": wearable.get("ingest_source", watch.get("ingest_source")),
        "age_seconds": wearable.get("age_seconds"),
        "timestamp": wearable.get("timestamp", watch.get("timestamp")),
        "sequence": wearable.get("sequence", watch.get("sequence")),
        "sent_count": wearable.get("sent_count", watch.get("sent_count")),
        "sample_interval_ms": wearable.get("sample_interval_ms", watch.get("sample_interval_ms")),
        "endpoint_mode": wearable.get("endpoint_mode", watch.get("endpoint_mode")),
        "last_http_code": wearable.get("last_http_code", watch.get("last_http_code")),
    }


def estimate_imu_motion_intensity(esp32_glove: dict[str, Any]) -> float:
    """Estimate IMU intensity from older payloads that predate this field."""

    motion_delta = safe_float(esp32_glove.get("motion_delta_mps2"), default=0.0) / 8.0
    angular_delta = safe_float(esp32_glove.get("angular_delta_dps"), default=0.0) / 180.0
    orientation_delta = safe_float(esp32_glove.get("orientation_delta_deg"), default=0.0) / 24.0
    return round(clamp(max(motion_delta, angular_delta, orientation_delta), 0.0, 1.0), 3)


def estimate_imu_motion_state(motion_intensity: float) -> str:
    """Mirror runtime IMU state labels for display fallback."""

    if motion_intensity < 0.08:
        return "steady"
    if motion_intensity < 0.28:
        return "small_motion"
    if motion_intensity < 0.72:
        return "active"
    return "burst"


def operator_state(payload: dict[str, Any]) -> str:
    """Return a high-level vision state suitable for clean mode."""

    motion_payload = as_dict(payload.get("motion_analysis"))
    motion_status = str(motion_payload.get("status", "unknown"))
    tokens = as_dict(payload.get("game_control")).get("tokens", [])
    if motion_status == "no_person_detected":
        return "no person"
    if motion_status == "arms_not_visible":
        return "arms hidden"
    if tokens:
        return "tracking"
    classifier_state = str(payload.get("movement_state") or payload.get("reason") or "standby")
    if classifier_state in {"ambiguous", "not_enough_motion", "collecting_motion", "unknown"}:
        return "tracking"
    return readable_state(classifier_state)


def operator_color(state: str) -> tuple[int, int, int]:
    """Return the clean-mode accent color for the current vision state."""

    if state in {"tracking", "detected", "motion tracked", "movement detected"}:
        return COLORS["green"]
    if state in {"standby", "arms hidden"}:
        return COLORS["yellow"]
    return COLORS["cyan"]


def fit_frame_to_width(frame: np.ndarray, target_width: int | None) -> np.ndarray:
    """Resize a camera frame while preserving aspect ratio for windowed mode."""

    if not target_width or target_width <= 0:
        return frame
    height, width = frame.shape[:2]
    if width == target_width:
        return frame
    scale = target_width / width
    target_height = max(1, int(height * scale))
    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)


def letterbox_frame(frame: np.ndarray, target_size: tuple[int, int]) -> LetterboxResult:
    """Scale a frame into ``target_size`` without stretching it.

    Aspect-ratio lock math:
    - Source aspect is ``src_w / src_h`` and target aspect is ``dst_w / dst_h``.
    - The only scale that can fit without cropping is
      ``min(dst_w / src_w, dst_h / src_h)``.
    - The resized image is centered in a black canvas, so any unused pixels are
      deterministic letterbox bars on the sides or top/bottom.
    """

    dst_w, dst_h = target_size
    src_h, src_w = frame.shape[:2]
    if dst_w <= 0 or dst_h <= 0 or src_w <= 0 or src_h <= 0:
        return LetterboxResult(canvas=frame, viewport=Rect(0, 0, frame.shape[1], frame.shape[0]))

    scale = min(dst_w / src_w, dst_h / src_h)
    scaled_w = max(1, int(round(src_w * scale)))
    scaled_h = max(1, int(round(src_h * scale)))
    x = (dst_w - scaled_w) // 2
    y = (dst_h - scaled_h) // 2

    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(frame, (scaled_w, scaled_h), interpolation=interpolation)
    canvas = np.zeros((dst_h, dst_w, 3), dtype=frame.dtype)
    canvas[y : y + scaled_h, x : x + scaled_w] = resized
    return LetterboxResult(canvas=canvas, viewport=Rect(x, y, scaled_w, scaled_h))


def draw_text(
    frame: np.ndarray,
    text: object,
    x: int,
    y: int,
    color: tuple[int, int, int] | None = None,
    scale: float = 0.45,
    thickness: int = 1,
    shadow: bool = True,
) -> None:
    """Draw anti-aliased HUD text with an optional dark readability shadow."""

    label = str(text)
    if shadow:
        cv2.putText(
            frame,
            label,
            (x + 1, y + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            COLORS["shadow"],
            thickness + 1,
            cv2.LINE_AA,
        )
    cv2.putText(
        frame,
        label,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color or COLORS["text"],
        thickness,
        cv2.LINE_AA,
    )


def rounded_rect(
    frame: np.ndarray,
    rect: Rect,
    color: tuple[int, int, int],
    radius: int,
    thickness: int = -1,
) -> None:
    """Draw a rounded rectangle using primitive OpenCV operations."""

    rect = clamp_rect(rect, frame.shape[1], frame.shape[0])
    if rect.w <= 0 or rect.h <= 0:
        return

    radius = max(0, min(radius, rect.w // 2, rect.h // 2))
    if radius == 0:
        cv2.rectangle(frame, (rect.x, rect.y), (rect.right, rect.bottom), color, thickness, cv2.LINE_AA)
        return

    if thickness < 0:
        cv2.rectangle(frame, (rect.x + radius, rect.y), (rect.right - radius, rect.bottom), color, -1)
        cv2.rectangle(frame, (rect.x, rect.y + radius), (rect.right, rect.bottom - radius), color, -1)
        for cx, cy in (
            (rect.x + radius, rect.y + radius),
            (rect.right - radius, rect.y + radius),
            (rect.right - radius, rect.bottom - radius),
            (rect.x + radius, rect.bottom - radius),
        ):
            cv2.circle(frame, (cx, cy), radius, color, -1, cv2.LINE_AA)
        return

    cv2.line(frame, (rect.x + radius, rect.y), (rect.right - radius, rect.y), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (rect.x + radius, rect.bottom), (rect.right - radius, rect.bottom), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (rect.x, rect.y + radius), (rect.x, rect.bottom - radius), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (rect.right, rect.y + radius), (rect.right, rect.bottom - radius), color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (rect.x + radius, rect.y + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (rect.right - radius, rect.y + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (rect.right - radius, rect.bottom - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (rect.x + radius, rect.bottom - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)


def draw_glass_panel(
    frame: np.ndarray,
    rect: Rect,
    alpha: float,
    border_color: tuple[int, int, int] | None = None,
    radius: int = THEME.radius,
) -> None:
    """Blend a #111111 glass panel using only the panel ROI.

    ``cv2.addWeighted`` is expensive when it touches a whole fullscreen frame.
    The optimization here slices the destination image to ``frame[y:y+h, x:x+w]``
    and blends only that small region.  This keeps clean/debug HUD glass effects
    without paying a 1080p/4K full-frame alpha cost.
    """

    rect = clamp_rect(rect, frame.shape[1], frame.shape[0])
    if rect.w <= 0 or rect.h <= 0:
        return
    roi = frame[rect.y : rect.bottom, rect.x : rect.right]
    overlay = roi.copy()
    rounded_rect(overlay, Rect(0, 0, rect.w, rect.h), COLORS["glass"], radius)
    cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0, dst=roi)
    rounded_rect(frame, rect, border_color or COLORS["glass_edge"], radius, thickness=1)


def draw_corner_marks(frame: np.ndarray, rect: Rect, color: tuple[int, int, int], length: int = 18) -> None:
    """Draw thin corner accents that make panels feel engineered, not boxed in."""

    length = max(6, min(length, rect.w // 4, rect.h // 4))
    points = [
        ((rect.x, rect.y + length), (rect.x, rect.y), (rect.x + length, rect.y)),
        ((rect.right - length, rect.y), (rect.right, rect.y), (rect.right, rect.y + length)),
        ((rect.right, rect.bottom - length), (rect.right, rect.bottom), (rect.right - length, rect.bottom)),
        ((rect.x + length, rect.bottom), (rect.x, rect.bottom), (rect.x, rect.bottom - length)),
    ]
    for start, corner, end in points:
        cv2.line(frame, start, corner, color, 1, cv2.LINE_AA)
        cv2.line(frame, corner, end, color, 1, cv2.LINE_AA)


def draw_led(frame: np.ndarray, center: tuple[int, int], color: tuple[int, int, int], active: bool = True) -> None:
    """Draw a small glowing hardware LED."""

    led_color = color if active else COLORS["faint"]
    for radius, alpha in ((18, 0.08), (12, 0.14)):
        draw_glow_circle(frame, center, radius, led_color, alpha)
    cv2.circle(frame, center, 7, COLORS["ink"], -1, cv2.LINE_AA)
    cv2.circle(frame, center, 5, led_color, -1, cv2.LINE_AA)
    cv2.circle(frame, center, 8, COLORS["white"], 1, cv2.LINE_AA)


def draw_glow_circle(
    frame: np.ndarray,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    """Blend a glow circle inside the smallest possible ROI."""

    x, y = center
    rect = clamp_rect(Rect(x - radius, y - radius, radius * 2 + 1, radius * 2 + 1), frame.shape[1], frame.shape[0])
    if rect.w <= 0 or rect.h <= 0:
        return
    local_center = (x - rect.x, y - rect.y)
    roi = frame[rect.y : rect.bottom, rect.x : rect.right]
    overlay = roi.copy()
    cv2.circle(overlay, local_center, radius, color, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0, dst=roi)


class DashboardRenderer:
    """Draw the clean HUD and optional debug telemetry overlay."""

    def __init__(
        self,
        canvas: np.ndarray,
        theme: Theme = THEME,
        debug_width: int | None = None,
        viewport: Rect | None = None,
    ):
        self.canvas = canvas
        self.theme = theme
        self.colors = theme.colors
        self.height, self.width = canvas.shape[:2]
        self.viewport = viewport or Rect(0, 0, self.width, self.height)
        self.debug_width = debug_width or theme.debug_panel_width

    def render(self, payload: dict[str, Any], detail: str = "clean") -> None:
        """Render clean mode by default; render debug details only on request."""

        view_model = DashboardViewModel.from_payload(payload, detail)
        self._clean_status_bar(view_model)
        if view_model.debug:
            self._debug_panel(view_model)

    def _clean_status_bar(self, view_model: DashboardViewModel) -> None:
        """Top-level monitor identity, FPS, and hardware LEDs."""

        if view_model.debug:
            rect_width = min(max(360, self.viewport.w // 3), 410)
        else:
            rect_width = min(max(520, self.viewport.w - self.theme.margin * 2), 760)
        rect = Rect(self.viewport.x + self.theme.margin, self.viewport.y + self.theme.margin, rect_width, self.theme.top_bar_height)
        draw_glass_panel(self.canvas, rect, self.theme.clean_panel_alpha, view_model.state_color)
        draw_corner_marks(self.canvas, rect, view_model.state_color, length=20)

        x = rect.x + self.theme.padding
        draw_text(self.canvas, "IRON QUEST 3D", x, rect.y + 32, COLORS["text"], self.theme.title_scale, 1)
        draw_text(
            self.canvas,
            "TRACKING & SENSOR MONITOR",
            x,
            rect.y + 57,
            COLORS["muted"],
            self.theme.caption_scale,
            1,
        )

        fps_rect = Rect(rect.right - 116, rect.y + 18, 96, 50)
        rounded_rect(self.canvas, fps_rect, COLORS["ink"], 8)
        rounded_rect(self.canvas, fps_rect, COLORS["glass_edge"], 8, thickness=1)
        draw_text(self.canvas, "FPS", fps_rect.x + 12, fps_rect.y + 18, COLORS["muted"], 0.32, 1)
        draw_text(self.canvas, f"{view_model.fps:04.1f}", fps_rect.x + 12, fps_rect.y + 40, COLORS["cyan"], 0.58, 1)

        # Hardware state is intentionally limited to LED-level information in
        # clean mode. Raw values stay hidden until debug mode is toggled.
        if rect.w >= 610:
            led_y = rect.y + 62
            led_x = rect.x + 302
            self._sensor_led("ESP32", view_model.esp32_label, (led_x, led_y), view_model.esp32_color)
            self._sensor_led("WEARABLE", view_model.wearable_label, (led_x + 142, led_y), view_model.wearable_color)

    def _sensor_led(self, name: str, status: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
        """Draw one clean-mode hardware indicator."""

        x, y = origin
        draw_led(self.canvas, (x, y - 3), color, active=color != COLORS["faint"])
        draw_text(self.canvas, name, x + 14, y - 9, COLORS["text"], 0.34, 1)
        draw_text(self.canvas, status, x + 14, y + 8, color, 0.31, 1)

    def _debug_panel(self, view_model: DashboardViewModel) -> None:
        """Fixed debug layout for game-control, IMU, and wearable telemetry."""

        panel_width = min(self.debug_width, max(320, self.viewport.w - self.theme.margin * 2))
        panel_height = self.viewport.h - self.theme.margin * 2
        panel = Rect(
            self.viewport.right - self.theme.margin - panel_width,
            self.viewport.y + self.theme.margin,
            panel_width,
            max(240, panel_height),
        )
        draw_glass_panel(self.canvas, panel, self.theme.debug_panel_alpha, COLORS["cyan"])
        draw_corner_marks(self.canvas, panel, COLORS["cyan"], length=24)

        body = panel.inset(self.theme.padding)
        draw_text(self.canvas, "DEBUG TELEMETRY", body.x, body.y + 22, COLORS["text"], 0.56, 1)
        draw_text(self.canvas, "control axes + live ESP32/IMU + smartwatch", body.x, body.y + 44, COLORS["muted"], 0.34, 1)

        cursor = body.y + 60
        available = max(240, body.bottom - cursor - self.theme.gap * 3)
        axis_height = min(138, max(104, int(available * 0.25)))
        imu_height = min(104, max(86, int(available * 0.20)))
        token_height = min(70, max(54, int(available * 0.14)))
        xyz_height = min(82, max(68, int(available * 0.16)))

        cursor = self._axis_grid(Rect(body.x, cursor, body.w, axis_height), view_model.axes)
        cursor += self.theme.gap
        cursor = self._imu_panel(Rect(body.x, cursor, body.w, imu_height), view_model.imu_signals)
        cursor += self.theme.gap
        cursor = self._token_grid(Rect(body.x, cursor, body.w, token_height), view_model.tokens, view_model.events)
        cursor += self.theme.gap
        cursor = self._esp32_xyz(Rect(body.x, cursor, body.w, xyz_height), view_model.esp32_vectors)
        cursor += self.theme.gap
        remaining = Rect(body.x, cursor, body.w, max(70, body.bottom - cursor))
        self._live_sensor_panel(remaining, view_model.esp32_detail, view_model.wearable_signals)

    def _section_label(self, label: str, x: int, y: int) -> None:
        """Draw a small debug section label with a neon rule."""

        draw_text(self.canvas, label, x, y, COLORS["cyan"], self.theme.caption_scale, 1)
        cv2.line(self.canvas, (x, y + 7), (x + 132, y + 7), COLORS["cyan"], 1, cv2.LINE_AA)

    def _axis_grid(self, rect: Rect, axes: dict[str, Any]) -> int:
        """Draw fixed rows for float analog axes from payload['game_control']."""

        self._section_label("GAME CONTROL AXES", rect.x, rect.y + 12)
        row_y = rect.y + 36
        if not axes:
            draw_text(self.canvas, "axes: {}", rect.x, row_y, COLORS["muted"], self.theme.body_scale, 1)
            return rect.bottom

        max_rows = min(8, max(1, (rect.h - 36) // 13))
        row_step = max(13, min(17, (rect.h - 36) // max_rows))
        for index, (name, raw_value) in enumerate(list(axes.items())[:max_rows]):
            y = row_y + index * row_step
            value = safe_float(raw_value)
            draw_text(self.canvas, ellipsize(name, 24), rect.x, y, COLORS["text"], 0.31, 1)
            draw_text(self.canvas, f"{value:+.3f}", rect.right - 62, y, COLORS["yellow"], 0.31, 1)

            bar = Rect(rect.x + 168, y - 7, max(40, rect.w - 244), 7)
            rounded_rect(self.canvas, bar, COLORS["bar_bg"], 4)
            center = bar.x + bar.w // 2
            fill = int((bar.w // 2) * clamp(abs(value), 0.0, 1.0))
            if fill > 0:
                start = (center - fill, bar.y + 4) if value < 0 else (center, bar.y + 4)
                end = (center, bar.y + 4) if value < 0 else (center + fill, bar.y + 4)
                cv2.line(self.canvas, start, end, COLORS["cyan"], 6, cv2.LINE_AA)
            cv2.line(self.canvas, (center, bar.y - 2), (center, bar.bottom + 2), COLORS["faint"], 1, cv2.LINE_AA)
        return rect.bottom

    def _imu_panel(self, rect: Rect, signals: dict[str, Any]) -> int:
        """Draw processed IMU state instead of only raw coordinates."""

        self._section_label("IMU CONTROL SIGNALS", rect.x, rect.y + 12)
        state = readable_state(signals.get("state", "unknown")).upper()
        transport = str(signals.get("transport") or "serial").upper()
        sample_rate = signals.get("sample_rate_hz")
        sample_label = "-- Hz" if sample_rate is None else f"{safe_float(sample_rate):05.2f} Hz"
        draw_text(self.canvas, state, rect.x, rect.y + 38, COLORS["yellow"], 0.44, 1)
        draw_text(self.canvas, transport, rect.x + 126, rect.y + 38, COLORS["muted"], 0.34, 1)
        draw_text(self.canvas, sample_label, rect.right - 88, rect.y + 38, COLORS["cyan"], 0.34, 1)

        rows = (
            ("motion", signals.get("motion_intensity"), COLORS["cyan"]),
            ("rotation", signals.get("rotation_intensity"), COLORS["magenta"]),
            ("stability", signals.get("stability_index"), COLORS["green"]),
        )
        row_y = rect.y + 60
        for index, (label, value, color) in enumerate(rows):
            y = row_y + index * 15
            draw_text(self.canvas, label, rect.x, y, COLORS["text"], 0.30, 1)
            bar = Rect(rect.x + 76, y - 8, max(80, rect.w - 150), 7)
            rounded_rect(self.canvas, bar, COLORS["bar_bg"], 4)
            numeric_value = None if value is None else safe_float(value)
            fill = 0 if numeric_value is None else int(bar.w * clamp(numeric_value, 0.0, 1.0))
            if fill > 0:
                cv2.line(self.canvas, (bar.x, bar.y + 4), (bar.x + fill, bar.y + 4), color, 6, cv2.LINE_AA)
            draw_text(
                self.canvas,
                "--" if numeric_value is None else f"{numeric_value:.3f}",
                rect.right - 58,
                y,
                COLORS["muted"] if numeric_value is None else COLORS["yellow"],
                0.30,
                1,
            )
        return rect.bottom

    def _token_grid(self, rect: Rect, tokens: list[str], events: list[str]) -> int:
        """Draw raw token/event chips without a scrolling log."""

        self._section_label("BOOLEAN TOKENS / EVENTS", rect.x, rect.y + 12)
        chips = [*tokens[:8], *[f"event:{event}" for event in events[:2]]]
        if not chips:
            draw_text(self.canvas, "tokens: []", rect.x, rect.y + 40, COLORS["muted"], self.theme.body_scale, 1)
            return rect.bottom

        cursor_x = rect.x
        cursor_y = rect.y + 39
        row_height = 25
        max_rows = 2
        current_row = 1
        for chip_text in chips:
            label = ellipsize(chip_text, 28)
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.32, 1)
            chip_w = min(rect.w, text_w + 16)
            if cursor_x + chip_w > rect.right:
                current_row += 1
                if current_row > max_rows:
                    draw_text(self.canvas, "...", rect.right - 20, cursor_y, COLORS["muted"], 0.34, 1)
                    break
                cursor_x = rect.x
                cursor_y += row_height
            chip = Rect(cursor_x, cursor_y - text_h - 7, chip_w, text_h + 11)
            rounded_rect(self.canvas, chip, COLORS["ink"], 6)
            rounded_rect(self.canvas, chip, COLORS["glass_edge"], 6, thickness=1)
            draw_text(self.canvas, label, chip.x + 8, cursor_y, COLORS["text"], 0.32, 1)
            cursor_x += chip_w + 7
        return rect.bottom

    def _esp32_xyz(self, rect: Rect, rows: list[tuple[str, str, str, str]]) -> int:
        """Draw exact ESP32 X/Y/Z coordinate rows."""

        self._section_label("ESP32 XYZ COORDINATES", rect.x, rect.y + 12)
        row_y = rect.y + 40
        if not rows:
            draw_text(self.canvas, "No ESP32 XYZ sample", rect.x, row_y, COLORS["muted"], self.theme.body_scale, 1)
            return rect.bottom

        for index, (label, x_value, y_value, z_value) in enumerate(rows[:3]):
            y = row_y + index * 24
            draw_text(self.canvas, label, rect.x, y, COLORS["yellow"], 0.38, 1)
            draw_text(self.canvas, x_value, rect.x + 76, y, COLORS["text"], 0.36, 1)
            draw_text(self.canvas, y_value, rect.x + 190, y, COLORS["text"], 0.36, 1)
            draw_text(self.canvas, z_value, rect.x + 304, y, COLORS["text"], 0.36, 1)
        return rect.bottom

    def _live_sensor_panel(self, rect: Rect, esp32: dict[str, Any], wearable: dict[str, Any]) -> None:
        """Draw structured hardware details as full-width sensor rows."""

        self._section_label("LIVE SENSOR DETAIL", rect.x, rect.y + 12)
        content = Rect(rect.x, rect.y + 24, rect.w, max(56, rect.h - 24))
        gap = 8
        row_h = min(96, max(68, (content.h - gap) // 2))
        esp32_row = Rect(content.x, content.y, content.w, row_h)
        wearable_row = Rect(content.x, content.y + row_h + gap, content.w, row_h)

        self._sensor_detail_row(
            esp32_row,
            "ESP32 + IMU",
            self._sensor_subtitle(esp32.get("status"), esp32.get("transport"), fallback="live motion"),
            COLORS["cyan"],
            self._esp32_detail_metrics(esp32),
        )
        self._sensor_detail_row(
            wearable_row,
            "GARMIN VENU 3",
            self._wearable_subtitle(wearable),
            COLORS["green"],
            self._wearable_metrics(wearable),
        )

    def _sensor_subtitle(self, status: object, source: object, fallback: str) -> str:
        """Return a compact sensor subtitle without duplicating metric rows."""

        status_key = str(status or "").lower()
        status_label = {
            "connected": "CONNECTED",
            "stale": "STALE",
            "listening_waiting_for_data": "WAITING",
            "connected_waiting_for_data": "WAITING",
            "listening_non_json_data": "WAITING",
            "connected_non_json_data": "WAITING",
        }.get(status_key, readable_state(status).upper())
        parts = [status_label] if self._has_metric_value(status) else []
        if self._has_metric_value(source):
            parts.append(readable_state(source).upper())
        return " / ".join(parts) if parts else fallback

    def _wearable_subtitle(self, wearable: dict[str, Any]) -> str:
        """Return channel and battery without duplicating the freshness cell."""

        sample_type = str(wearable.get("sample_type") or "").lower()
        if "connect_iq" in sample_type:
            channel = "CIQ"
        elif "health" in sample_type or "sdk" in sample_type:
            channel = "SDK"
        elif "heart" in sample_type or "ble" in sample_type:
            channel = "HR"
        else:
            channel = "DATA"
        battery = format_number(wearable.get("battery"), 0, "%", missing=None)
        parts = [] if channel == "DATA" else [channel]
        if battery is not None:
            parts.append(f"BAT {battery}")
        return " / ".join(parts) if parts else "watch data"

    def _esp32_detail_metrics(self, detail: dict[str, Any]) -> list[tuple[str, object, tuple[int, int, int]]]:
        """Return non-duplicated ESP32/IMU detail cells for the live row."""

        status = str(detail.get("status") or "waiting").lower()
        if status != "connected":
            age = optional_float(detail.get("sample_age_seconds"))
            status_label = "STALE / RECONNECTING" if status == "stale" else "WAITING FOR DATA"
            metrics = [
                (
                    "STATUS",
                    status_label,
                    COLORS["yellow"] if status == "stale" else COLORS["muted"],
                )
            ]
            if age is not None:
                metrics.append(("LAST SAMPLE", format_duration(age), COLORS["muted"]))
            return metrics

        metrics: list[tuple[str, object, tuple[int, int, int]]] = [
            ("ORIENT", self._orientation_label(detail), COLORS["yellow"]),
            ("DELTA", self._imu_delta_label(detail), COLORS["text"]),
            ("SEQ", detail.get("sequence"), COLORS["cyan"]),
        ]
        optional_metrics = [
            ("BATTERY", format_number(detail.get("battery_v"), 2, " V") if detail.get("battery_v") is not None else None, COLORS["green"]),
            ("TEMP", format_number(detail.get("temperature_c"), 1, " C") if detail.get("temperature_c") is not None else None, COLORS["text"]),
        ]
        metrics.extend(optional_metrics)
        return self._clean_metric_list(metrics, fallback=("STATUS", detail.get("status", "waiting"), COLORS["muted"]))

    def _wearable_metrics(self, wearable: dict[str, Any]) -> list[tuple[str, object, tuple[int, int, int]]]:
        """Return useful Garmin metrics that are present in the current payload."""

        is_stale = self._wearable_is_stale(wearable)
        zone = readable_state(wearable.get("intensity_zone", "unknown")).upper()
        contact = wearable.get("heart_rate_contact") or wearable.get("heart_rate_confidence")
        hr = format_number(wearable.get("heart_rate_bpm"), 0, " BPM", missing=None)
        hr_label = f"{hr} / {zone}" if hr and zone != "UNKNOWN" else hr
        mounted_side = readable_state(wearable.get("mounted_side")).upper()
        freshness_color = self._wearable_quality_color(wearable)
        metric_color = COLORS["muted"] if is_stale else COLORS["green"]
        metrics: list[tuple[str, object, tuple[int, int, int]]] = [
            ("FRESHNESS", self._wearable_quality_label(wearable), freshness_color),
            ("HEART", hr_label, COLORS["muted"] if is_stale else COLORS["yellow"]),
            (
                "CONTACT",
                readable_state(contact) if self._has_metric_value(contact) else None,
                metric_color,
            ),
            ("MOTION", self._wearable_wrist_motion_label(wearable), metric_color),
            ("ACC MAG", self._wearable_accel_label(wearable), COLORS["muted"] if is_stale else COLORS["magenta"]),
            ("WRIST", mounted_side if mounted_side != "UNKNOWN" else None, COLORS["muted"] if is_stale else COLORS["cyan"]),
        ]
        return self._clean_metric_list(metrics, fallback=("STATUS", wearable.get("status", "waiting"), COLORS["muted"]))

    def _orientation_label(self, detail: dict[str, Any]) -> str | None:
        """Return pitch/roll/yaw as one compact useful value."""

        pitch = format_number(detail.get("pitch"), 0, "", missing=None)
        roll = format_number(detail.get("roll"), 0, "", missing=None)
        yaw = format_number(detail.get("yaw"), 0, "", missing=None)
        if not any(self._has_metric_value(value) for value in (pitch, roll, yaw)):
            return None
        return f"P{pitch or '--'} R{roll or '--'} Y{yaw or '--'}"

    def _imu_delta_label(self, detail: dict[str, Any]) -> str | None:
        """Return compact IMU delta summary without repeating the upper panel."""

        accel = format_number(detail.get("motion_delta_mps2"), 2, "", missing=None)
        gyro = format_number(detail.get("angular_delta_dps"), 1, "", missing=None)
        orient = format_number(detail.get("orientation_delta_deg"), 1, "", missing=None)
        parts = []
        if accel is not None:
            parts.append(f"A{accel}")
        if gyro is not None:
            parts.append(f"G{gyro}")
        if orient is not None:
            parts.append(f"O{orient}")
        return " ".join(parts) if parts else None

    def _wearable_quality_label(self, wearable: dict[str, Any]) -> str:
        """Return live/stale quality as a direct operator signal."""

        status = str(wearable.get("status") or "unknown").lower()
        age = optional_float(wearable.get("age_seconds"))
        if status == "stale":
            return f"STALE {format_duration(age)}" if age is not None else "STALE"
        if status in {"missing_device", "error", "bad_json"}:
            return readable_state(status).upper()
        if age is not None:
            return f"LIVE {format_duration(age)}" if age <= 5 else f"OLD {format_duration(age)}"
        return readable_state(status).upper()

    def _wearable_quality_color(self, wearable: dict[str, Any]) -> tuple[int, int, int]:
        """Color freshness without needing an extra explanation string."""

        status = str(wearable.get("status") or "unknown").lower()
        age = optional_float(wearable.get("age_seconds"))
        if status in {"missing_device", "error", "bad_json"}:
            return COLORS["red"]
        if status == "stale" or (age is not None and age > 30):
            return COLORS["yellow"]
        if status == "connected":
            return COLORS["green"]
        return COLORS["muted"]

    def _wearable_is_stale(self, wearable: dict[str, Any]) -> bool:
        """Return true when values should be treated as historical, not live."""

        status = str(wearable.get("status") or "unknown").lower()
        age = optional_float(wearable.get("age_seconds"))
        return status == "stale" or (age is not None and age > 30)

    def _wearable_age_label(self, wearable: dict[str, Any]) -> str:
        """Return the current payload age in human-friendly form."""

        return format_duration(wearable.get("age_seconds"))

    def _wearable_source_label(self, wearable: dict[str, Any]) -> str | None:
        """Return compact Garmin ingest source without exposing raw JSON."""

        sample_type = str(wearable.get("sample_type") or "").lower()
        source = str(wearable.get("source") or "").lower()
        if "connect_iq_safe" in sample_type or "safe" in source:
            return "CIQ SAFE"
        if "connect_iq" in sample_type or "connect_iq" in source:
            return "CIQ"
        if "ble" in sample_type or "heart" in sample_type:
            return "BLE HR"
        if "health" in sample_type or "sdk" in sample_type:
            return "SDK"
        return readable_state(sample_type or source) if sample_type or source else None

    def _rr_hrv_label(self, wearable: dict[str, Any]) -> str | None:
        """Return beat-to-beat context when Garmin provides it."""

        parts = []
        rr = format_number(wearable.get("rr_interval_ms"), 0, " ms", missing=None)
        hrv = format_number(wearable.get("hrv_ms"), 0, " ms", missing=None)
        if rr is not None:
            parts.append(f"RR {rr}")
        if hrv is not None:
            parts.append(f"HRV {hrv}")
        return " | ".join(parts) if parts else None

    def _wearable_health_label(self, wearable: dict[str, Any]) -> str | None:
        """Return the most useful wellness summary in one cell."""

        candidates = [
            ("Body", wearable.get("body_battery")),
            ("SpO2", wearable.get("pulse_ox")),
            ("Stress", wearable.get("stress")),
            ("Resp", format_number(wearable.get("respiration_rate"), 0, "", missing=None)),
        ]
        parts = [f"{label} {value}" for label, value in candidates if self._has_metric_value(value)]
        return " | ".join(parts[:2]) if parts else None

    def _wearable_activity_label(self, wearable: dict[str, Any]) -> str | None:
        """Return activity context only when it adds new information."""

        parts = []
        if self._has_metric_value(wearable.get("steps")):
            parts.append(f"Steps {wearable.get('steps')}")
        if self._has_metric_value(wearable.get("calories")):
            parts.append(f"Cal {wearable.get('calories')}")
        distance = format_number(wearable.get("distance_m"), 0, " m", missing=None)
        if distance is not None:
            parts.append(distance)
        return " | ".join(parts[:2]) if parts else None

    def _wearable_wrist_motion_label(self, wearable: dict[str, Any]) -> str | None:
        """Return the watch-derived wrist motion state and sample-to-sample delta."""

        state = wearable.get("watch_motion_state")
        delta = format_number(wearable.get("watch_motion_delta_mg"), 0, " mg", missing=None)
        if self._has_metric_value(state) and delta is not None:
            return f"{readable_state(state)} / {delta}"
        if self._has_metric_value(state):
            return readable_state(state)
        if delta is not None:
            return f"delta {delta}"
        return self._wearable_motion_label(wearable)

    def _wearable_accel_label(self, wearable: dict[str, Any]) -> str | None:
        """Return watch acceleration magnitude without exposing raw XYZ values."""

        magnitude = format_number(wearable.get("acceleration_magnitude_mg"), 0, " mg", missing=None)
        if magnitude is not None:
            return magnitude
        return self._vector_magnitude_label(wearable.get("acceleration"), wearable.get("acceleration_unit"))

    def _wearable_packet_label(self, wearable: dict[str, Any]) -> str | None:
        """Return the current Connect IQ packet number for quick live checking."""

        sequence = wearable.get("sequence")
        sent = wearable.get("sent_count")
        if self._has_metric_value(sequence) and self._has_metric_value(sent):
            return f"seq {sequence} / sent {sent}"
        if self._has_metric_value(sequence):
            return f"seq {sequence}"
        return None

    def _wearable_motion_label(self, wearable: dict[str, Any]) -> str | None:
        """Return watch IMU presence as magnitudes, not raw XYZ clutter."""

        parts = []
        accel = self._wearable_accel_label(wearable)
        gyro = self._vector_magnitude_label(wearable.get("gyroscope"), wearable.get("gyroscope_unit") or "dps")
        if accel is not None:
            parts.append(f"A{accel}")
        if gyro is not None:
            parts.append(f"G{gyro}")
        return " ".join(parts) if parts else None

    def _wearable_location_label(self, wearable: dict[str, Any]) -> str | None:
        """Return compact GPS/location context when available."""

        location = as_dict(wearable.get("location"))
        latitude = optional_float(wearable.get("latitude", location.get("latitude")))
        longitude = optional_float(wearable.get("longitude", location.get("longitude")))
        if latitude is not None and longitude is not None:
            return f"{latitude:.4f}, {longitude:.4f}"
        speed = format_number(wearable.get("speed_mps", location.get("speed_mps")), 1, " m/s", missing=None)
        altitude = format_number(wearable.get("altitude_m", location.get("altitude_m")), 0, " m", missing=None)
        if speed is not None:
            return f"Speed {speed}"
        if altitude is not None:
            return f"Alt {altitude}"
        return None

    def _vector_magnitude_label(self, value: object, unit: object = None) -> str | None:
        """Return a scalar magnitude from a vector-like payload."""

        vector = self._vector_xyz(value)
        if vector is None:
            return None
        magnitude = float(np.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2))
        unit_label = str(unit or "").strip()
        if unit_label:
            return f"{magnitude:.1f}{unit_label}"
        return f"{magnitude:.2f}"

    def _vector_xyz(self, value: object) -> tuple[float, float, float] | None:
        """Parse a vector from dict/list payloads already normalized by sensors.py."""

        if isinstance(value, dict):
            x = optional_float(value.get("x"))
            y = optional_float(value.get("y"))
            z = optional_float(value.get("z"))
        elif isinstance(value, (list, tuple)) and len(value) >= 3:
            x = optional_float(value[0])
            y = optional_float(value[1])
            z = optional_float(value[2])
        else:
            return None
        if x is None or y is None or z is None:
            return None
        return x, y, z

    def _clean_metric_list(
        self,
        metrics: list[tuple[str, object, tuple[int, int, int]]],
        fallback: tuple[str, object, tuple[int, int, int]],
    ) -> list[tuple[str, object, tuple[int, int, int]]]:
        """Remove empty smartwatch/IMU values before rendering compact chips."""

        clean = [(label, value, color) for label, value, color in metrics if self._has_metric_value(value)]
        return clean or [fallback]

    def _has_metric_value(self, value: object) -> bool:
        """Return true for values that should be visible in the debug UI."""

        if value is None:
            return False
        if isinstance(value, float) and np.isnan(value):
            return False
        if isinstance(value, str):
            text = value.strip().lower()
            return text not in {"", "--", "--/--", "none", "null", "nan", "unknown"}
        return True

    def _sensor_detail_row(
        self,
        rect: Rect,
        title: str,
        subtitle: str,
        accent: tuple[int, int, int],
        metrics: list[tuple[str, object, tuple[int, int, int]]],
    ) -> None:
        """Draw one full-width hardware row with fixed metric cells."""

        rounded_rect(self.canvas, rect, COLORS["ink"], 8)
        rounded_rect(self.canvas, rect, COLORS["glass_edge"], 8, thickness=1)
        label_w = min(124, max(108, rect.w // 4))
        draw_text(self.canvas, title, rect.x + 10, rect.y + 21, accent, 0.36, 1)
        draw_text(self.canvas, ellipsize(subtitle, 22), rect.x + 10, rect.y + 41, COLORS["muted"], 0.29, 1)

        chip_area = Rect(rect.x + label_w, rect.y + 11, max(40, rect.w - label_w - 10), max(20, rect.h - 18))
        self._metric_cells(chip_area, metrics)

    def _metric_cells(self, rect: Rect, metrics: list[tuple[str, object, tuple[int, int, int]]]) -> None:
        """Draw useful key values in a small fixed grid, not loose chips."""

        columns = 3 if rect.w >= 250 else 2
        rows = max(1, min(2, rect.h // 34))
        cell_w = max(46, rect.w // columns)
        cell_h = max(30, rect.h // rows)
        max_items = columns * rows
        for index, (label, value, value_color) in enumerate(metrics[:max_items]):
            row = index // columns
            column = index % columns
            x = rect.x + column * cell_w
            y = rect.y + row * cell_h
            if column > 0:
                cv2.line(self.canvas, (x - 6, y + 3), (x - 6, min(y + cell_h - 6, rect.bottom)), COLORS["faint"], 1, cv2.LINE_AA)
            label_max = max(7, int((cell_w - 8) / 7))
            value_max = max(8, int((cell_w - 2) / 6))
            draw_text(self.canvas, ellipsize(label, label_max), x, y + 13, COLORS["muted"], 0.27, 1)
            draw_text(self.canvas, ellipsize(value, value_max), x, y + 32, value_color, 0.34, 1)
    def _json_block(self, rect: Rect, title: str, raw_json: str) -> None:
        """Draw compact raw JSON in a bounded debug block."""

        self._section_label(title, rect.x, rect.y + 12)
        block = Rect(rect.x, rect.y + 24, rect.w, max(20, rect.h - 24))
        rounded_rect(self.canvas, block, COLORS["ink"], 8)
        rounded_rect(self.canvas, block, COLORS["glass_edge"], 8, thickness=1)

        max_chars = max(32, int((block.w - 20) / 7))
        max_lines = max(1, int((block.h - 16) / self.theme.line_height))
        for index, line in enumerate(wrap_fixed(raw_json, max_chars, max_lines)):
            draw_text(
                self.canvas,
                line,
                block.x + 10,
                block.y + 18 + index * self.theme.line_height,
                COLORS["muted"],
                self.theme.mono_scale,
                1,
            )


def keypoint_color(name: str) -> tuple[int, int, int]:
    """Return the neon color assigned to an anatomical side."""

    if name.startswith("left_"):
        return COLORS["bone_left"]
    if name.startswith("right_"):
        return COLORS["bone_right"]
    return COLORS["bone_center"]


def bone_color(start_name: str, end_name: str) -> tuple[int, int, int]:
    """Use center color for cross-body bones and side colors for limbs."""

    if start_name.startswith("left_") and end_name.startswith("left_"):
        return COLORS["bone_left"]
    if start_name.startswith("right_") and end_name.startswith("right_"):
        return COLORS["bone_right"]
    return COLORS["cyan"]


def draw_glow_line(
    frame: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    """Draw a bright inner line with a dark outer channel for contrast."""

    cv2.line(frame, start, end, COLORS["ink"], thickness + 5, cv2.LINE_AA)
    cv2.line(frame, start, end, color, thickness + 2, cv2.LINE_AA)
    cv2.line(frame, start, end, COLORS["white"], 1, cv2.LINE_AA)


def draw_pose_overlay(frame: np.ndarray, pose: PoseCandidate | None, min_confidence: float = 0.25) -> None:
    """Draw a polished game-engine body skeleton over the camera preview."""

    if pose is None:
        return

    for start_name, end_name in POSE_EDGES:
        if not is_visible(pose, start_name, min_confidence) or not is_visible(pose, end_name, min_confidence):
            continue
        start = tuple(pose.xy[COCO_KEYPOINTS[start_name]].astype(int))
        end = tuple(pose.xy[COCO_KEYPOINTS[end_name]].astype(int))
        draw_glow_line(frame, start, end, bone_color(start_name, end_name), thickness=2)

    for name, index in COCO_KEYPOINTS.items():
        if name in {"nose", "left_eye", "right_eye", "left_ear", "right_ear"}:
            continue
        if not is_visible(pose, name, min_confidence):
            continue
        point = tuple(pose.xy[index].astype(int))
        color = keypoint_color(name)
        cv2.circle(frame, point, 10, COLORS["ink"], -1, cv2.LINE_AA)
        cv2.circle(frame, point, 7, color, 1, cv2.LINE_AA)
        cv2.circle(frame, point, 3, COLORS["white"], -1, cv2.LINE_AA)


def mirror_x_for_display(x: float, frame_width: int) -> float:
    """Mirror an image-space X coordinate without changing analysis payloads."""

    return float(frame_width - 1 - x)


def mirror_pose_for_display(pose: PoseCandidate | None, frame_width: int) -> PoseCandidate | None:
    """Mirror pose coordinates for preview only; analysis stays anatomical."""

    if pose is None:
        return None
    xy = pose.xy.copy()
    visible = xy[:, 0] != 0
    xy[visible, 0] = frame_width - 1 - xy[visible, 0]
    return PoseCandidate(xy=xy, conf=pose.conf, box_confidence=pose.box_confidence)


def draw_hud_panel(
    panel: np.ndarray,
    payload: dict[str, Any],
    detail: str = "clean",
    debug_width: int | None = None,
    viewport: Rect | None = None,
) -> None:
    """Compatibility wrapper that draws the HUD over any image surface."""

    DashboardRenderer(panel, debug_width=debug_width, viewport=viewport).render(payload, detail=detail)


def compose_detector_view(
    frame: np.ndarray,
    payload: dict[str, Any],
    display_width: int | None,
    panel_width: int | None = None,
    ui_detail: str = "clean",
    display_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """Create the final detector view with the HUD overlaid on the camera feed."""

    if display_size is not None:
        letterboxed = letterbox_frame(frame, display_size)
        draw_hud_panel(
            letterboxed.canvas,
            payload,
            detail=ui_detail,
            debug_width=panel_width,
            viewport=letterboxed.viewport,
        )
        return letterboxed.canvas

    frame = fit_frame_to_width(frame, display_width)
    draw_hud_panel(frame, payload, detail=ui_detail, debug_width=panel_width)
    return frame


def compose_detector_preview(
    frame: np.ndarray,
    payload: dict[str, Any],
    pose: PoseCandidate | None,
    object_result: object | None,
    display_width: int | None,
    panel_width: int | None = None,
    ui_detail: str = "clean",
    mirror: bool = False,
    min_pose_confidence: float = 0.25,
    min_object_area_ratio: float = 0.0,
    display_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """Render the full preview while keeping analysis coordinates anatomical."""

    detail = "debug" if ui_detail == "debug" else "clean"
    annotated = cv2.flip(frame, 1) if mirror else frame.copy()
    display_pose = mirror_pose_for_display(pose, frame.shape[1]) if mirror else pose
    draw_pose_overlay(annotated, display_pose, min_confidence=min_pose_confidence)
    if object_result is not None:
        draw_object_detections(
            annotated,
            object_result,
            mirror_width=frame.shape[1] if mirror else None,
            min_area_ratio=min_object_area_ratio,
            object_payload=payload.get("object_detection"),
            show_label=detail == "debug",
        )
    return compose_detector_view(
        annotated,
        payload,
        display_width,
        panel_width,
        ui_detail=detail,
        display_size=display_size,
    )


def compose_camera_detection_preview(
    frame: np.ndarray,
    payload: dict[str, Any],
    pose: PoseCandidate | None,
    object_result: object | None,
    display_width: int | None,
    mirror: bool = False,
    min_pose_confidence: float = 0.25,
    min_object_area_ratio: float = 0.0,
    display_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """Render only the camera image, pose skeleton, and accepted weights.

    The browser game is the user-facing surface. It should not receive the
    developer HUD that remains available in the standalone OpenCV monitor.
    """

    annotated = cv2.flip(frame, 1) if mirror else frame.copy()
    display_pose = mirror_pose_for_display(pose, frame.shape[1]) if mirror else pose
    draw_pose_overlay(annotated, display_pose, min_confidence=min_pose_confidence)
    if object_result is not None:
        draw_object_detections(
            annotated,
            object_result,
            mirror_width=frame.shape[1] if mirror else None,
            min_area_ratio=min_object_area_ratio,
            object_payload=payload.get("object_detection"),
            show_label=False,
        )
    if display_size is not None:
        return letterbox_frame(annotated, display_size).canvas
    return fit_frame_to_width(annotated, display_width)


def draw_target_bracket(
    frame: np.ndarray,
    rect: Rect,
    color: tuple[int, int, int],
    label: str | None = None,
) -> None:
    """Draw a high-tech corner-bracket target instead of a solid box."""

    rect = clamp_rect(rect, frame.shape[1], frame.shape[0])
    if rect.w <= 0 or rect.h <= 0:
        return

    length = max(12, min(34, int(min(rect.w, rect.h) * 0.34)))
    segments = [
        ((rect.x, rect.y + length), (rect.x, rect.y), (rect.x + length, rect.y)),
        ((rect.right - length, rect.y), (rect.right, rect.y), (rect.right, rect.y + length)),
        ((rect.right, rect.bottom - length), (rect.right, rect.bottom), (rect.right - length, rect.bottom)),
        ((rect.x + length, rect.bottom), (rect.x, rect.bottom), (rect.x, rect.bottom - length)),
    ]
    for start, corner, end in segments:
        cv2.line(frame, start, corner, COLORS["ink"], 6, cv2.LINE_AA)
        cv2.line(frame, corner, end, COLORS["ink"], 6, cv2.LINE_AA)
        cv2.line(frame, start, corner, color, 2, cv2.LINE_AA)
        cv2.line(frame, corner, end, color, 2, cv2.LINE_AA)

    center = (rect.x + rect.w // 2, rect.y + rect.h // 2)
    cv2.line(frame, (center[0] - 8, center[1]), (center[0] + 8, center[1]), color, 1, cv2.LINE_AA)
    cv2.line(frame, (center[0], center[1] - 8), (center[0], center[1] + 8), color, 1, cv2.LINE_AA)
    cv2.circle(frame, center, 3, COLORS["white"], -1, cv2.LINE_AA)

    if label:
        (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)
        label_rect = Rect(rect.x, max(0, rect.y - label_h - 14), label_w + 18, label_h + 12)
        draw_glass_panel(frame, label_rect, 0.70, color, radius=6)
        draw_text(frame, label, label_rect.x + 8, label_rect.y + label_h + 2, COLORS["text"], 0.36, 1)


def draw_object_detections(
    frame: np.ndarray,
    object_result: object,
    mirror_width: int | None = None,
    min_area_ratio: float = 0.0,
    object_payload: dict[str, Any] | None = None,
    show_label: bool = False,
) -> None:
    """Draw accepted dumbbell/weight detections as targeting brackets.

    When ``object_payload`` is provided, only body-context accepted detections
    are drawn.  This keeps the monitor from rewarding raw YOLO false positives.
    """

    min_area = None
    if min_area_ratio > 0:
        height, width = frame.shape[:2]
        min_area = float(height * width * min_area_ratio)

    if object_payload is not None:
        detections = object_payload.get("detections", [])
    else:
        detections = [
            detection.as_payload()
            for detection in extract_object_detections(object_result, {"dumbbell", "weight"}, min_area=min_area)
        ]

    for detection in detections:
        try:
            x1, y1, x2, y2 = [int(value) for value in detection["xyxy"]]
        except (KeyError, TypeError, ValueError):
            continue
        if mirror_width is not None:
            x1, x2 = int(mirror_x_for_display(x2, mirror_width)), int(mirror_x_for_display(x1, mirror_width))
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        label = None
        if show_label:
            label = f"{detection.get('label', 'target')} {safe_float(detection.get('confidence')):.2f}"
        draw_target_bracket(frame, Rect(x1, y1, x2 - x1, y2 - y1), COLORS["target"], label=label)
