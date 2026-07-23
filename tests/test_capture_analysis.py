"""Regression tests for offline capture analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.capture_analysis import analyze_capture, format_capture_report


def test_analyze_capture_summarizes_imu_quality(tmp_path: Path) -> None:
    session = tmp_path / "20260629_test_capture"
    session.mkdir()
    (session / "metadata.json").write_text(
        json.dumps({"session": session.name, "label": "test_capture"}),
        encoding="utf-8",
    )
    rows = [
        _row(0.0, "connected", "ready", 0.04, 4.0, 0.2),
        _row(0.1, "connected", "ready", 0.45, 72.0, 6.0),
        _row(0.2, "connected", "ready", 0.95, 240.0, 28.0),
    ]
    jsonl = session / "motion_payloads.jsonl"
    jsonl.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    summary = analyze_capture(jsonl)
    report = format_capture_report(summary)

    assert summary["capture"]["frames"] == 3
    assert summary["quality"]["esp32_sample_ratio"] == 1.0
    assert summary["quality"]["usable_for_imu_analysis"] is False
    assert summary["esp32"]["motion_states"]["burst"] == 1
    assert "Capture Analysis" in report
    assert "COM7" not in report


def test_analyze_capture_summarizes_wearable_quality(tmp_path: Path) -> None:
    session = tmp_path / "20260708_wearable_capture"
    session.mkdir()
    rows = [
        _row(0.0, "connected", "ready", 0.04, 4.0, 0.2, heart_rate=88, exertion=0.2, intensity_zone="low", wearable_motion_state="steady", wearable_motion_delta_mg=4.0, wearable_acceleration_magnitude_mg=1000.0),
        _row(0.1, "connected", "ready", 0.08, 8.0, 0.4, heart_rate=96, exertion=0.3, intensity_zone="low", wearable_motion_state="steady", wearable_motion_delta_mg=8.0, wearable_acceleration_magnitude_mg=1001.0),
        _row(0.2, "connected", "ready", 0.12, 12.0, 0.6, heart_rate=112, exertion=0.45, intensity_zone="moderate", wearable_motion_state="moving", wearable_motion_delta_mg=12.0, wearable_acceleration_magnitude_mg=1002.0),
        _row(0.3, "connected", "ready", 0.16, 16.0, 0.8, heart_rate=128, exertion=0.62, intensity_zone="moderate", wearable_motion_state="moving", wearable_motion_delta_mg=16.0, wearable_acceleration_magnitude_mg=1003.0),
        _row(0.4, "connected", "ready", 0.20, 20.0, 1.0, heart_rate=146, exertion=0.78, intensity_zone="high", wearable_motion_state="active", wearable_motion_delta_mg=20.0, wearable_acceleration_magnitude_mg=1004.0),
    ]
    jsonl = session / "motion_payloads.jsonl"
    jsonl.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    summary = analyze_capture(jsonl)
    report = format_capture_report(summary)

    assert summary["quality"]["wearable_hr_ratio"] == 1.0
    assert summary["quality"]["wearable_motion_ratio"] == 1.0
    assert summary["quality"]["usable_for_wearable_motion_crosscheck"] is True
    assert summary["quality"]["usable_for_wearable_analysis"] is True
    assert summary["wearable"]["heart_rate_bpm"]["p50"] == 112.0
    assert summary["wearable"]["intensity_zones"] == {"low": 2, "moderate": 2, "high": 1}
    assert summary["wearable"]["motion_states"] == {"steady": 2, "moving": 2, "active": 1}
    assert summary["wearable"]["motion_delta_mg"]["p50"] == 12.0
    assert "Garmin / Wearable" in report


def _row(
    timestamp: float,
    esp32_status: str,
    status: str,
    motion_delta: float,
    angular_delta: float,
    orientation_delta: float,
    heart_rate: int | None = None,
    exertion: float | None = None,
    intensity_zone: str | None = None,
    wearable_motion_state: str | None = None,
    wearable_motion_delta_mg: float | None = None,
    wearable_acceleration_magnitude_mg: float | None = None,
) -> dict:
    sensor_status = {"esp32_glove": esp32_status}
    game_control = {
        "status": status,
        "sensor_status": sensor_status,
        "events": [],
        "esp32_glove": {
            "timestamp_ms": int(timestamp * 1000),
            "motion_delta_mps2": motion_delta,
            "angular_delta_dps": angular_delta,
            "orientation_delta_deg": orientation_delta,
            "motion_intensity": max(motion_delta / 8.0, angular_delta / 180.0, orientation_delta / 24.0),
            "sample_interval_ms": 66.0,
            "stability_index": 0.3,
        },
    }
    if heart_rate is not None:
        sensor_status["wearable_watch"] = "connected"
        game_control["wearable_watch"] = {
            "status": "connected",
            "device": "garmin_venu_3",
            "heart_rate_bpm": heart_rate,
            "exertion_level": exertion,
            "intensity_zone": intensity_zone,
            "watch_motion_state": wearable_motion_state,
            "watch_motion_delta_mg": wearable_motion_delta_mg,
            "acceleration_magnitude_mg": wearable_acceleration_magnitude_mg,
        }
        game_control["user_state"] = {
            "heart_rate_bpm": heart_rate,
            "exertion_level": exertion,
            "intensity_zone": intensity_zone,
        }

    return {
        "timestamp": timestamp,
        "pose_confidence": 0.9,
        "motion_analysis": {
            "status": "ok",
            "sides": {"right": {"visible": True}},
        },
        "game_control": game_control,
    }
