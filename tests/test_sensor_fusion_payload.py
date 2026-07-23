"""Regression checks for the sensor-fusion middleware contract."""

from __future__ import annotations

import sys
import socket
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.game_controls import EventDebouncer, build_game_control_payload
from ironquest.sensors import ESP32AutoBridge, ESP32Telemetry, ESP32UdpBridge, WearableFileBridge, normalise_wearable_payload


def test_esp32_payload_accepts_orientation_aliases() -> None:
    sample = ESP32Telemetry.from_raw(
        {
            "device_id": "esp32_0",
            "timestamp_ms": 123,
            "mount": "right_gym_glove",
            "pitch": 4.2,
            "roll": -1.0,
            "yaw": 88.0,
            "accel": [0.1, 0.2, 9.8],
            "gyro": {"x": 1.0, "y": 2.0, "z": 3.0},
        },
        received_at=10.0,
    )

    assert sample is not None
    payload = sample.as_payload()
    assert payload["orientation_euler_deg"] == {"pitch": 4.2, "roll": -1.0, "yaw": 88.0}
    assert payload["accel_mps2"]["z"] == 9.8
    assert payload["gyro_dps"]["x"] == 1.0


def test_esp32_payload_accepts_real_bno08x_firmware_shape() -> None:
    sample = ESP32Telemetry.from_raw(
        {
            "device_id": "esp32_0",
            "timestamp_ms": 12345,
            "mount": "right_gym_glove",
            "orientation_euler_deg": {"pitch": 1.2, "roll": -0.5, "yaw": 30.1},
            "accel_mps2": {"x": 0.1, "y": 0.2, "z": 9.7},
            "gyro_dps": {"x": 0.0, "y": 0.0, "z": 0.3},
        },
        received_at=10.0,
    )

    assert sample is not None
    payload = sample.as_payload()
    assert payload["device_id"] == "esp32_0"
    assert payload["mount"] == "right_gym_glove"
    assert payload["orientation_euler_deg"]["yaw"] == 30.1
    assert payload["accel_mps2"]["z"] == 9.7
    assert payload["gyro_dps"]["z"] == 0.3


def test_esp32_payload_derives_motion_quality_placeholders() -> None:
    first = ESP32Telemetry.from_raw(
        {
            "device_id": "esp32_0",
            "timestamp_ms": 100,
            "pitch": 0.0,
            "roll": 0.0,
            "yaw": 0.0,
            "accel": [0.0, 0.0, 9.8],
            "gyro": [0.0, 0.0, 0.0],
        },
        received_at=10.0,
    )
    second = ESP32Telemetry.from_raw(
        {
            "device_id": "esp32_0",
            "timestamp_ms": 120,
            "pitch": 1.0,
            "roll": 0.5,
            "yaw": 0.0,
            "accel": [0.2, 0.1, 9.9],
            "gyro": [1.0, 0.0, 0.0],
        },
        received_at=10.02,
    )

    assert first is not None
    assert second is not None
    payload = second.with_motion_quality(first).as_payload()

    assert payload["sample_interval_ms"] == 20.0
    assert payload["motion_delta_mps2"] > 0
    assert 0.0 < payload["stability_index"] < 1.0
    assert payload["orientation_delta_deg"] > 0


def test_esp32_sample_interval_prefers_firmware_timestamp() -> None:
    first = ESP32Telemetry.from_raw(
        {"device_id": "esp32_0", "timestamp_ms": 1000, "accel_mps2": {"x": 0, "y": 0, "z": 9.8}},
        received_at=10.0,
    )
    second = ESP32Telemetry.from_raw(
        {"device_id": "esp32_0", "timestamp_ms": 1066, "accel_mps2": {"x": 0, "y": 0, "z": 9.8}},
        received_at=10.002,
    )

    assert first is not None
    assert second is not None
    assert second.with_motion_quality(first).as_payload()["sample_interval_ms"] == 66.0


