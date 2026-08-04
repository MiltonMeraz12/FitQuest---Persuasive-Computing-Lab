# Iron Quest 3D (FitQuest)

Iron Quest 3D is a **universal sensor-fusion engine for physical interaction**, plus a small browser game that proves the complete sensor-to-action path. It converts camera, dumbbell, ESP32/IMU, and wearable data into a normalized JSON signal contract, then demonstrates those signals through a live web client.

Built as a Mitacs Globalink research project at Dalhousie University's Persuasive Computing Lab, for a research paper due August 7, 2026.

## Run It

```powershell
.\run_ironquest.bat
```

That is the whole daily workflow. The launcher starts the camera and sensor pipeline, publishes the local browser gateway, and opens the FitQuest client automatically. The technical OpenCV monitor stays available beside it for diagnostics.

Before a session, enable heart-rate broadcast on the Garmin Venu 3:

```text
Settings > Watch Sensors > Wrist Heart Rate > Broadcast Heart Rate
```

Close the OpenCV monitor with `q`; press `d` to toggle the telemetry panel.

## What It Does

- YOLO body-pose tracking for upper-body posture and movement primitives.
- YOLO dumbbell/weight object detection linked to body-side context.
- ESP32-S3 + BNO08x IMU glove telemetry over USB serial and Wi-Fi UDP simultaneously.
- Garmin Venu 3 context through a Connect IQ watch app, a Cloudflare Worker relay, and a BLE fallback.
- Dynamic per-user auto-calibration, so different people produce the same 0.0-1.0 signal contract without code changes.
- Bilateral symmetry, arm extension, range utilization, stability index, exertion level, and intensity zones.
- Sensor-fusion payloads plus flat `signal_log` records written to JSONL for later analysis and paper figures.
- A browser game that consumes `game_control`, prescribes exercises, validates each repetition against camera + IMU + watch evidence, and animates a 3D avatar.

Out of scope: complex game development, multiplayer, production platform features, rule-based gym rep counting, and any vision model beyond body pose plus dumbbell/weight detection.

## Frame Payload

Each analyzed frame produces:

| Section | Contents |
| --- | --- |
| `motion_analysis` | Body posture, calibration state, normalized arm signals, symmetry, load tokens. |
| `object_detection` | Accepted dumbbell/weight boxes. |
| `limbs` | Left/right dumbbell association. |
| `wearable` | Garmin heart-rate and physiology context. |
| `esp32` | ESP32/IMU glove telemetry. |
| `game_control` | The paper-facing sensor-fusion contract, with asymmetric hardware fusion. |
| `signal_log` | Flat Pandas-friendly signal record. |

Clients read `game_control`, never raw YOLO output.

## Repository Layout

| Path | Contents |
| --- | --- |
| `ironquest/` | Runtime package: CLI, pipeline, sensors, motion analysis, payload, HUD, web gateway. |
| `web/` | FitQuest browser client. |
| `tools/` | Bridges started by the runtime, plus an offline stream simulator. |
| `tests/` | Regression tests. |
| `firmware/` | ESP32-S3 sketches. |
| `monkey_c/` | Garmin Connect IQ watch app. |
| `hardware/` | Glove case model and print files. |
| `cloudflare/` | Worker relaying Garmin samples. |
| `configs/` | Ultralytics training profiles. |
| `docs/` | Technical documentation and dated supervisor reports. |

## Setup

```powershell
python -m venv ironquest_env
.\ironquest_env\Scripts\python.exe -m pip install -r requirements.txt
```

Run the tests:

```powershell
.\ironquest_env\Scripts\python.exe -m pytest tests\ -q
```

## Documentation

Start with the [Documentation Index](docs/00_DOCUMENTATION_INDEX.md).

- [Project Roadmap](docs/01_PROJECT_ROADMAP.md) — scope, deadline, deliverables
- [System Architecture](docs/02_SYSTEM_ARCHITECTURE.md) — runtime layers and data flow
- [Run and Demo Guide](docs/03_RUN_AND_DEMO.md) — what a healthy run looks like
- [Command Reference](docs/04_COMMAND_REFERENCE.md) — every CLI command
- [Sensor-Fusion Payload](docs/06_SENSOR_FUSION_PAYLOAD.md) — the `game_control` contract
- [Web Game Implementation](docs/07_WEB_GAME_IMPLEMENTATION.md) — browser client and gateway
- [ESP32/IMU Hardware](docs/09_ESP32_IMU_HARDWARE.md) — wiring, firmware, wireless transport
- [Garmin Venu 3 Bridge](docs/10_GARMIN_VENU3_BRIDGE.md) — watch app and troubleshooting
