"""Sensor integration payload models and lightweight hardware readers.

The project can run without Garmin or ESP32 hardware. This module defines the
paper-facing payload contracts now, so detector logs and future game work can
depend on predictable ``wearable`` and ``esp32`` sections while hardware
integration is still being tested.
"""

from __future__ import annotations

import json
import math
import socket
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import sleep, time
from typing import Any

ESP32_PORT_HINTS = (
    "esp32",
    "espressif",
    "cp210",
    "ch340",
    "wch",
    "usb serial",
    "usb jtag",
    "silicon labs",
)

ESP32_DEFAULT_STALE_SECONDS = 2.0


def _sample_age_seconds(sample: "ESP32Telemetry | None") -> float | None:
    """Return the age of a sample using the host receive timestamp."""

    if sample is None:
        return None
    return max(0.0, time() - sample.received_at)


@dataclass(frozen=True)
class Vector3:
    """Three-axis sensor vector in the units declared by the field name."""

    x: float
    y: float
    z: float

    @classmethod
    def from_raw(cls, value: Any) -> "Vector3 | None":
        """Parse a vector from ``{"x": ..}``, ``[x, y, z]``, or ``(x, y, z)``."""

        if isinstance(value, dict):
            try:
                return cls(x=float(value["x"]), y=float(value["y"]), z=float(value["z"]))
            except (KeyError, TypeError, ValueError):
                return None
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                return cls(x=float(value[0]), y=float(value[1]), z=float(value[2]))
            except (TypeError, ValueError):
                return None
        return None

    def as_payload(self) -> dict[str, float]:
        """Return a JSON-friendly vector."""

        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 4),
        }


@dataclass(frozen=True)
class Quaternion:
    """Four-component orientation quaternion from BNO08X-style IMU output."""

    w: float
    x: float
    y: float
    z: float

    @classmethod
    def from_raw(cls, value: Any) -> "Quaternion | None":
        """Parse ``{"w": ..}`` or ``[w, x, y, z]`` quaternion payloads."""

        if isinstance(value, dict):
            try:
                return cls(w=float(value["w"]), x=float(value["x"]), y=float(value["y"]), z=float(value["z"]))
            except (KeyError, TypeError, ValueError):
                return None
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            try:
                return cls(w=float(value[0]), x=float(value[1]), y=float(value[2]), z=float(value[3]))
            except (TypeError, ValueError):
                return None
        return None

    def as_payload(self) -> dict[str, float]:
        """Return a JSON-friendly quaternion."""

        return {
            "w": round(self.w, 5),
            "x": round(self.x, 5),
            "y": round(self.y, 5),
            "z": round(self.z, 5),
        }