def test_esp32_udp_bridge_accepts_wireless_json() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    udp_port = probe.getsockname()[1]
    probe.close()

    bridge = ESP32UdpBridge(host="127.0.0.1", udp_port=udp_port)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(
            b'{"device_id":"esp32_0","timestamp_ms":2000,"mount":"right_gym_glove",'
            b'"orientation_euler_deg":{"pitch":1.0,"roll":2.0,"yaw":3.0},'
            b'"accel_mps2":{"x":0.1,"y":0.2,"z":9.7},'
            b'"gyro_dps":{"x":0.0,"y":0.0,"z":0.3}}\n',
            ("127.0.0.1", udp_port),
        )
        time.sleep(0.02)
        payload = bridge.poll()
    finally:
        sender.close()
        bridge.close()

    assert payload["status"] == "connected"
    assert payload["transport"] == "udp"
    assert payload["latest"]["mount"] == "right_gym_glove"
    assert payload["latest"]["orientation_euler_deg"]["yaw"] == 3.0


def test_esp32_udp_bridge_marks_old_samples_stale_and_recovers() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    udp_port = probe.getsockname()[1]
    probe.close()

    bridge = ESP32UdpBridge(host="127.0.0.1", udp_port=udp_port, stale_seconds=0.1)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(
            b'{"device_id":"esp32_0","timestamp_ms":2100,"accel_mps2":{"x":1,"y":2,"z":3}}\n',
            ("127.0.0.1", udp_port),
        )
        time.sleep(0.02)
        connected = bridge.poll()
        time.sleep(0.15)
        stale = bridge.poll()

        sender.sendto(
            b'{"device_id":"esp32_0","timestamp_ms":2200,"accel_mps2":{"x":4,"y":5,"z":6}}\n',
            ("127.0.0.1", udp_port),
        )
        time.sleep(0.02)
        reconnected = bridge.poll()
    finally:
        sender.close()
        bridge.close()

    assert connected["status"] == "connected"
    assert stale["status"] == "stale"
    assert stale["sample_age_seconds"] > 0.1
    assert reconnected["status"] == "connected"
    assert reconnected["latest"]["timestamp_ms"] == 2200


