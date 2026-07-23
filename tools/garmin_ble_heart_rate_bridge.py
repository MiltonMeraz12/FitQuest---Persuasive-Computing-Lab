"""Bridge a Garmin Venu 3 BLE heart-rate broadcast into IronQuest JSON.

The live IronQuest pipeline already reads a Garmin-style ``--wearable-json``
file. This script keeps Bluetooth details outside the camera loop: it subscribes
to the standard BLE Heart Rate Measurement characteristic and continuously
writes the latest sample to ``runs/validate/wearable_live.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


def connectiq_payload_is_fresh(path: Path, stale_seconds: float) -> bool:
    """Return True when the shared wearable file has recent Connect IQ data."""

    if stale_seconds <= 0 or not path.exists():
        return False
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > stale_seconds:
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(payload.get("sample_type", "")).startswith("connect_iq")


def connectiq_payload_exists(path: Path) -> bool:
    """Return True when the current shared wearable file came from Connect IQ."""

    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(payload.get("sample_type", "")).startswith("connect_iq")


def parse_heart_rate_measurement(data: bytes | bytearray) -> dict[str, Any]:
    """Parse a BLE Heart Rate Measurement characteristic payload."""

    if len(data) < 2:
        raise ValueError("Heart-rate measurement payload is too short.")

    flags = data[0]
    index = 1
    uses_uint16_bpm = bool(flags & 0x01)
    if uses_uint16_bpm:
        if len(data) < index + 2:
            raise ValueError("Heart-rate uint16 payload is incomplete.")
        heart_rate_bpm = int.from_bytes(data[index : index + 2], "little")
        index += 2
    else:
        heart_rate_bpm = int(data[index])
        index += 1

    contact_supported = bool(flags & 0x04)
    contact_detected = bool(flags & 0x02) if contact_supported else None
    energy_expended = None
    if flags & 0x08:
        if len(data) >= index + 2:
            energy_expended = int.from_bytes(data[index : index + 2], "little")
            index += 2

    rr_intervals_ms: list[float] = []
    if flags & 0x10:
        while len(data) >= index + 2:
            rr_raw = int.from_bytes(data[index : index + 2], "little")
            rr_intervals_ms.append(round(rr_raw * 1000.0 / 1024.0, 3))
            index += 2

    sample: dict[str, Any] = {
        "heart_rate_bpm": heart_rate_bpm,
        "heart_rate_confidence": "contact_detected"
        if contact_detected is True
        else "contact_not_detected"
        if contact_detected is False
        else "contact_unknown",
    }
    if contact_detected is not None:
        sample["heart_rate_contact"] = "detected" if contact_detected else "not_detected"
    if energy_expended is not None:
        sample["energy_expended_kj"] = energy_expended
    if rr_intervals_ms:
        sample["rr_intervals_ms"] = rr_intervals_ms
    return sample


def build_wearable_sample(
    measurement: dict[str, Any],
    device_name: str | None,
    device_address: str | None,
    resting_bpm: int | None,
    max_bpm: int | None,
    activity_state: str,
    ble_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON shape consumed by IronQuest's WearableFileBridge."""

    ble_metadata = ble_metadata or {}
    payload = {
        "status": "connected",
        "device": "garmin_venu_3",
        "device_name": device_name,
        "device_address": device_address,
        "provider": "garmin",
        "sample_type": "ble_heart_rate",
        "source": "ble_heart_rate_service",
        "activity_state": activity_state,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **ble_metadata,
        **measurement,
    }
    if resting_bpm is not None:
        payload["resting_heart_rate_bpm"] = resting_bpm
    if max_bpm is not None:
        payload["max_heart_rate_bpm"] = max_bpm
    return {key: value for key, value in payload.items() if value is not None}


async def read_optional_ble_metadata(client: Any) -> dict[str, Any]:
    """Read optional standard BLE metadata exposed by the watch."""

    metadata: dict[str, Any] = {}
    try:
        battery_raw = await client.read_gatt_char(BATTERY_LEVEL_UUID)
    except Exception:
        battery_raw = None
    if battery_raw:
        metadata["battery"] = int(battery_raw[0])
    return metadata


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON without leaving a half-written sample for the camera loop."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


async def discover_device(address: str | None, name_filter: str | None, timeout: float):
    """Return the BLE device that should be used for the heart-rate bridge."""

    from bleak import BleakScanner  # type: ignore

    if address:
        devices = await BleakScanner.discover(timeout=timeout)
        for device in devices:
            if str(getattr(device, "address", "")).lower() == address.lower():
                return device
        return address

    name_filter = (name_filter or "venu").lower()
    try:
        discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
        candidates = [item[0] for item in discovered.values()]
    except TypeError:
        candidates = await BleakScanner.discover(timeout=timeout)

    preferred = []
    fallback = []
    for device in candidates:
        name = str(getattr(device, "name", "") or "")
        lowered = name.lower()
        if name_filter and name_filter in lowered:
            preferred.append(device)
        if "garmin" in lowered or "venu" in lowered:
            fallback.append(device)
    if preferred:
        return preferred[0]
    if fallback:
        return fallback[0]
    return None