@dataclass(frozen=True)
class ESP32Telemetry:
    """One future ESP32-S3 IMU sample received over newline-delimited JSON.

    Preferred firmware-side shape for the BNO08X prototype:

    ``{"device_id":"esp32_0","timestamp_ms":12345,
    "mount":"right_gym_glove",
    "orientation_euler_deg":{"pitch":4.1,"roll":-2.0,"yaw":91.5},
    "quaternion":{"w":0.99,"x":0.01,"y":0.02,"z":0.03},
    "accel_mps2":{"x":0,"y":0,"z":9.81},
    "gyro_dps":{"x":0,"y":0,"z":0}}``

    The parser also accepts shorter aliases such as ``accel``/``gyro`` so early
    experiments can evolve without breaking the Python pipeline contract.
    """

    device_id: str = "esp32_0"
    timestamp_ms: int | None = None
    received_at: float = field(default_factory=time)
    mount: str | None = None
    orientation_euler_deg: dict[str, float | None] | None = None
    quaternion: Quaternion | None = None
    accel_mps2: Vector3 | None = None
    gyro_dps: Vector3 | None = None
    magnetometer_ut: Vector3 | None = None
    sample_interval_ms: float | None = None
    motion_delta_mps2: float | None = None
    angular_delta_dps: float | None = None
    orientation_delta_deg: float | None = None
    stability_index: float | None = None
    temperature_c: float | None = None
    battery_v: float | None = None
    sequence: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw_payload: Any, received_at: float | None = None) -> "ESP32Telemetry | None":
        """Parse a telemetry dataclass from one raw JSON object."""

        if not isinstance(raw_payload, dict):
            return None

        timestamp_value = raw_payload.get("timestamp_ms", raw_payload.get("t_ms"))
        sequence_value = raw_payload.get("sequence", raw_payload.get("seq"))
        temperature_value = raw_payload.get("temperature_c", raw_payload.get("temp_c"))
        battery_value = raw_payload.get("battery_v", raw_payload.get("battery"))
        try:
            timestamp_ms = None if timestamp_value is None else int(timestamp_value)
        except (TypeError, ValueError):
            timestamp_ms = None
        try:
            sequence = None if sequence_value is None else int(sequence_value)
        except (TypeError, ValueError):
            sequence = None

        orientation = _orientation_euler_from_raw(raw_payload)
        quaternion = Quaternion.from_raw(
            raw_payload.get("quaternion", raw_payload.get("rotation_vector", raw_payload.get("quat")))
        )
        return cls(
            device_id=str(raw_payload.get("device_id", raw_payload.get("id", "esp32_0"))),
            timestamp_ms=timestamp_ms,
            received_at=float(received_at if received_at is not None else time()),
            mount=raw_payload.get("mount", raw_payload.get("placement", raw_payload.get("side"))),
            orientation_euler_deg=orientation,
            quaternion=quaternion,
            accel_mps2=Vector3.from_raw(
                raw_payload.get("accel_mps2", raw_payload.get("acceleration", raw_payload.get("accel")))
            ),
            gyro_dps=Vector3.from_raw(raw_payload.get("gyro_dps", raw_payload.get("gyroscope", raw_payload.get("gyro")))),
            magnetometer_ut=Vector3.from_raw(
                raw_payload.get("magnetometer_ut", raw_payload.get("magnetometer", raw_payload.get("mag")))
            ),
            temperature_c=_optional_float(temperature_value),
            battery_v=_optional_float(battery_value),
            sequence=sequence,
            raw=dict(raw_payload),
        )

    def with_motion_quality(self, previous: "ESP32Telemetry | None") -> "ESP32Telemetry":
        """Attach frame-to-frame IMU signal features.

        The first real firmware can stream raw acceleration/gyro/orientation.
        This bridge derives lightweight stability features from consecutive
        samples without blocking the camera thread or requiring a full
        signal-processing stack yet.
        """

        if previous is None:
            return self

        motion_delta = _vector_delta(self.accel_mps2, previous.accel_mps2)
        angular_delta = _vector_delta(self.gyro_dps, previous.gyro_dps)
        orientation_delta = _orientation_delta(self.orientation_euler_deg, previous.orientation_euler_deg)
        return replace(
            self,
            sample_interval_ms=_sample_interval_ms(self, previous),
            motion_delta_mps2=motion_delta,
            angular_delta_dps=angular_delta,
            orientation_delta_deg=orientation_delta,
            stability_index=_stability_index(motion_delta),
        )

    def as_payload(self) -> dict[str, Any]:
        """Return the stable ESP32 JSON payload section."""

        payload: dict[str, Any] = {
            "device_id": self.device_id,
            "timestamp_ms": self.timestamp_ms,
            "received_at": round(self.received_at, 3),
            "mount": self.mount,
            "orientation_euler_deg": self.orientation_euler_deg,
            "quaternion": None if self.quaternion is None else self.quaternion.as_payload(),
            "accel_mps2": None if self.accel_mps2 is None else self.accel_mps2.as_payload(),
            "gyro_dps": None if self.gyro_dps is None else self.gyro_dps.as_payload(),
            "magnetometer_ut": None if self.magnetometer_ut is None else self.magnetometer_ut.as_payload(),
            "sample_interval_ms": self.sample_interval_ms,
            "motion_delta_mps2": None if self.motion_delta_mps2 is None else round(self.motion_delta_mps2, 5),
            "angular_delta_dps": None if self.angular_delta_dps is None else round(self.angular_delta_dps, 5),
            "orientation_delta_deg": None
            if self.orientation_delta_deg is None
            else round(self.orientation_delta_deg, 5),
            "stability_index": None if self.stability_index is None else round(self.stability_index, 5),
            "temperature_c": self.temperature_c,
            "battery_v": self.battery_v,
            "sequence": self.sequence,
        }
        compact_raw = {key: value for key, value in self.raw.items() if key not in payload}
        if compact_raw:
            payload["raw"] = compact_raw
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class ESP32Payload:
    """Top-level ESP32 payload consumed by the detector and game layer."""

    status: str
    devices: dict[str, ESP32Telemetry] = field(default_factory=dict)
    latest: ESP32Telemetry | None = None
    port: str | None = None
    baud: int | None = None
    note: str | None = None
    error: str | None = None
    available_ports: list[dict[str, Any]] | None = None
    lines_read: int | None = None
    backlog_bytes: int | None = None
    parsed_messages: int | None = None
    non_json_lines: int | None = None
    transport: str | None = None
    host: str | None = None
    udp_port: int | None = None
    remote: str | None = None
    sample_age_seconds: float | None = None

    def as_payload(self) -> dict[str, Any]:
        """Return the existing dictionary shape expected upstream."""

        payload: dict[str, Any] = {
            "status": self.status,
            "devices": {device_id: sample.as_payload() for device_id, sample in self.devices.items()},
            "latest": None if self.latest is None else self.latest.as_payload(),
        }
        if self.port is not None:
            payload["port"] = self.port
        if self.baud is not None:
            payload["baud"] = self.baud
        if self.note is not None:
            payload["note"] = self.note
        if self.error is not None:
            payload["error"] = self.error
        if self.available_ports is not None:
            payload["available_ports"] = self.available_ports
        if self.lines_read is not None:
            payload["lines_read"] = self.lines_read
        if self.backlog_bytes is not None:
            payload["backlog_bytes"] = self.backlog_bytes
        if self.parsed_messages is not None:
            payload["parsed_messages"] = self.parsed_messages
        if self.non_json_lines is not None:
            payload["non_json_lines"] = self.non_json_lines
        if self.transport is not None:
            payload["transport"] = self.transport
        if self.host is not None:
            payload["host"] = self.host
        if self.udp_port is not None:
            payload["udp_port"] = self.udp_port
        if self.remote is not None:
            payload["remote"] = self.remote
        if self.sample_age_seconds is not None:
            payload["sample_age_seconds"] = round(max(0.0, self.sample_age_seconds), 3)
        return payload


