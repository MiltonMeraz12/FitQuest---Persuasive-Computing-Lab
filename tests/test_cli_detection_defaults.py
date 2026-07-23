"""Regression checks for detection presets used by the live middleware."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.cli import (
    DEFAULT_WEARABLE_LIVE_JSON,
    LIVE_COMMAND_ALIASES,
    apply_live_command_defaults,
    build_esp32_bridge,
    build_parser,
    fill_detection_defaults,
)


def test_full_preset_enables_dumbbell_tracking_without_abandoned_model() -> None:
    parser = build_parser()
    args = parser.parse_args(["full", "--source", "sample.mp4", "--no-show"])
    args.mode = "full"

    filled = fill_detection_defaults(args)

    assert filled.mode == "full"
    assert filled.object_model is not None
    assert filled.object_imgsz == 640
    assert filled.object_conf == 0.20
    assert filled.object_track_hold_frames == 4
    assert filled.dumbbell_conf == 0.30
    assert filled.weight_conf == 0.50
    assert filled.calibration_seconds == 7.0
    assert filled.esp32_side == "right"
    assert filled.esp32_transport == "auto"
    assert filled.esp32_udp_port == 4210
    assert filled.wearable_side == "left"


def test_legacy_mode_is_not_a_valid_runtime_preset() -> None:
    parser = build_parser()
    legacy_mode = "legacy_keypoints"

    with pytest.raises(SystemExit):
        parser.parse_args(["detect", "--mode", legacy_mode, "--source", "sample.mp4", "--no-show"])


def test_esp32_transport_none_disables_bridge() -> None:
    parser = build_parser()
    args = parser.parse_args(["detect", "--mode", "full", "--source", "sample.mp4", "--esp32-transport", "none", "--no-show"])
    args = fill_detection_defaults(args)

    assert args.esp32_transport == "none"
    assert build_esp32_bridge(args) is None


def test_run_alias_uses_one_command_live_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--source", "sample.mp4", "--no-show"])

    configured = fill_detection_defaults(apply_live_command_defaults(args))

    assert configured.mode == "full"
    assert configured.object_model is not None
    assert configured.esp32_transport == "auto"
    assert configured.esp32_udp_port == 4210
    assert configured.ui_detail == "debug"
    assert configured.wearable_stale_seconds == 5.0
    assert configured.wearable_json == DEFAULT_WEARABLE_LIVE_JSON
    assert configured.garmin_bridge is False
    assert configured.garmin_connectiq_bridge is True
    assert configured.garmin_connectiq_port == 8765


def test_run_alias_can_disable_background_garmin_bridge() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--source", "sample.mp4", "--no-show", "--no-garmin-bridge"])

    configured = fill_detection_defaults(apply_live_command_defaults(args))

    assert configured.garmin_bridge is False


def test_run_alias_can_disable_connectiq_bridge() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--source", "sample.mp4", "--no-show", "--no-garmin-connectiq-bridge"])

    configured = fill_detection_defaults(apply_live_command_defaults(args))

    assert configured.garmin_connectiq_bridge is False


def test_live_command_aliases_cover_full_demo_and_run() -> None:
    # "full", "demo", and "run" are aliases of one subparser and are meant to
    # share the same live-session lock and defaults.
    assert LIVE_COMMAND_ALIASES == {"full", "demo", "run"}


def test_full_and_demo_aliases_get_the_same_live_defaults_as_run() -> None:
    parser = build_parser()
    for command in ("full", "demo", "run"):
        args = parser.parse_args([command, "--source", "sample.mp4", "--no-show"])
        configured = fill_detection_defaults(apply_live_command_defaults(args))

        assert configured.command == command
        assert configured.esp32_transport == "auto"
        assert configured.ui_detail == "debug"
        assert configured.wearable_stale_seconds == 5.0
        assert configured.wearable_json == DEFAULT_WEARABLE_LIVE_JSON


def test_esp32_transport_auto_builds_hybrid_bridge() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--source", "sample.mp4", "--no-show"])
    args = fill_detection_defaults(apply_live_command_defaults(args))
    bridge = build_esp32_bridge(args)

    try:
        assert bridge is not None
        assert bridge.__class__.__name__ == "ESP32AutoBridge"
    finally:
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    test_full_preset_enables_dumbbell_tracking_without_abandoned_model()
    test_legacy_mode_is_not_a_valid_runtime_preset()
    test_esp32_transport_none_disables_bridge()
    test_run_alias_uses_one_command_live_defaults()
    test_esp32_transport_auto_builds_hybrid_bridge()
    test_run_alias_can_disable_connectiq_bridge()
    test_live_command_aliases_cover_full_demo_and_run()
    test_full_and_demo_aliases_get_the_same_live_defaults_as_run()
    print("CLI detection defaults tests passed")
