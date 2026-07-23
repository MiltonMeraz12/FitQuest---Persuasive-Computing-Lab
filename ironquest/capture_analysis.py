"""Offline summaries for recorded IronQuest sensor-fusion captures."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def resolve_capture_jsonl(path: Path | None, captures_root: Path = Path("data/captures")) -> Path:
    """Return a motion_payloads JSONL path from a file, folder, or latest capture."""

    if path is None:
        latest = latest_capture_dir(captures_root)
        if latest is None:
            raise FileNotFoundError(f"No capture sessions found under {captures_root}")
        return latest / "motion_payloads.jsonl"

    if path.is_dir():
        return path / "motion_payloads.jsonl"
    return path


def latest_capture_dir(captures_root: Path = Path("data/captures")) -> Path | None:
    """Find the newest capture session containing motion payloads."""

    if not captures_root.exists():
        return None
    candidates = [
        child
        for child in captures_root.iterdir()
        if child.is_dir() and (child / "motion_payloads.jsonl").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda child: (child / "motion_payloads.jsonl").stat().st_mtime)


def analyze_capture(path: Path | None = None, captures_root: Path = Path("data/captures")) -> dict[str, Any]:
    """Analyze a recorded capture and return a compact, reusable summary."""

    jsonl_path = resolve_capture_jsonl(path, captures_root=captures_root)
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Capture JSONL not found: {jsonl_path}")

    rows = _read_jsonl(jsonl_path)
    metadata = _read_metadata(jsonl_path.parent / "metadata.json")
    timestamps = [_number(row.get("timestamp")) for row in rows]
    timestamps = [value for value in timestamps if value is not None]
    duration_s = 0.0 if len(timestamps) < 2 else max(0.0, timestamps[-1] - timestamps[0])
    frame_count = len(rows)
    effective_fps = None if duration_s <= 0 else frame_count / duration_s

    esp32_statuses = Counter(_path(row, "game_control.sensor_status.esp32_glove") or _path(row, "esp32.status") or "unknown" for row in rows)
    wearable_statuses = Counter(
        _path(row, "game_control.sensor_status.wearable_watch") or _path(row, "wearable.status") or "unknown"
        for row in rows
    )
    vision_statuses = Counter(_path(row, "game_control.status") or _path(row, "motion_analysis.status") or "unknown" for row in rows)
    imu_states = Counter(_imu_state(row) for row in rows if _imu_state(row) is not None)
    intensity_zones = Counter(_wearable_zone(row) for row in rows if _wearable_zone(row) is not None)
    event_counts = Counter(event for row in rows for event in _events(row))

    esp32_connected_frames = sum(count for status, count in esp32_statuses.items() if str(status).startswith("connected"))
    wearable_connected_frames = sum(
        count for status, count in wearable_statuses.items() if str(status).startswith("connected")
    )
    esp32_with_samples = sum(1 for row in rows if _latest_esp32(row))
    wearable_with_hr = sum(1 for row in rows if _wearable_number(row, "heart_rate_bpm", "heart_rate_bpm") is not None)
    wearable_with_motion = sum(1 for row in rows if _wearable_motion_state(row) is not None)
    pose_ready_frames = sum(count for status, count in vision_statuses.items() if status == "ready")
    arms_visible_frames = sum(1 for row in rows if _arm_visible(row))

    imu_motion = [_imu_number(row, "motion_delta_mps2", "imu_motion_delta_mps2") for row in rows]
    imu_angular = [_imu_number(row, "angular_delta_dps", "imu_angular_delta_dps") for row in rows]
    imu_orientation = [_imu_number(row, "orientation_delta_deg", "imu_orientation_delta_deg") for row in rows]
    imu_intensity = [_imu_intensity(row) for row in rows]
    imu_stability = [_imu_number(row, "stability_index", "stability_index") for row in rows]
    sample_ms = [_imu_number(row, "sample_interval_ms", "imu_sample_interval_ms") for row in rows]
    heart_rate = [_wearable_number(row, "heart_rate_bpm", "heart_rate_bpm") for row in rows]
    exertion = [_wearable_number(row, "exertion_level", "exertion_level") for row in rows]
    wearable_motion_states = Counter(_wearable_motion_state(row) for row in rows if _wearable_motion_state(row) is not None)
    wearable_motion_delta = [
        _wearable_number(row, "watch_motion_delta_mg", "wearable_motion_delta_mg") for row in rows
    ]
    wearable_acceleration = [
        _wearable_number(row, "acceleration_magnitude_mg", "wearable_acceleration_magnitude_mg") for row in rows
    ]
    pose_confidence = [_number(row.get("pose_confidence", row.get("confidence"))) for row in rows]

    summary = {
        "schema_version": "capture-analysis-v1",
        "capture": {
            "session": metadata.get("session", jsonl_path.parent.name),
            "label": metadata.get("label"),
            "path": str(jsonl_path.parent),
            "jsonl": str(jsonl_path),
            "frames": frame_count,
            "duration_s": _round(duration_s),
            "effective_fps": _round(effective_fps),
            "metadata": metadata,
        },
        "quality": {
            "esp32_connected_ratio": _ratio(esp32_connected_frames, frame_count),
            "esp32_sample_ratio": _ratio(esp32_with_samples, frame_count),
            "wearable_connected_ratio": _ratio(wearable_connected_frames, frame_count),
            "wearable_hr_ratio": _ratio(wearable_with_hr, frame_count),
            "wearable_motion_ratio": _ratio(wearable_with_motion, frame_count),
            "pose_ready_ratio": _ratio(pose_ready_frames, frame_count),
            "arms_visible_ratio": _ratio(arms_visible_frames, frame_count),
            "usable_for_imu_analysis": esp32_with_samples >= max(5, frame_count * 0.5),
            "usable_for_wearable_analysis": wearable_with_hr >= max(5, frame_count * 0.3),
            "usable_for_wearable_motion_crosscheck": wearable_with_motion >= max(5, frame_count * 0.3),
            "usable_for_pose_analysis": arms_visible_frames >= max(5, frame_count * 0.35),
        },
        "vision": {
            "statuses": dict(vision_statuses),
            "pose_confidence": _series_stats(pose_confidence),
        },
        "esp32": {
            "statuses": dict(esp32_statuses),
            "motion_states": dict(imu_states),
            "motion_delta_mps2": _series_stats(imu_motion),
            "angular_delta_dps": _series_stats(imu_angular),
            "orientation_delta_deg": _series_stats(imu_orientation),
            "motion_intensity": _series_stats(imu_intensity),
            "stability_index": _series_stats(imu_stability),
            "sample_interval_ms": _series_stats(sample_ms),
            "sample_rate_hz": _sample_rate_stats(sample_ms),
        },
        "wearable": {
            "statuses": dict(wearable_statuses),
            "heart_rate_bpm": _series_stats(heart_rate),
            "exertion_level": _series_stats(exertion),
            "intensity_zones": dict(intensity_zones),
            "motion_states": dict(wearable_motion_states),
            "motion_delta_mg": _series_stats(wearable_motion_delta),
            "acceleration_magnitude_mg": _series_stats(wearable_acceleration),
        },
        "events": dict(event_counts),
    }
    summary["recommendations"] = _recommendations(summary)
    return summary


def write_capture_report(summary: dict[str, Any], out_path: Path) -> None:
    """Write a human-readable markdown report for one capture summary."""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(format_capture_report(summary), encoding="utf-8")


def format_capture_report(summary: dict[str, Any]) -> str:
    """Return a short markdown report suitable for project notes."""

    capture = summary["capture"]
    quality = summary["quality"]
    esp32 = summary["esp32"]
    wearable = summary["wearable"]
    vision = summary["vision"]
    sample_rate = esp32["sample_rate_hz"]
    motion = esp32["motion_intensity"]
    angular = esp32["angular_delta_dps"]
    heart_rate = wearable["heart_rate_bpm"]
    exertion = wearable["exertion_level"]
    pose = vision["pose_confidence"]
    recommendations = summary.get("recommendations", [])

    lines = [
        f"# Capture Analysis - {capture['session']}",
        "",
        f"- Label: {capture.get('label') or 'unknown'}",
        f"- Frames: {capture['frames']}",
        f"- Duration: {capture['duration_s']} s",
        f"- Effective FPS: {capture['effective_fps']}",
        f"- ESP32 sample ratio: {quality['esp32_sample_ratio']}",
        f"- Wearable HR ratio: {quality['wearable_hr_ratio']}",
        f"- Wearable motion cross-check ratio: {quality['wearable_motion_ratio']}",
        f"- Pose ready ratio: {quality['pose_ready_ratio']}",
        f"- Arms visible ratio: {quality['arms_visible_ratio']}",
        "",
        "## ESP32 / IMU",
        "",
        f"- Motion states: {esp32['motion_states']}",
        f"- Motion intensity p50/p90/max: {_stat_triplet(motion)}",
        f"- Angular delta p50/p90/max: {_stat_triplet(angular)} dps",
        f"- Sample rate p50: {sample_rate.get('p50')} Hz",
        "",
        "## Garmin / Wearable",
        "",
        f"- Statuses: {wearable['statuses']}",
        f"- Heart-rate p50/p90/max: {_stat_triplet(heart_rate)} bpm",
        f"- Exertion p50/p90/max: {_stat_triplet(exertion)}",
        f"- Intensity zones: {wearable['intensity_zones']}",
        f"- Wrist motion states: {wearable['motion_states']}",
        f"- Wrist motion delta p50/p90/max: {_stat_triplet(wearable['motion_delta_mg'])} mg",
        f"- Wrist acceleration magnitude p50/p90/max: {_stat_triplet(wearable['acceleration_magnitude_mg'])} mg",
        "",
        "## Vision",
        "",
        f"- Statuses: {vision['statuses']}",
        f"- Pose confidence p50/p90/max: {_stat_triplet(pose)}",
        "",
        "## Recommendations",
        "",
    ]
    if recommendations:
        lines.extend(f"- {item}" for item in recommendations)
    else:
        lines.append("- Capture quality is usable for the current sensor-fusion pipeline.")
    lines.append("")
    return "\n".join(lines)


def print_capture_summary(summary: dict[str, Any]) -> None:
    """Print a concise terminal summary for quick iteration."""

    capture = summary["capture"]
    quality = summary["quality"]
    esp32 = summary["esp32"]
    print(f"Capture: {capture['session']}")
    print(f"Frames: {capture['frames']} | Duration: {capture['duration_s']}s | FPS: {capture['effective_fps']}")
    print(
        "Quality: "
        f"ESP32 samples={quality['esp32_sample_ratio']} "
        f"wearable_hr={quality['wearable_hr_ratio']} "
        f"pose_ready={quality['pose_ready_ratio']} "
        f"arms_visible={quality['arms_visible_ratio']}"
    )
    print(f"IMU states: {esp32['motion_states']}")
    print(f"IMU intensity p50/p90/max: {_stat_triplet(esp32['motion_intensity'])}")
    print(f"IMU angular p50/p90/max: {_stat_triplet(esp32['angular_delta_dps'])} dps")
    print(f"Garmin HR p50/p90/max: {_stat_triplet(summary['wearable']['heart_rate_bpm'])} bpm")
    print(f"Garmin zones: {summary['wearable']['intensity_zones']}")
    print(f"Garmin wrist motion states: {summary['wearable']['motion_states']}")
    print("Recommendations:")
    recommendations = summary.get("recommendations", [])
    if not recommendations:
        print("- Capture quality is usable for the current sensor-fusion pipeline.")
    for item in recommendations:
        print(f"- {item}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _latest_esp32(row: dict[str, Any]) -> dict[str, Any] | None:
    latest = _path(row, "game_control.esp32_glove")
    if isinstance(latest, dict) and latest.get("timestamp_ms") is not None:
        return latest
    latest = _path(row, "esp32.latest")
    if isinstance(latest, dict) and latest.get("timestamp_ms") is not None:
        return latest
    return None


def _imu_number(row: dict[str, Any], glove_key: str, signal_key: str) -> float | None:
    latest = _latest_esp32(row) or {}
    value = latest.get(glove_key)
    if value is None:
        value = _path(row, f"signal_log.{signal_key}")
    return _number(value)


def _imu_intensity(row: dict[str, Any]) -> float | None:
    value = _imu_number(row, "motion_intensity", "imu_motion_intensity")
    if value is not None:
        return value
    motion_delta = _imu_number(row, "motion_delta_mps2", "imu_motion_delta_mps2")
    angular_delta = _imu_number(row, "angular_delta_dps", "imu_angular_delta_dps")
    orientation_delta = _imu_number(row, "orientation_delta_deg", "imu_orientation_delta_deg")
    if motion_delta is None and angular_delta is None and orientation_delta is None:
        return None
    return round(
        min(
            1.0,
            max(
                0.0 if motion_delta is None else motion_delta / 8.0,
                0.0 if angular_delta is None else angular_delta / 180.0,
                0.0 if orientation_delta is None else orientation_delta / 24.0,
            ),
        ),
        3,
    )


def _imu_state(row: dict[str, Any]) -> str | None:
    latest = _latest_esp32(row) or {}
    state = latest.get("motion_state") or _path(row, "signal_log.imu_motion_state")
    if state:
        return str(state)
    intensity = _imu_intensity(row)
    if intensity is None:
        return None
    if intensity < 0.08:
        return "steady"
    if intensity < 0.28:
        return "small_motion"
    if intensity < 0.72:
        return "active"
    return "burst"


def _wearable_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    latest = _path(row, "game_control.wearable_watch")
    if isinstance(latest, dict):
        return latest
    latest = row.get("wearable")
    return latest if isinstance(latest, dict) else None


def _wearable_motion_state(row: dict[str, Any]) -> str | None:
    """Return the Garmin-derived wrist state when the capture contains it."""

    latest = _wearable_payload(row) or {}
    value = latest.get("watch_motion_state")
    if value is None:
        value = _path(row, "signal_log.wearable_motion_state")
    return None if value is None else str(value)


def _wearable_number(row: dict[str, Any], wearable_key: str, signal_key: str) -> float | None:
    latest = _wearable_payload(row) or {}
    value = latest.get(wearable_key)
    if value is None:
        value = _path(row, f"game_control.user_state.{wearable_key}")
    if value is None:
        value = _path(row, f"signal_log.{signal_key}")
    return _number(value)


def _wearable_zone(row: dict[str, Any]) -> str | None:
    value = _path(row, "game_control.user_state.intensity_zone")
    if value is None:
        value = _path(row, "game_control.wearable_watch.intensity_zone")
    if value is None:
        value = _path(row, "signal_log.intensity_zone")
    return None if value is None else str(value)


def _arm_visible(row: dict[str, Any]) -> bool:
    for side in ("left", "right"):
        if _path(row, f"motion_analysis.sides.{side}.visible") is True:
            return True
    return False


def _events(row: dict[str, Any]) -> list[str]:
    events = _path(row, "game_control.events")
    return [str(event) for event in events] if isinstance(events, list) else []


def _recommendations(summary: dict[str, Any]) -> list[str]:
    quality = summary["quality"]
    esp32 = summary["esp32"]
    recommendations: list[str] = []
    if not quality["usable_for_imu_analysis"]:
        recommendations.append(
            "ESP32 samples are missing or sparse; close any other serial monitor and use the normal auto transport for USB serial plus Wi-Fi."
        )
    if not quality["usable_for_wearable_analysis"]:
        recommendations.append(
            "Garmin heart-rate samples are missing or sparse; start the BLE bridge or simulator before capture and pass --wearable-json."
        )
    if quality["arms_visible_ratio"] < 0.35:
        recommendations.append("Camera pose is weak for arms; place the board/hand inside frame and keep wrists visible during calibration.")
    if quality["pose_ready_ratio"] < 0.5:
        recommendations.append("Run a longer calibration with arms visible or reduce occlusion before using pose-derived arm metrics.")
    sample_rate = esp32["sample_rate_hz"].get("p50")
    if sample_rate is not None and sample_rate < 10:
        recommendations.append("IMU sample rate is low; avoid running another app that reads the same ESP32 serial or UDP stream.")
    motion_states = esp32.get("motion_states", {})
    if motion_states and motion_states.get("burst", 0) > motion_states.get("active", 0) + motion_states.get("small_motion", 0):
        recommendations.append("This capture is dominated by bursts; record one slower tilt sweep too for calibration and threshold comparison.")
    return recommendations


def _sample_rate_stats(sample_ms: list[float | None]) -> dict[str, float | int | None]:
    rates = [1000.0 / value for value in sample_ms if value and value > 0]
    return _series_stats(rates)


def _series_stats(values: list[float | None]) -> dict[str, float | int | None]:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return {"count": 0, "min": None, "p50": None, "p75": None, "p90": None, "p95": None, "max": None}
    return {
        "count": len(clean),
        "min": _round(min(clean)),
        "p50": _round(_percentile(clean, 50)),
        "p75": _round(_percentile(clean, 75)),
        "p90": _round(_percentile(clean, 90)),
        "p95": _round(_percentile(clean, 95)),
        "max": _round(max(clean)),
    }


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _path(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else round(numerator / denominator, 3)


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 3)


def _stat_triplet(stats: dict[str, Any]) -> str:
    return f"{stats.get('p50')}/{stats.get('p90')}/{stats.get('max')}"