@dataclass(frozen=True)
class WearablePayload:
    """Normalized Garmin Venu 3 / BLE heart-rate sample."""

    status: str = "not_configured"
    device: str | None = "garmin_venu_3"
    device_name: str | None = None
    device_address: str | None = None
    provider: str | None = "garmin"
    sample_type: str | None = "ble_heart_rate"
    heart_rate_bpm: float | int | None = None
    heart_rate_confidence: str | float | int | None = None
    heart_rate_contact: str | None = None
    resting_heart_rate_bpm: float | int | None = None
    max_heart_rate_bpm: float | int | None = None
    rr_intervals_ms: list[float] | None = None
    energy_expended_kj: float | int | None = None
    stress: float | int | str | None = None
    body_battery: float | int | str | None = None
    respiration_rate: float | int | str | None = None
    pulse_ox: float | int | str | None = None
    steps: float | int | str | None = None
    calories: float | int | str | None = None
    hrv_ms: float | int | str | None = None
    activity_state: str | None = None
    timestamp: str | float | int | None = None
    source: str | None = None
    ingest_source: str | None = None
    received_at: float | None = None
    battery: float | int | str | None = None
    battery_unit: str | None = None
    path: str | None = None
    age_seconds: float | None = None
    acceleration: Vector3 | Any | None = None
    acceleration_unit: str | None = None
    acceleration_magnitude_mg: float | int | str | None = None
    watch_motion_delta_mg: float | int | str | None = None
    watch_motion_state: str | None = None
    gyroscope: Vector3 | Any | None = None
    gyroscope_unit: str | None = None
    location: dict[str, Any] | None = None
    latitude: float | int | str | None = None
    longitude: float | int | str | None = None
    altitude_m: float | int | str | None = None
    speed_mps: float | int | str | None = None
    distance_m: float | int | str | None = None
    heading_deg: float | int | str | None = None
    sequence: int | str | None = None
    sent_count: int | str | None = None
    sample_interval_ms: float | int | str | None = None
    endpoint_mode: str | None = None
    last_http_code: int | str | None = None
    note: str | None = None
    error: str | None = None
    latest: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        """Return a JSON-friendly wearable payload."""

        payload: dict[str, Any] = {
            "status": self.status,
            "device": self.device,
            "device_name": self.device_name,
            "device_address": self.device_address,
            "provider": self.provider,
            "sample_type": self.sample_type,
            "heart_rate_bpm": self.heart_rate_bpm,
            "heart_rate_confidence": self.heart_rate_confidence,
            "heart_rate_contact": self.heart_rate_contact,
            "resting_heart_rate_bpm": self.resting_heart_rate_bpm,
            "max_heart_rate_bpm": self.max_heart_rate_bpm,
            "rr_intervals_ms": self.rr_intervals_ms,
            "energy_expended_kj": self.energy_expended_kj,
            "stress": self.stress,
            "body_battery": self.body_battery,
            "respiration_rate": self.respiration_rate,
            "pulse_ox": self.pulse_ox,
            "steps": self.steps,
            "calories": self.calories,
            "hrv_ms": self.hrv_ms,
            "activity_state": self.activity_state,
            "timestamp": self.timestamp,
        }
        optional_values = {
            "source": self.source,
            "ingest_source": self.ingest_source,
            "received_at": None if self.received_at is None else round(self.received_at, 3),
            "battery": self.battery,
            "battery_unit": self.battery_unit,
            "path": self.path,
            "age_seconds": self.age_seconds,
            "acceleration": _vector_or_raw(self.acceleration),
            "acceleration_unit": self.acceleration_unit,
            "acceleration_magnitude_mg": self.acceleration_magnitude_mg,
            "watch_motion_delta_mg": self.watch_motion_delta_mg,
            "watch_motion_state": self.watch_motion_state,
            "gyroscope": _vector_or_raw(self.gyroscope),
            "gyroscope_unit": self.gyroscope_unit,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m,
            "speed_mps": self.speed_mps,
            "distance_m": self.distance_m,
            "heading_deg": self.heading_deg,
            "sequence": self.sequence,
            "sent_count": self.sent_count,
            "sample_interval_ms": self.sample_interval_ms,
            "endpoint_mode": self.endpoint_mode,
            "last_http_code": self.last_http_code,
            "note": self.note,
            "error": self.error,
            "latest": self.latest,
        }
        payload.update({key: value for key, value in optional_values.items() if value is not None})
        return payload


def build_empty_esp32_payload() -> dict[str, Any]:
    """Return the default payload used when no ESP32 is configured."""

    return ESP32Payload(
        status="not_configured",
        note="Use run_ironquest.bat for the normal camera + ESP32/IMU startup.",
    ).as_payload()


def build_empty_wearable_payload() -> dict[str, Any]:
    """Return the default payload used when no smartwatch is configured."""

    return WearablePayload(
        note="Reserved for Garmin Venu 3 heart-rate data via BLE, Garmin SDK, or a bridge JSON file.",
    ).as_payload()