async def bridge(args: argparse.Namespace) -> int:
    """Run BLE discovery, subscribe to heart-rate updates, and write samples."""

    try:
        from bleak import BleakClient  # type: ignore
    except ImportError:
        print("Missing dependency: install bleak with `pip install bleak` or reinstall requirements.txt.")
        return 2

    started_at = time.time()
    received_any_sample = False

    while True:
        if args.seconds and (time.time() - started_at) >= args.seconds:
            return 0 if received_any_sample else 1

        device = await discover_device(args.address, args.name, args.scan_seconds)
        if device is None:
            if connectiq_payload_exists(args.out):
                print("Connect IQ sample exists; skipping BLE missing-device overwrite.")
                await asyncio.sleep(max(0.5, args.retry_seconds))
                continue
            write_json_atomic(
                args.out,
                {
                    "status": "missing_device",
                    "device": "garmin_venu_3",
                    "provider": "garmin",
                    "sample_type": "ble_heart_rate",
                    "source": "ble_heart_rate_service",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "note": "Enable heart-rate broadcast on the watch and keep it near the laptop.",
                },
            )
            print(f"No Garmin/Venu BLE heart-rate device found during {args.scan_seconds}s scan.")
            await asyncio.sleep(max(0.5, args.retry_seconds))
            continue

        device_name = str(getattr(device, "name", "") or args.name or "Garmin Venu 3")
        device_address = str(getattr(device, "address", "") or args.address or "")
        print(f"Connecting to {device_name} {device_address}".strip())

        received_session_sample = asyncio.Event()
        ble_metadata: dict[str, Any] = {}

        def on_measurement(_sender: Any, data: bytearray) -> None:
            nonlocal received_any_sample
            try:
                if connectiq_payload_is_fresh(args.out, args.connectiq_priority_seconds):
                    return
                measurement = parse_heart_rate_measurement(data)
                payload = build_wearable_sample(
                    measurement,
                    device_name=device_name,
                    device_address=device_address,
                    resting_bpm=args.resting_bpm,
                    max_bpm=args.max_bpm,
                    activity_state=args.activity_state,
                    ble_metadata=ble_metadata,
                )
                write_json_atomic(args.out, payload)
                received_any_sample = True
                received_session_sample.set()
                print(
                    json.dumps(
                        {
                            "status": "updated",
                            "path": str(args.out),
                            "heart_rate_bpm": payload["heart_rate_bpm"],
                            "timestamp": payload["timestamp"],
                        }
                    )
                )
            except Exception as exc:
                print(json.dumps({"status": "parse_failed", "error": str(exc)}))

        try:
            async with BleakClient(device) as client:
                if not client.is_connected:
                    print("BLE connection failed.")
                    await asyncio.sleep(max(0.5, args.retry_seconds))
                    continue
                ble_metadata = await read_optional_ble_metadata(client)
                await client.start_notify(HEART_RATE_MEASUREMENT_UUID, on_measurement)
                try:
                    while True:
                        if args.seconds and (time.time() - started_at) >= args.seconds:
                            return 0 if received_any_sample else 1
                        await asyncio.sleep(0.25)
                finally:
                    await client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
        except Exception as exc:
            print(json.dumps({"status": "bridge_disconnected", "error": str(exc)}))

        if args.seconds and (time.time() - started_at) >= args.seconds:
            return 0 if received_any_sample else 1
        if received_session_sample.is_set():
            print("Garmin BLE bridge disconnected; retrying scan.")
        await asyncio.sleep(max(0.5, args.retry_seconds))


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Garmin Venu 3 BLE heart-rate data to wearable_live.json.")
    parser.add_argument("--out", type=Path, default=Path("runs/validate/wearable_live.json"))
    parser.add_argument("--name", default="Venu", help="BLE device-name filter. Use Garmin or Venu if unsure.")
    parser.add_argument("--address", help="Optional BLE address shown by a scanner.")
    parser.add_argument("--scan-seconds", type=float, default=10.0)
    parser.add_argument("--retry-seconds", type=float, default=5.0)
    parser.add_argument("--seconds", type=float, default=0.0, help="Stop after N seconds. Use 0 to run until Ctrl+C.")
    parser.add_argument("--resting-bpm", type=int, help="Optional personal baseline used for exertion_level.")
    parser.add_argument("--max-bpm", type=int, help="Optional personal peak/reference BPM used for exertion_level.")
    parser.add_argument("--activity-state", default="controlled_dumbbell_movement")
    parser.add_argument(
        "--connectiq-priority-seconds",
        type=float,
        default=4.0,
        help="Do not overwrite fresh Connect IQ samples in the shared wearable JSON.",
    )
    args = parser.parse_args()
    return asyncio.run(bridge(args))


if __name__ == "__main__":
    raise SystemExit(main())
