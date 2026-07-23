"""Receive Garmin Connect IQ telemetry and write IronQuest wearable JSON.

The Connect IQ watch app sends small HTTP POST payloads through Garmin Connect
on the phone. This bridge keeps the main IronQuest runtime unchanged by writing
the latest sample to ``runs/validate/wearable_live.json``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically so the live runtime never reads a partial sample."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def parse_request_body(raw_body: bytes, content_type: str) -> dict[str, Any]:
    """Parse JSON or form-encoded Connect IQ request bodies."""

    text = raw_body.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    if "application/json" in content_type.lower():
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"payload": parsed}
    form = parse_qs(text, keep_blank_values=True)
    if "payload" in form and form["payload"]:
        parsed = json.loads(form["payload"][0])
        return parsed if isinstance(parsed, dict) else {"payload": parsed}
    return {key: values[-1] if values else "" for key, values in form.items()}


def normalize_connectiq_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """Convert the watch app payload into the shared wearable contract."""

    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "status": "connected",
        "device": "garmin_venu_3",
        "device_name": raw_payload.get("device_name", "Venu 3"),
        "provider": "garmin",
        "sample_type": raw_payload.get("sample_type", "connect_iq_live"),
        "source": raw_payload.get("source", "connect_iq_watch_app"),
        "timestamp": raw_payload.get("timestamp", now),
        "activity_state": raw_payload.get("activity_state", "connect_iq_live_stream"),
    }
    passthrough_keys = (
        "heart_rate_bpm",
        "heart_rate_contact",
        "heart_rate_confidence",
        "rr_intervals_ms",
        "hrv_ms",
        "battery",
        "stress",
        "body_battery",
        "respiration_rate",
        "pulse_ox",
        "steps",
        "calories",
        "acceleration",
        "acceleration_unit",
        "acceleration_magnitude_mg",
        "watch_motion_delta_mg",
        "watch_motion_state",
        "gyroscope",
        "gyroscope_unit",
        "location",
        "latitude",
        "longitude",
        "altitude_m",
        "speed_mps",
        "distance_m",
        "heading_deg",
        "sequence",
        "sent_count",
        "sample_interval_ms",
        "endpoint_mode",
        "last_http_code",
        "battery_unit",
        "note",
    )
    payload.update({key: raw_payload[key] for key in passthrough_keys if key in raw_payload})
    return {key: value for key, value in payload.items() if value is not None}


class GarminConnectIQHandler(BaseHTTPRequestHandler):
    """HTTP handler that accepts health pings from the Connect IQ app."""

    server: "GarminConnectIQServer"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        """Health check endpoint for phone/browser diagnostics."""

        payload: dict[str, Any] = {
            "status": "ok",
            "message": "IronQuest Garmin Connect IQ bridge is listening.",
            "out_path": str(self.server.out_path),
        }
        if self.server.out_path.exists():
            payload["wearable_json_last_write"] = datetime.fromtimestamp(
                self.server.out_path.stat().st_mtime,
                timezone.utc,
            ).isoformat()
        self._send_json(payload)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        """Accept one Connect IQ sample."""

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_payload = parse_request_body(
                self.rfile.read(length),
                self.headers.get("Content-Type", ""),
            )
            payload = normalize_connectiq_payload(raw_payload)
            write_json_atomic(self.server.out_path, payload)
            if self.server.print_samples:
                print(json.dumps({"status": "updated", "path": str(self.server.out_path), **payload}), flush=True)
            self._send_json({"status": "ok"})
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "error": str(exc)}).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the console focused on telemetry updates."""

        if self.server.verbose:
            super().log_message(format, *args)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GarminConnectIQServer(ThreadingHTTPServer):
    """HTTP server with bridge configuration attached."""

    def __init__(
        self,
        server_address: tuple[str, int],
        out_path: Path,
        print_samples: bool,
        verbose: bool,
    ):
        super().__init__(server_address, GarminConnectIQHandler)
        self.out_path = out_path
        self.print_samples = print_samples
        self.verbose = verbose


def main() -> int:
    parser = argparse.ArgumentParser(description="Receive Garmin Connect IQ telemetry for IronQuest.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--out", type=Path, default=Path("runs/validate/wearable_live.json"))
    parser.add_argument("--print-samples", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    server = GarminConnectIQServer(
        (args.host, args.port),
        out_path=args.out,
        print_samples=args.print_samples,
        verbose=args.verbose,
    )
    print(f"Garmin Connect IQ bridge listening on http://{args.host}:{args.port}/garmin", flush=True)
    print(f"Writing latest sample to {args.out}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Garmin Connect IQ bridge stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