def normalise_wearable_payload(raw_payload: Any, source: str = "file") -> dict[str, Any]:
    """Convert external wearable data into the project payload shape."""

    if isinstance(raw_payload, dict) and isinstance(raw_payload.get("wearable"), dict):
        raw_payload = raw_payload["wearable"]
    if isinstance(raw_payload, list):
        raw_payload = next((item for item in reversed(raw_payload) if isinstance(item, dict)), {})
    if not isinstance(raw_payload, dict):
        return WearablePayload(
            status="bad_json",
            source=source,
            error="Wearable JSON must be an object or a list of objects.",
            note="Wearable JSON must be an object, a list of objects, or a nested {'wearable': {...}} payload.",
        ).as_payload()

    physiology = raw_payload.get("physiology") if isinstance(raw_payload.get("physiology"), dict) else {}
    activity = raw_payload.get("activity") if isinstance(raw_payload.get("activity"), dict) else {}
    motion = raw_payload.get("motion") if isinstance(raw_payload.get("motion"), dict) else {}
    location_raw = _first_present(raw_payload, activity, "location", "position", "gps")
    location = _normalise_location(location_raw)
    heart_rate = _first_present(
        raw_payload,
        physiology,
        "heart_rate_bpm",
        "heart_rate",
        "hr",
        "bpm",
        "beats_per_minute",
    )
    resting_heart_rate = _first_present(
        raw_payload,
        physiology,
        "resting_heart_rate_bpm",
        "resting_heart_rate",
        "hr_min_bpm",
    )
    max_heart_rate = _first_present(
        raw_payload,
        physiology,
        "max_heart_rate_bpm",
        "max_heart_rate",
        "hr_max_bpm",
    )
    rr_intervals = _first_present(raw_payload, physiology, "rr_intervals_ms", "rr_interval_ms", "rr_intervals")
    activity_state = raw_payload.get(
        "activity_state",
        raw_payload.get("activity_type", activity.get("type", activity.get("state", raw_payload.get("state")))),
    )
    provider = raw_payload.get("provider", physiology.get("provider", "garmin"))
    device = raw_payload.get("device", raw_payload.get("device_name", physiology.get("device", "garmin_venu_3")))
    source_name = raw_payload.get("source", raw_payload.get("data_source", physiology.get("source", source)))
    acceleration = _first_present(
        raw_payload,
        motion,
        "acceleration",
        "accelerometer",
        "accel",
        "acceleration_mg",
        "accel_mg",
    )
    gyroscope = _first_present(raw_payload, motion, "gyroscope", "gyro", "gyro_dps")
    return WearablePayload(
        status=str(raw_payload.get("status", "connected")),
        device=device,
        device_name=raw_payload.get("device_name", physiology.get("device_name")),
        device_address=raw_payload.get("device_address", raw_payload.get("address")),
        provider=provider,
        sample_type=raw_payload.get("sample_type", physiology.get("sample_type", "ble_heart_rate")),
        heart_rate_bpm=_optional_int(heart_rate),
        heart_rate_confidence=raw_payload.get("heart_rate_confidence", physiology.get("heart_rate_confidence")),
        heart_rate_contact=raw_payload.get("heart_rate_contact", physiology.get("heart_rate_contact")),
        resting_heart_rate_bpm=_optional_int(resting_heart_rate),
        max_heart_rate_bpm=_optional_int(max_heart_rate),
        rr_intervals_ms=_optional_float_list(rr_intervals),
        energy_expended_kj=_optional_int(
            raw_payload.get("energy_expended_kj", raw_payload.get("energy_expended"))
        ),
        stress=raw_payload.get("stress", raw_payload.get("body_response", physiology.get("stress"))),
        body_battery=raw_payload.get("body_battery", raw_payload.get("body_battery_level", physiology.get("body_battery"))),
        respiration_rate=raw_payload.get(
            "respiration_rate",
            raw_payload.get("respiration_rate_bpm", physiology.get("respiration_rate")),
        ),
        pulse_ox=raw_payload.get("pulse_ox", raw_payload.get("spo2", physiology.get("pulse_ox"))),
        steps=raw_payload.get("steps", physiology.get("steps")),
        calories=raw_payload.get("calories", raw_payload.get("active_calories", physiology.get("calories"))),
        hrv_ms=raw_payload.get("hrv_ms", raw_payload.get("heart_rate_variability_ms", physiology.get("hrv_ms"))),
        activity_state=None if activity_state is None else str(activity_state),
        timestamp=raw_payload.get("timestamp", raw_payload.get("time", physiology.get("timestamp"))),
        source=source_name,
        ingest_source=source,
        received_at=time(),
        battery=raw_payload.get("battery"),
        battery_unit=raw_payload.get("battery_unit"),
        acceleration=_vector_from_raw_or_latest(acceleration),
        acceleration_unit=raw_payload.get("acceleration_unit", motion.get("acceleration_unit")),
        acceleration_magnitude_mg=raw_payload.get(
            "acceleration_magnitude_mg",
            motion.get("acceleration_magnitude_mg", motion.get("accel_magnitude_mg")),
        ),
        watch_motion_delta_mg=raw_payload.get(
            "watch_motion_delta_mg",
            motion.get("watch_motion_delta_mg", motion.get("motion_delta_mg")),
        ),
        watch_motion_state=raw_payload.get(
            "watch_motion_state",
            motion.get("watch_motion_state", motion.get("motion_state")),
        ),
        gyroscope=_vector_from_raw_or_latest(gyroscope),
        gyroscope_unit=raw_payload.get("gyroscope_unit", motion.get("gyroscope_unit")),
        location=location,
        latitude=_first_present(raw_payload, location or {}, "latitude", "lat"),
        longitude=_first_present(raw_payload, location or {}, "longitude", "lon", "lng"),
        altitude_m=_first_present(raw_payload, location or {}, "altitude_m", "altitude"),
        speed_mps=_first_present(raw_payload, activity, location or {}, "speed_mps", "speed"),
        distance_m=_first_present(raw_payload, activity, "distance_m", "distance"),
        heading_deg=_first_present(raw_payload, location or {}, "heading_deg", "heading"),
        sequence=_optional_int(raw_payload.get("sequence", raw_payload.get("seq"))),
        sent_count=_optional_int(raw_payload.get("sent_count")),
        sample_interval_ms=_optional_float(raw_payload.get("sample_interval_ms")),
        endpoint_mode=raw_payload.get("endpoint_mode"),
        last_http_code=_optional_int(raw_payload.get("last_http_code")),
    ).as_payload()


