"""Pull the latest FitQuest Garmin sample into the existing local JSON contract."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def write_json_atomic(path: Path, payload: dict) -> None:
    """Replace the wearable file atomically so the UI never reads partial JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)

    # Keep the local freshness clock aligned with the time the Worker received
    # the Garmin sample, rather than the time the laptop performed the poll.
    received_epoch_ms = payload.get("bridge_received_epoch_ms")
    try:
        received_epoch = float(received_epoch_ms) / 1000.0
    except (TypeError, ValueError):
        received_epoch = None
    if received_epoch is not None and received_epoch > 0:
        try:
            os.utime(path, (received_epoch, received_epoch))
        except OSError:
            pass


def sample_identity(payload: dict) -> tuple[str, str]:
    """Return a stable key for one remote sample."""

    received_epoch_ms = payload.get("bridge_received_epoch_ms")
    if received_epoch_ms is not None:
        return ("bridge_received_epoch_ms", str(received_epoch_ms))
    return ("payload", json.dumps(payload, sort_keys=True, separators=(",", ":")))


def fetch_latest(url: str, timeout: float) -> dict | None:
    """Return one Worker sample, or ``None`` while no sample is available."""

    request = Request(
        url.rstrip("/") + "/latest",
        # Cloudflare can reject Python's default ``Python-urllib`` signature.
        # Use a stable application identifier for the portable puller instead.
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "FitQuest-Puller/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Worker HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Worker unavailable: {exc.reason}") from exc

    if not isinstance(payload, dict) or payload.get("status") in {"waiting", "error"}:
        return None
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull FitQuest Garmin telemetry from a Cloudflare Worker.")
    parser.add_argument("--url", required=True, help="FitQuest Worker base URL, without /latest.")
    parser.add_argument("--out", type=Path, required=True, help="Local wearable JSON destination.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between Worker polls.")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout per poll.")
    args = parser.parse_args()

    interval = max(0.5, float(args.interval))
    last_error = None
    last_sample_key = None
    print(f"FitQuest Worker puller started: {args.url}", flush=True)
    while True:
        try:
            payload = fetch_latest(args.url, max(0.5, float(args.timeout)))
            if payload is not None:
                current_sample_key = sample_identity(payload)
                if current_sample_key != last_sample_key:
                    write_json_atomic(args.out, payload)
                    last_sample_key = current_sample_key
                if last_error is not None:
                    print("FitQuest Worker connection recovered.", flush=True)
                last_error = None
            elif last_error is None:
                print("FitQuest Worker is waiting for the first Garmin sample.", flush=True)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            message = str(exc)
            if message != last_error:
                print(message, flush=True)
            last_error = message
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
