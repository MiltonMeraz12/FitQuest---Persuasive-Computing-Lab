"""Write a Garmin-style wearable JSON file for local UI testing.

This does not emulate Garmin transport. It only keeps the project's existing
``--wearable-json`` bridge alive while the real watch path is being evaluated.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path


def build_sample(started_at: float, resting_bpm: int, peak_bpm: int, activity_state: str) -> dict:
    """Return one synthetic wearable sample with a smooth heart-rate trend."""

    elapsed = max(0.0, time.time() - started_at)
    wave = (math.sin(elapsed / 12.0) + 1.0) / 2.0
    bpm = int(round(resting_bpm + wave * (peak_bpm - resting_bpm)))
    return {
        "status": "connected",
        "device": "garmin_venu_3",
        "provider": "garmin",
        "sample_type": "mock_heart_rate_bridge",
        "heart_rate_bpm": bpm,
        "heart_rate_confidence": "simulated",
        "resting_heart_rate_bpm": resting_bpm,
        "max_heart_rate_bpm": peak_bpm,
        "activity_state": activity_state,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "battery": 87,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously write a Garmin-style wearable JSON sample.")
    parser.add_argument("--out", type=Path, default=Path("runs/validate/wearable_live.json"))
    parser.add_argument("--seconds", type=float, default=0.0, help="Stop after N seconds. Use 0 to run until Ctrl+C.")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--resting-bpm", type=int, default=65)
    parser.add_argument("--peak-bpm", type=int, default=150)
    parser.add_argument("--activity-state", default="controlled_dumbbell_movement")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    while True:
        sample = build_sample(started_at, args.resting_bpm, args.peak_bpm, args.activity_state)
        args.out.write_text(json.dumps(sample, indent=2), encoding="utf-8")
        print(json.dumps({"status": "updated", "path": str(args.out), "heart_rate_bpm": sample["heart_rate_bpm"]}))
        if args.seconds and (time.time() - started_at) >= args.seconds:
            break
        time.sleep(max(0.1, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