class WearableFileBridge:
    """Read the latest smartwatch/wristband sample from a JSON file.

    File-system reads are throttled. OpenCV may render at 30+ FPS, but wearable
    files usually update slowly, so checking the file at most twice per second
    avoids a needless per-frame ``stat`` and read path.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        stale_seconds: float = 10.0,
        max_reads_per_second: float = 2.0,
    ):
        """Store the JSON file path, stale age, and polling throttle."""

        self.path = Path(path) if path else None
        self.stale_seconds = max(float(stale_seconds), 0.0)
        self.min_poll_interval = 1.0 / max(float(max_reads_per_second), 0.1)
        self.last_payload: dict[str, Any] | None = None
        self._last_read_attempt = 0.0

    def poll(self) -> dict[str, Any]:
        """Read and normalize one wearable JSON file without blocking."""

        if self.path is None:
            return build_empty_wearable_payload()

        now = time()
        if self.last_payload is not None and now - self._last_read_attempt < self.min_poll_interval:
            return self.last_payload
        self._last_read_attempt = now

        if not self.path.exists():
            self.last_payload = WearablePayload(
                status="missing_file",
                source="file",
                path=str(self.path),
                note="Create this JSON file from a smartwatch export or bridge script.",
            ).as_payload()
            return self.last_payload

        try:
            stat = self.path.stat()
            raw_payload = json.loads(self.path.read_text(encoding="utf-8"))
            payload = normalise_wearable_payload(raw_payload, source="file")
            age_seconds = max(0.0, now - stat.st_mtime)
            payload["path"] = str(self.path)
            payload["age_seconds"] = round(age_seconds, 2)
            if self.stale_seconds and age_seconds > self.stale_seconds:
                payload["status"] = "stale"
            self.last_payload = payload
            return payload
        except json.JSONDecodeError as exc:
            return WearablePayload(
                status="bad_json",
                source="file",
                path=str(self.path),
                error=str(exc),
                latest=self.last_payload,
            ).as_payload()
        except Exception as exc:  # pragma: no cover - depends on local files and permissions
            return WearablePayload(
                status="read_failed",
                source="file",
                path=str(self.path),
                error=str(exc),
                latest=self.last_payload,
            ).as_payload()


class ESP32SerialBridge:
    """Read newline-delimited ESP32 telemetry JSON over USB serial.

    Includes hot-plugging support: it will automatically attempt to reconnect
    every 2 seconds if the device is unplugged and plugged back in.
    """

    def __init__(
        self,
        port: str | None = None,
        baud: int = 115200,
        max_lines_per_poll: int = 32,
        serial_startup_delay: float = 2.0,
        stale_seconds: float = ESP32_DEFAULT_STALE_SECONDS,
    ):
        """Store serial settings and open the port when one is configured."""

        self.enabled = port is not None
        self.auto_detect = str(port).lower() == "auto" if port is not None else False
        self.port_config = port
        self.port: str | None = None
        self.available_ports: list[dict[str, Any]] = []
        self.baud = baud
        self.serial = None
        self.last_sample: ESP32Telemetry | None = None
        self.error: str | None = None
        self.max_lines_per_poll = max(1, int(max_lines_per_poll))
        self.serial_startup_delay = max(0.0, float(serial_startup_delay))
        self.stale_seconds = max(0.1, float(stale_seconds))
        self.parsed_messages = 0
        self.non_json_lines = 0
        self.last_reconnect_attempt = 0.0
        self.reconnect_cooldown = 2.0
        if self.enabled:
            self._try_connect(force=True)

    def _try_connect(self, force: bool = False) -> None:
        """Attempt to open the serial port silently to avoid frame drops."""

        if not self.enabled:
            return
        now = time()
        if not force and now - self.last_reconnect_attempt < self.reconnect_cooldown:
            return
        self.last_reconnect_attempt = now

        self.available_ports = list_serial_ports() if self.auto_detect else []
        self.port = find_esp32_port(self.available_ports) if self.auto_detect else self.port_config

        if not self.port:
            self.error = "no_serial_port_found"
            return

        try:
            import serial  # type: ignore
        except ImportError:
            self.error = "pyserial_missing"
            return

        try:
            self.serial = serial.Serial(self.port, self.baud, timeout=0.01)
            try:
                self.serial.setDTR(False)
                self.serial.setRTS(False)
            except Exception:
                pass
            if self.serial_startup_delay:
                sleep(self.serial_startup_delay)
            try:
                self.serial.reset_input_buffer()
            except Exception:
                pass
            self.error = None
        except Exception as exc:  # pragma: no cover - depends on external hardware
            self.error = f"serial_open_failed: {exc}"
            self.serial = None

    def poll(self) -> dict[str, Any]:
        """Read the newest available ESP32 telemetry message without blocking."""

        if not self.enabled:
            return build_empty_esp32_payload()

        if self.serial is None:
            self._try_connect()
            if self.serial is None:
                return ESP32Payload(
                    status=self.error or "no_serial_port_found",
                    latest=self.last_sample,
                    sample_age_seconds=_sample_age_seconds(self.last_sample),
                    port=self.port,
                    baud=self.baud,
                    available_ports=self.available_ports if self.auto_detect else None,
                ).as_payload()

        latest = self.last_sample
        non_json_line: str | None = None
        lines_read = 0
        backlog_bytes: int | None = None

        try:
            while self.serial.in_waiting and lines_read < self.max_lines_per_poll:
                line = self.serial.readline().decode("utf-8", errors="replace").strip()
                lines_read += 1
                if not line:
                    continue
                try:
                    raw_message = json.loads(line)
                except json.JSONDecodeError:
                    non_json_line = line[:120]
                    self.non_json_lines += 1
                    continue
                parsed = ESP32Telemetry.from_raw(raw_message, received_at=time())
                if parsed is not None:
                    parsed = parsed.with_motion_quality(latest)
                    latest = parsed
                    self.parsed_messages += 1
            try:
                backlog_bytes = int(self.serial.in_waiting)
            except Exception:
                backlog_bytes = None
        except Exception as exc:  # pragma: no cover - depends on external hardware
            self.close()
            return ESP32Payload(
                status="serial_disconnected",
                latest=latest,
                sample_age_seconds=_sample_age_seconds(latest),
                port=self.port,
                baud=self.baud,
                error=str(exc),
                available_ports=self.available_ports if self.auto_detect else None,
                lines_read=lines_read,
                backlog_bytes=backlog_bytes,
                parsed_messages=self.parsed_messages,
                non_json_lines=self.non_json_lines,
            ).as_payload()

        self.last_sample = latest
        devices = {latest.device_id: latest} if latest is not None else {}
        sample_age = _sample_age_seconds(latest)
        is_fresh = sample_age is not None and sample_age <= self.stale_seconds
        status = "connected" if is_fresh else ("stale" if latest is not None else "connected_waiting_for_data")
        note = None

        if status == "stale":
            note = "ESP32 stopped sending telemetry; waiting for serial reconnection."

        if latest is None and non_json_line is not None:
            status = "connected_non_json_data"
            note = "Serial port is open, but the ESP32 is not streaming telemetry JSON yet."

        return ESP32Payload(
            status=status,
            devices=devices,
            latest=latest,
            port=self.port,
            baud=self.baud,
            note=note,
            error=None if latest is not None else non_json_line,
            available_ports=self.available_ports if self.auto_detect else None,
            lines_read=lines_read,
            backlog_bytes=backlog_bytes,
            parsed_messages=self.parsed_messages,
            non_json_lines=self.non_json_lines,
            sample_age_seconds=sample_age,
        ).as_payload()

    def close(self) -> None:
        """Close the serial port safely."""

        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None


class ESP32UdpBridge:
    """Receive ESP32 telemetry JSON over Wi-Fi UDP datagrams.

    This is the next hardware step after USB serial. The ESP32 can send the
    same JSON payload over the local network while the Python runtime listens
    without blocking the camera loop.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        udp_port: int = 4210,
        discovery_port: int = 4211,
        discovery_interval_seconds: float = 2.0,
        max_packets_per_poll: int = 32,
        stale_seconds: float = ESP32_DEFAULT_STALE_SECONDS,
    ):
        """Bind a non-blocking UDP socket for ESP32 JSON telemetry."""

        self.host = host
        self.udp_port = int(udp_port)
        self.discovery_port = int(discovery_port)
        self.discovery_interval_seconds = max(0.5, float(discovery_interval_seconds))
        self.max_packets_per_poll = max(1, int(max_packets_per_poll))
        self.stale_seconds = max(0.1, float(stale_seconds))
        self.socket: socket.socket | None = None
        self.last_sample: ESP32Telemetry | None = None
        self.last_remote: str | None = None
        self.error: str | None = None
        self.parsed_messages = 0
        self.non_json_lines = 0
        self.last_discovery_sent = 0.0
        self.last_reconnect_attempt = 0.0
        self.reconnect_cooldown = 2.0
        self._open_socket()

    def _open_socket(self) -> None:
        """Open the UDP socket used by the Python receiver."""

        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_socket.bind((self.host, self.udp_port))
            udp_socket.setblocking(False)
            self.socket = udp_socket
            self.error = None
        except OSError as exc:
            self.socket = None
            self.error = f"udp_bind_failed: {exc}"

    def poll(self) -> dict[str, Any]:
        """Read all currently buffered UDP packets without blocking."""

        if self.socket is None:
            now = time()
            if now - self.last_reconnect_attempt >= self.reconnect_cooldown:
                self.last_reconnect_attempt = now
                self._open_socket()
        if self.socket is None:
            return ESP32Payload(
                status=self.error or "udp_bind_failed",
                latest=self.last_sample,
                sample_age_seconds=_sample_age_seconds(self.last_sample),
                transport="udp",
                host=self.host,
                udp_port=self.udp_port,
                note=f"UDP discovery is sent to broadcast port {self.discovery_port}.",
                remote=self.last_remote,
                parsed_messages=self.parsed_messages,
                non_json_lines=self.non_json_lines,
            ).as_payload()

        latest = self.last_sample
        packets_read = 0
        non_json_line: str | None = None

        while packets_read < self.max_packets_per_poll:
            try:
                packet, remote = self.socket.recvfrom(4096)
            except BlockingIOError:
                break
            except OSError as exc:
                self.error = f"udp_read_failed: {exc}"
                break

            packets_read += 1
            self.last_remote = f"{remote[0]}:{remote[1]}"
            for line in packet.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_message = json.loads(line)
                except json.JSONDecodeError:
                    non_json_line = line[:120]
                    self.non_json_lines += 1
                    continue
                parsed = ESP32Telemetry.from_raw(raw_message, received_at=time())
                if parsed is not None:
                    parsed = parsed.with_motion_quality(latest)
                    latest = parsed
                    self.parsed_messages += 1

        if packets_read == 0:
            self._maybe_send_discovery()

        self.last_sample = latest
        devices = {latest.device_id: latest} if latest is not None else {}
        sample_age = _sample_age_seconds(latest)
        is_fresh = sample_age is not None and sample_age <= self.stale_seconds
        status = "connected" if is_fresh else ("stale" if latest is not None else "listening_waiting_for_data")
        note = None
        if status == "stale":
            note = "ESP32 stopped sending telemetry; waiting for Wi-Fi reconnection."
        if latest is None and non_json_line is not None:
            status = "listening_non_json_data"
            note = "UDP socket is open, but the ESP32 is not sending telemetry JSON yet."

        return ESP32Payload(
            status=status,
            devices=devices,
            latest=latest,
            note=note,
            error=self.error if self.error else (None if latest is not None else non_json_line),
            lines_read=packets_read,
            parsed_messages=self.parsed_messages,
            non_json_lines=self.non_json_lines,
            transport="udp",
            host=self.host,
            udp_port=self.udp_port,
            remote=self.last_remote,
            sample_age_seconds=sample_age,
        ).as_payload()

    def _maybe_send_discovery(self) -> None:
        """Broadcast this listener's port so the ESP32 can learn the laptop IP."""

        if self.socket is None:
            return
        now = time()
        if now - self.last_discovery_sent < self.discovery_interval_seconds:
            return
        self.last_discovery_sent = now
        message = f"ironquest_discover:{self.udp_port}\n".encode("ascii")
        try:
            self.socket.sendto(message, ("255.255.255.255", self.discovery_port))
        except OSError as exc:
            self.error = f"udp_discovery_failed: {exc}"

    def close(self) -> None:
        """Close the UDP listener."""

        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None