class _RecordingSocket:
    """Stand-in for a UDP socket that records outgoing discovery packets."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def recvfrom(self, bufsize: int):
        raise BlockingIOError()

    def sendto(self, data: bytes, addr) -> None:
        self.sent.append(data)

    def close(self) -> None:
        pass


def test_esp32_udp_bridge_discovery_message_includes_shared_token() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    udp_port = probe.getsockname()[1]
    probe.close()

    bridge = ESP32UdpBridge(host="127.0.0.1", udp_port=udp_port, discovery_token="test-token-123")
    bridge.socket.close()
    recorder = _RecordingSocket()
    bridge.socket = recorder
    try:
        bridge.poll()  # no packets waiting, so this should trigger a discovery send
    finally:
        bridge.close()

    assert recorder.sent == [b"ironquest_discover:test-token-123\n"]


def test_esp32_auto_bridge_accepts_udp_without_serial() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    udp_port = probe.getsockname()[1]
    probe.close()

    bridge = ESP32AutoBridge(serial_port=None, udp_host="127.0.0.1", udp_port=udp_port)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        waiting = bridge.poll()
        sender.sendto(
            b'{"device_id":"esp32_0","timestamp_ms":3000,"mount":"right_gym_glove",'
            b'"accel_mps2":{"x":1.0,"y":2.0,"z":3.0},'
            b'"gyro_dps":{"x":4.0,"y":5.0,"z":6.0}}\n',
            ("127.0.0.1", udp_port),
        )
        time.sleep(0.02)
        payload = bridge.poll()
    finally:
        sender.close()
        bridge.close()

    assert payload["status"] == "connected"
    assert waiting["status"] == "listening_waiting_for_data"
    assert payload["transport"] == "auto:udp"
    assert payload["auto_transport"] == "udp"
    assert payload["transport_summary"] == "WIFI"
    assert payload["connected_transports"] == ["wifi"]
    assert payload["sources"]["udp"]["status"] == "connected"
    assert payload["latest"]["accel_mps2"]["x"] == 1.0


def test_esp32_auto_bridge_exposes_stale_state_until_wifi_recovers() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    udp_port = probe.getsockname()[1]
    probe.close()

    bridge = ESP32AutoBridge(
        serial_port=None,
        udp_host="127.0.0.1",
        udp_port=udp_port,
        stale_seconds=0.1,
    )
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(
            b'{"device_id":"esp32_0","timestamp_ms":3100,"accel_mps2":{"x":1,"y":2,"z":3}}\n',
            ("127.0.0.1", udp_port),
        )
        time.sleep(0.02)
        connected = bridge.poll()
        time.sleep(0.15)
        stale = bridge.poll()

        sender.sendto(
            b'{"device_id":"esp32_0","timestamp_ms":3200,"accel_mps2":{"x":4,"y":5,"z":6}}\n',
            ("127.0.0.1", udp_port),
        )
        time.sleep(0.02)
        reconnected = bridge.poll()
    finally:
        sender.close()
        bridge.close()

    assert connected["status"] == "connected"
    assert connected["transport_summary"] == "WIFI"
    assert stale["status"] == "stale"
    assert stale["transport_summary"] == "WAIT"
    assert stale["connected_transports"] == []
    assert stale["latest"] is None
    assert reconnected["status"] == "connected"
    assert reconnected["transport_summary"] == "WIFI"
    assert reconnected["latest"]["timestamp_ms"] == 3200


def test_wearable_payload_normalises_garmin_heart_rate() -> None:
    payload = normalise_wearable_payload(
        {
            "device": "garmin_venu_3",
            "device_name": "Venu 3",
            "device_address": "E0:48:24:99:5B:51",
            "provider": "garmin",
            "bpm": 96,
            "resting_heart_rate_bpm": 58,
            "max_heart_rate_bpm": 168,
            "rr_intervals_ms": [812.5, "820.0"],
            "energy_expended_kj": 12,
            "body_battery": 74,
            "pulse_ox": 98,
            "respiration_rate": 15,
            "steps": 1234,
            "calories": 87,
            "activity_state": "strength_training",
            "sample_type": "ble_heart_rate",
        }
    )

    assert payload["device"] == "garmin_venu_3"
    assert payload["device_name"] == "Venu 3"
    assert payload["device_address"] == "E0:48:24:99:5B:51"
    assert payload["provider"] == "garmin"
    assert payload["heart_rate_bpm"] == 96
    assert payload["resting_heart_rate_bpm"] == 58
    assert payload["max_heart_rate_bpm"] == 168
    assert payload["rr_intervals_ms"] == [812.5, 820.0]
    assert payload["energy_expended_kj"] == 12
    assert payload["body_battery"] == 74
    assert payload["pulse_ox"] == 98
    assert payload["respiration_rate"] == 15
    assert payload["steps"] == 1234
    assert payload["calories"] == 87
    assert payload["sample_type"] == "ble_heart_rate"


def test_wearable_file_bridge_accepts_a_source_that_appears_after_start(tmp_path: Path) -> None:
    path = tmp_path / "wearable_live.json"
    bridge = WearableFileBridge(path, max_reads_per_second=1000)

    waiting = bridge.poll()
    path.write_text(
        '{"status":"connected","heart_rate_bpm":92,"sequence":1}',
        encoding="utf-8",
    )
    time.sleep(0.01)
    connected = bridge.poll()

    assert waiting["status"] == "missing_file"
    assert connected["status"] == "connected"
    assert connected["heart_rate_bpm"] == 92


def test_wearable_payload_preserves_rich_garmin_context() -> None:
    payload = normalise_wearable_payload(
        {
            "device": "garmin_venu_3",
            "sample_type": "connect_iq_live",
            "source": "connect_iq_sensor_stream",
            "battery": 82,
            "battery_unit": "percent",
            "hrv_ms": 43.5,
            "sequence": 17,
            "sent_count": 16,
            "sample_interval_ms": 3000,
            "endpoint_mode": "cloudflare_https",
            "last_http_code": 200,
            "motion": {
                "acceleration": {"x": [10, 20], "y": [1, 2], "z": [1000, 1002]},
                "gyroscope": {"x": 1.5, "y": 2.5, "z": 3.5},
                "acceleration_unit": "mg",
                "gyroscope_unit": "dps",
                "acceleration_magnitude_mg": 1002.2,
                "watch_motion_delta_mg": 9.8,
                "watch_motion_state": "steady",
            },
            "location": {
                "lat": 45.5017,
                "lng": -73.5673,
                "altitude": 12.3,
                "speed": 1.2,
                "quality": "good",
            },
            "activity": {"type": "strength_training", "distance_m": 128.4},
        },
        source="file",
    )

    assert payload["sample_type"] == "connect_iq_live"
    assert payload["source"] == "connect_iq_sensor_stream"
    assert payload["ingest_source"] == "file"
    assert payload["battery"] == 82
    assert payload["battery_unit"] == "percent"
    assert payload["hrv_ms"] == 43.5
    assert payload["sequence"] == 17
    assert payload["sent_count"] == 16
    assert payload["sample_interval_ms"] == 3000.0
    assert payload["endpoint_mode"] == "cloudflare_https"
    assert payload["last_http_code"] == 200
    assert payload["acceleration"] == {"x": 20.0, "y": 2.0, "z": 1002.0}
    assert payload["acceleration_unit"] == "mg"
    assert payload["acceleration_magnitude_mg"] == 1002.2
    assert payload["watch_motion_delta_mg"] == 9.8
    assert payload["watch_motion_state"] == "steady"
    assert payload["gyroscope"] == {"x": 1.5, "y": 2.5, "z": 3.5}
    assert payload["gyroscope_unit"] == "dps"
    assert payload["latitude"] == 45.5017
    assert payload["longitude"] == -73.5673
    assert payload["altitude_m"] == 12.3
    assert payload["speed_mps"] == 1.2
    assert payload["distance_m"] == 128.4
    assert payload["activity_state"] == "strength_training"
    assert payload["location"]["quality"] == "good"


def test_game_control_payload_has_sensor_fusion_sections_without_removed_axes() -> None:
    motion = {
        "status": "ok",
        "signature": "left:overhead | right:torso",
        "tokens": ["left_arm_overhead", "right_dumbbell_loaded"],
        "sides": {
            "left": {
                "visible": True,
                "height_score": 0.8,
                "motion_speed": 0.1,
                "angle_range_deg": 42.0,
                "arm_extension": 0.7,
                "height_signal": 0.8,
                "reach_signal": 0.5,
                "range_utilization": 0.32,
            },
            "right": {
                "visible": True,
                "height_score": 0.4,
                "motion_speed": 0.2,
                "angle_range_deg": 40.0,
                "arm_extension": 0.65,
                "height_signal": 0.4,
                "reach_signal": 0.55,
                "range_utilization": 0.30,
            },
        },
        "body": {"vertical_delta": 0.0, "jump_candidate": False},
        "signal_metrics": {
            "calibration": {"state": "tracking"},
            "sides": {
                "left": {"angle_range_deg": 42.0, "arm_extension": 0.7, "range_utilization": 0.32},
                "right": {"angle_range_deg": 40.0, "arm_extension": 0.65, "range_utilization": 0.30},
            },
            "bilateral": {"symmetry_score": 0.92},
        },
    }
    movement = {
        "pose_confidence": 0.7,
        "object_detection": {
            "status": "ok",
            "detections": [{"label": "dumbbell", "confidence": 0.9, "xyxy": [1, 2, 3, 4]}],
            "accepted_count": 1,
        },
        "limbs": {"sides": {"left": {}, "right": {"dumbbell_near_wrist_or_forearm": True}}},
    }
    esp32 = {
        "status": "connected",
        "transport": "auto:udp",
        "transport_summary": "WIFI",
        "connected_transports": ["wifi"],
        "latest": {
            "mount": "right_glove",
            "orientation_euler_deg": {"pitch": 1.0, "roll": 2.0, "yaw": 3.0},
            "motion_delta_mps2": 1.2,
            "angular_delta_dps": 24.0,
            "orientation_delta_deg": 1.0,
            "stability_index": 0.81,
            "sample_interval_ms": 66.0,
        },
    }
    wearable = {"status": "connected", "device": "garmin_venu_3", "heart_rate_bpm": 145}

    payload = build_game_control_payload(motion, movement, esp32, wearable, esp32_side="right", wearable_side="left")

    assert payload["control_mode"] == "sensor_fusion_engine"
    assert payload["exercise_candidate"]["id"] == "press"
    assert "body_posture" in payload
    assert "dumbbells" in payload
    assert "arm_signals" in payload
    assert "esp32_glove" in payload
    assert "wearable_watch" in payload
    assert payload["axes"]["left_arm_extension"] == 0.7
    assert payload["axes"]["symmetry_score"] == 0.92
    assert payload["axes"]["imu_motion_intensity"] > 0
    assert payload["esp32_glove"]["motion_state"] == "small_motion"
    assert payload["esp32_glove"]["sample_rate_hz"] == 15.15
    assert payload["esp32_glove"]["transport_summary"] == "WIFI"
    assert payload["esp32_glove"]["connected_transports"] == ["wifi"]
    assert payload["esp32_glove"]["mounted_side"] == "right"
    assert payload["arm_signals"]["right"]["hardware"]["esp32_glove"]["stability_index"] == 0.81
    assert payload["arm_signals"]["left"]["hardware"]["wearable_watch"]["heart_rate_bpm"] == 145
    assert payload["user_state"]["intensity_zone"] == "high"
    assert payload["events"] == []


def test_game_control_payload_marks_imu_motion_bursts() -> None:
    motion = {
        "status": "ok",
        "sides": {},
        "body": {},
        "signal_metrics": {"bilateral": {}},
    }
    movement = {"pose_confidence": 0.8, "object_detection": {}, "limbs": {"sides": {}}}
    esp32 = {
        "status": "connected",
        "latest": {
            "mount": "right_gym_glove",
            "orientation_euler_deg": {"pitch": 0.0, "roll": 0.0, "yaw": 0.0},
            "motion_delta_mps2": 9.5,
            "angular_delta_dps": 240.0,
            "orientation_delta_deg": 32.0,
            "stability_index": 0.05,
            "sample_interval_ms": 67.0,
        },
    }

    payload = build_game_control_payload(motion, movement, esp32)

    assert payload["esp32_glove"]["motion_intensity"] == 1.0
    assert payload["esp32_glove"]["motion_state"] == "burst"
    assert "IMU_MOTION_BURST" in payload["events"]


def test_event_debouncer_holds_exercise_candidate_before_switching() -> None:
    motion_press = {"status": "ok", "tokens": ["left_arm_overhead"], "sides": {}, "body": {}, "signal_metrics": {"bilateral": {}}}
    motion_idle = {"status": "ok", "tokens": [], "sides": {}, "body": {}, "signal_metrics": {"bilateral": {}}}
    movement = {"pose_confidence": 0.8, "object_detection": {}, "limbs": {"sides": {}}}
    debouncer = EventDebouncer(hold_frames=3)

    first = build_game_control_payload(motion_press, movement, debouncer=debouncer)
    second = build_game_control_payload(motion_press, movement, debouncer=debouncer)
    third = build_game_control_payload(motion_press, movement, debouncer=debouncer)

    assert first["exercise_candidate"] is None
    assert second["exercise_candidate"] is None
    assert third["exercise_candidate"]["id"] == "press"

    fourth = build_game_control_payload(motion_idle, movement, debouncer=debouncer)
    fifth = build_game_control_payload(motion_idle, movement, debouncer=debouncer)
    sixth = build_game_control_payload(motion_idle, movement, debouncer=debouncer)

    assert fourth["exercise_candidate"]["id"] == "press"
    assert fifth["exercise_candidate"]["id"] == "press"
    assert sixth["exercise_candidate"] is None


def test_event_debouncer_reports_imu_burst_once_per_rising_edge() -> None:
    motion = {"status": "ok", "sides": {}, "body": {}, "signal_metrics": {"bilateral": {}}}
    movement = {"pose_confidence": 0.8, "object_detection": {}, "limbs": {"sides": {}}}
    burst_esp32 = {
        "status": "connected",
        "latest": {
            "mount": "right_gym_glove",
            "orientation_euler_deg": {"pitch": 0.0, "roll": 0.0, "yaw": 0.0},
            "motion_delta_mps2": 9.5,
            "angular_delta_dps": 240.0,
            "orientation_delta_deg": 32.0,
            "stability_index": 0.05,
            "sample_interval_ms": 67.0,
        },
    }
    calm_esp32 = {
        "status": "connected",
        "latest": {
            "mount": "right_gym_glove",
            "orientation_euler_deg": {"pitch": 0.0, "roll": 0.0, "yaw": 0.0},
            "motion_delta_mps2": 0.1,
            "angular_delta_dps": 2.0,
            "orientation_delta_deg": 0.2,
            "stability_index": 0.95,
            "sample_interval_ms": 67.0,
        },
    }
    debouncer = EventDebouncer()

    first = build_game_control_payload(motion, movement, burst_esp32, debouncer=debouncer)
    second = build_game_control_payload(motion, movement, burst_esp32, debouncer=debouncer)
    third = build_game_control_payload(motion, movement, calm_esp32, debouncer=debouncer)
    fourth = build_game_control_payload(motion, movement, burst_esp32, debouncer=debouncer)

    assert "IMU_MOTION_BURST" in first["events"]
    assert "IMU_MOTION_BURST" not in second["events"]
    assert "IMU_MOTION_BURST" not in third["events"]
    assert "IMU_MOTION_BURST" in fourth["events"]
