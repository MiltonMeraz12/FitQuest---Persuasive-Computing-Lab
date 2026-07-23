"""Regression checks for compact hardware labels in the live HUD."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.ui import esp32_sensor_label, sensor_label


def test_waiting_label_does_not_mistake_udp_listener_for_live_device() -> None:
    assert sensor_label("listening_waiting_for_data") == "WAITING"
    assert esp32_sensor_label({"status": "listening_waiting_for_data", "transport": "udp"}) == "WAITING"


def test_live_transport_label_stays_specific() -> None:
    assert esp32_sensor_label({"status": "connected", "transport_summary": "WIFI"}) == "WIFI"
    assert esp32_sensor_label({"status": "connected", "transport_summary": "USB"}) == "USB"


def test_stale_and_reconnect_labels_explain_transient_loss() -> None:
    assert sensor_label("stale") == "STALE"
    assert sensor_label("serial_disconnected") == "RECONNECT"