class ESP32AutoBridge:
    """Read ESP32 telemetry from USB serial and Wi-Fi UDP at the same time."""

    def __init__(
        self,
        serial_port: str | None = "auto",
        baud: int = 115200,
        udp_host: str = "0.0.0.0",
        udp_port: int = 4210,
        stale_seconds: float = ESP32_DEFAULT_STALE_SECONDS,
    ):
        """Open both available transports so the UI can use whichever works."""

        self.serial_bridge = ESP32SerialBridge(
            serial_port,
            baud,
            serial_startup_delay=0.25,
            stale_seconds=stale_seconds,
        )
        self.udp_bridge = ESP32UdpBridge(udp_host, udp_port, stale_seconds=stale_seconds)
        self.last_payload: dict[str, Any] | None = None

    def poll(self) -> dict[str, Any]:
        """Return the freshest ESP32 sample from serial or UDP."""

        serial_payload = self.serial_bridge.poll()
        udp_payload = self.udp_bridge.poll()
        candidates: list[tuple[float, str, dict[str, Any]]] = []

        for transport, payload in (("serial", serial_payload), ("udp", udp_payload)):
            latest = payload.get("latest") if isinstance(payload, dict) else None
            if not isinstance(latest, dict):
                continue
            if payload.get("status") != "connected":
                continue
            candidates.append((float(latest.get("received_at", 0.0) or 0.0), transport, payload))

        if candidates:
            _, active_transport, active_payload = max(candidates, key=lambda item: item[0])
            payload = dict(active_payload)
            sources = {
                "serial": self._source_summary(serial_payload),
                "udp": self._source_summary(udp_payload),
            }
            payload["transport"] = f"auto:{active_transport}"
            payload["auto_transport"] = active_transport
            payload["sources"] = sources
            payload["connected_transports"] = self._connected_transports(sources)
            payload["transport_summary"] = self._transport_summary(payload["connected_transports"])
            self.last_payload = payload
            return payload

        sources = {
            "serial": self._source_summary(serial_payload),
            "udp": self._source_summary(udp_payload),
        }
        stale_sources = [
            source for source in sources.values() if source.get("status") == "stale"
        ]
        status = "stale" if stale_sources else "listening_waiting_for_data"
        note = (
            "ESP32 stopped sending telemetry; waiting for USB/Wi-Fi reconnection."
            if stale_sources
            else "Waiting for ESP32 telemetry over USB serial or Wi-Fi UDP."
        )
        sample_ages = [
            float(source["sample_age_seconds"])
            for source in sources.values()
            if source.get("sample_age_seconds") is not None
        ]
        payload = ESP32Payload(
            status=status,
            latest=None,
            note=note,
            transport="auto",
            host=udp_payload.get("host"),
            udp_port=udp_payload.get("udp_port"),
            remote=udp_payload.get("remote"),
            available_ports=serial_payload.get("available_ports"),
            parsed_messages=(serial_payload.get("parsed_messages") or 0) + (udp_payload.get("parsed_messages") or 0),
            non_json_lines=(serial_payload.get("non_json_lines") or 0) + (udp_payload.get("non_json_lines") or 0),
            sample_age_seconds=min(sample_ages) if sample_ages else None,
        ).as_payload()
        payload["sources"] = sources
        payload["connected_transports"] = self._connected_transports(sources)
        payload["transport_summary"] = self._transport_summary(payload["connected_transports"])
        if self.last_payload is not None:
            payload["last_connected"] = {
                "transport": self.last_payload.get("auto_transport"),
                "latest": self.last_payload.get("latest"),
            }
        return payload

    @staticmethod
    def _source_summary(payload: dict[str, Any]) -> dict[str, Any]:
        """Return compact transport state for the debug payload."""

        keys = (
            "status",
            "transport",
            "port",
            "baud",
            "host",
            "udp_port",
            "remote",
            "error",
            "note",
            "parsed_messages",
            "non_json_lines",
            "lines_read",
            "sample_age_seconds",
        )
        return {key: payload[key] for key in keys if key in payload}

    @staticmethod
    def _connected_transports(sources: dict[str, dict[str, Any]]) -> list[str]:
        """Return stable human-facing transport names that are receiving data."""

        connected: list[str] = []
        serial = sources.get("serial", {})
        udp = sources.get("udp", {})
        if serial.get("status") == "connected" and int(serial.get("parsed_messages") or 0) > 0:
            connected.append("usb")
        if udp.get("status") == "connected" and int(udp.get("parsed_messages") or 0) > 0:
            connected.append("wifi")
        return connected

    @staticmethod
    def _transport_summary(connected_transports: list[str]) -> str:
        """Return a compact label for UI/debug display."""

        if connected_transports == ["usb"]:
            return "USB"
        if connected_transports == ["wifi"]:
            return "WIFI"
        if "usb" in connected_transports and "wifi" in connected_transports:
            return "USB+WIFI"
        return "WAIT"

    def close(self) -> None:
        """Close both transport bridges."""

        self.serial_bridge.close()
        self.udp_bridge.close()


