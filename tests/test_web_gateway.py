"""Smoke tests for the local FitQuest browser stream."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.web_gateway import WebGateway, WebStream
from ironquest.ui import compose_camera_detection_preview


def test_web_stream_keeps_latest_payload_and_sequence() -> None:
    stream = WebStream()
    stream.publish({"game_control": {"status": "ready"}})

    event = stream.wait_for_event(0, timeout=0.05)

    assert event is not None
    assert event["sequence"] == 1
    assert event["payload"]["game_control"]["status"] == "ready"


def test_web_gateway_serves_client_and_health_endpoint() -> None:
    gateway = WebGateway(host="127.0.0.1", port=0)
    gateway.start()
    try:
        with urllib.request.urlopen(f"{gateway.url}api/health", timeout=2.0) as response:
            health = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{gateway.url}fitquest_game.html", timeout=2.0) as response:
            html = response.read().decode("utf-8")

        assert health["status"] == "ok"
        assert health["stream"] == "waiting"
        assert "SENSOR-FUSION WORKOUT" in html
    finally:
        gateway.close()


def test_web_gateway_serves_vendored_three_js() -> None:
    gateway = WebGateway(host="127.0.0.1", port=0)
    gateway.start()
    try:
        with urllib.request.urlopen(f"{gateway.url}vendor/three.min.js", timeout=2.0) as response:
            body = response.read()
        assert response.status == 200
        assert b"THREE" in body
    finally:
        gateway.close()


def test_web_gateway_blocks_vendor_path_traversal() -> None:
    gateway = WebGateway(host="127.0.0.1", port=0)
    gateway.start()
    try:
        request = urllib.request.Request(f"{gateway.url}vendor/../../ironquest/cli.py")
        try:
            urllib.request.urlopen(request, timeout=2.0)
            raised = False
        except urllib.error.HTTPError as error:
            raised = True
            assert error.code == 404
        assert raised
    finally:
        gateway.close()


def test_web_gateway_queues_detector_controls() -> None:
    gateway = WebGateway(host="127.0.0.1", port=0)
    gateway.start()
    try:
        request = urllib.request.Request(
            f"{gateway.url}api/control",
            data=json.dumps({"action": "calibrate"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2.0) as response:
            result = json.loads(response.read().decode("utf-8"))
        assert result == {"status": "accepted", "action": "calibrate"}
        assert gateway.poll_controls() == ["calibrate"]
    finally:
        gateway.close()


def test_browser_preview_keeps_the_camera_surface_clean() -> None:
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    preview = compose_camera_detection_preview(
        frame,
        {"object_detection": {"detections": []}},
        pose=None,
        object_result=None,
        display_width=160,
    )

    assert preview.shape == frame.shape
    assert np.array_equal(preview, frame)