def list_serial_ports() -> list[dict[str, Any]]:
    """Return serial ports visible to pyserial without opening them."""

    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return []

    ports: list[dict[str, Any]] = []
    for port in list_ports.comports():
        text = " ".join(
            str(value).lower()
            for value in (port.device, port.description, port.hwid, getattr(port, "manufacturer", ""))
            if value
        )
        ports.append(
            {
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
                "manufacturer": getattr(port, "manufacturer", None),
                "likely_esp32": any(hint in text for hint in ESP32_PORT_HINTS),
            }
        )
    return ports


def find_esp32_port(ports: list[dict[str, Any]] | None = None) -> str | None:
    """Choose the most likely ESP32 serial port from visible hardware."""

    available = ports if ports is not None else list_serial_ports()
    for port in available:
        if port.get("likely_esp32") and port.get("device"):
            return str(port["device"])
    if len(available) == 1 and available[0].get("device"):
        return str(available[0]["device"])
    return None


def _orientation_euler_from_raw(raw_payload: dict[str, Any]) -> dict[str, float | None] | None:
    """Parse pitch/roll/yaw values from nested or flat IMU payloads."""

    raw_orientation = raw_payload.get(
        "orientation_euler_deg",
        raw_payload.get("euler_deg", raw_payload.get("orientation")),
    )
    if isinstance(raw_orientation, dict):
        values = {
            "pitch": _optional_float(raw_orientation.get("pitch")),
            "roll": _optional_float(raw_orientation.get("roll")),
            "yaw": _optional_float(raw_orientation.get("yaw")),
        }
        return values if any(value is not None for value in values.values()) else None

    values = {
        "pitch": _optional_float(raw_payload.get("pitch", raw_payload.get("pitch_deg"))),
        "roll": _optional_float(raw_payload.get("roll", raw_payload.get("roll_deg"))),
        "yaw": _optional_float(raw_payload.get("yaw", raw_payload.get("yaw_deg"))),
    }
    return values if any(value is not None for value in values.values()) else None


def _sample_interval_ms(current: ESP32Telemetry, previous: ESP32Telemetry) -> float:
    """Prefer firmware timestamps over host read timing for buffered serial data."""

    if current.timestamp_ms is not None and previous.timestamp_ms is not None:
        delta_ms = current.timestamp_ms - previous.timestamp_ms
        if delta_ms > 0:
            return round(float(delta_ms), 3)
    return round(max(float(current.received_at - previous.received_at), 1e-6) * 1000.0, 3)


def _vector_delta(current: Vector3 | None, previous: Vector3 | None) -> float | None:
    """Return Euclidean delta between two sensor vectors."""

    if current is None or previous is None:
        return None
    return math.sqrt(
        (current.x - previous.x) ** 2
        + (current.y - previous.y) ** 2
        + (current.z - previous.z) ** 2
    )


def _orientation_delta(
    current: dict[str, float | None] | None,
    previous: dict[str, float | None] | None,
) -> float | None:
    """Return simple pitch/roll/yaw Euclidean delta in degrees."""

    if not isinstance(current, dict) or not isinstance(previous, dict):
        return None
    deltas: list[float] = []
    for key in ("pitch", "roll", "yaw"):
        first = _optional_float(current.get(key))
        second = _optional_float(previous.get(key))
        if first is not None and second is not None:
            deltas.append(first - second)
    if not deltas:
        return None
    return math.sqrt(sum(delta * delta for delta in deltas))


def _stability_index(motion_delta: float | None) -> float | None:
    """Map acceleration change into a neutral 1.0-stable to 0.0-unstable signal."""

    if motion_delta is None:
        return None
    return max(0.0, min(1.0, 1.0 / (1.0 + max(float(motion_delta), 0.0) * 3.0)))


def _optional_float(value: Any) -> float | None:
    """Convert an optional scalar to float."""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    """Convert an optional scalar to int."""

    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _optional_float_list(value: Any) -> list[float] | None:
    """Convert a scalar/list of optional numbers into a compact float list."""

    if value is None:
        return None
    values = value if isinstance(value, (list, tuple)) else [value]
    parsed = [_optional_float(item) for item in values]
    clean = [round(item, 3) for item in parsed if item is not None]
    return clean or None


def _last_optional_float(value: Any) -> float | None:
    """Return the latest numeric value from a scalar or non-empty series."""

    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            parsed = _optional_float(item)
            if parsed is not None:
                return parsed
        return None
    return _optional_float(value)


def _vector_from_raw_or_latest(value: Any) -> Vector3 | Any | None:
    """Parse a vector, including Connect IQ arrays where the latest sample wins."""

    vector = Vector3.from_raw(value)
    if vector is not None:
        return vector
    if isinstance(value, dict):
        x = _last_optional_float(value.get("x"))
        y = _last_optional_float(value.get("y"))
        z = _last_optional_float(value.get("z"))
        if x is not None and y is not None and z is not None:
            return Vector3(x=x, y=y, z=z)
    return value


def _normalise_location(value: Any) -> dict[str, Any] | None:
    """Return a compact location payload from common Garmin/SDK shapes."""

    if not isinstance(value, dict):
        return None
    payload: dict[str, Any] = {}
    latitude = _optional_float(_first_present(value, "latitude", "lat"))
    longitude = _optional_float(_first_present(value, "longitude", "lon", "lng"))
    if latitude is not None:
        payload["latitude"] = round(latitude, 7)
    if longitude is not None:
        payload["longitude"] = round(longitude, 7)
    for output_key, aliases in {
        "altitude_m": ("altitude_m", "altitude"),
        "speed_mps": ("speed_mps", "speed"),
        "heading_deg": ("heading_deg", "heading"),
        "accuracy_m": ("accuracy_m", "accuracy"),
    }.items():
        parsed = _optional_float(_first_present(value, *aliases))
        if parsed is not None:
            payload[output_key] = round(parsed, 3)
    for output_key, aliases in {
        "quality": ("quality", "gps_quality"),
        "source": ("source", "provider"),
    }.items():
        raw = _first_present(value, *aliases)
        if raw is not None:
            payload[output_key] = str(raw)
    return payload or None


def _first_present(*sources_and_keys: Any) -> Any:
    """Return the first present value from one or more dictionaries.

    Call shape: ``_first_present(dict_a, dict_b, "key1", "key2")``.
    """

    dictionaries = [source for source in sources_and_keys if isinstance(source, dict)]
    keys = [source for source in sources_and_keys if isinstance(source, str)]
    for key in keys:
        for dictionary in dictionaries:
            if key in dictionary and dictionary[key] is not None:
                return dictionary[key]
    return None


def _vector_or_raw(value: Vector3 | Any | None) -> Any:
    """Serialize a vector dataclass while preserving unknown raw values."""

    if isinstance(value, Vector3):
        return value.as_payload()
    return value
