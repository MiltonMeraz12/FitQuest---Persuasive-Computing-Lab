# FitQuest

**A sensor-fusion engine for physical interaction.** FitQuest converts camera,
inertial, and physiological measurements into a single normalized signal
specification, and drives a browser application from it to demonstrate the
complete path from physical movement to interaction.

Built during a Mitacs Globalink Research Internship at the
[Persuasive Computing Lab](https://pcl.cs.dal.ca/), Faculty of Computer Science,
Dalhousie University, May–August 2026. The project was originally proposed as
*IronQuest 3D — Smart Dumbbell Fitness Gaming Platform*, which remains the
repository name.

📄 **[Final Internship Report](docs/reports/FitQuest_Final_Internship_Report.tex)**
— architecture, engineering decisions, results, limitations, and future work.

---

## What it does

Three sensing modalities are combined into one payload that clients consume
without knowing anything about the hardware behind it:

| Source | Contributes |
| --- | --- |
| Camera + YOLO26 | 17-keypoint body pose; dumbbell/weight detection associated to left or right limb |
| ESP32-S3 + BNO08x | Forearm orientation, motion intensity, stability, at ~15 Hz over USB and Wi-Fi |
| Garmin Venu 3 | Heart rate, derived exertion level and intensity zone, wrist motion state |

On top of that contract sits a browser client with ten exercises, three session
modes, four difficulty levels, per-repetition multi-sensor validation, and an
animated 3D avatar.

**Per-user calibration** is what makes the signals transferable: a short warm-up
window records each person's comfortable range, so comparable effort maps to
comparable normalized values across users of different height, limb length, and
mobility — with no retraining and no per-user code.

**Out of scope**, deliberately: complex game development, multiplayer,
production platform features, repetition counting from fixed joint-angle
thresholds, and any vision model beyond body pose plus dumbbell detection.

## Hardware

| Item | Notes |
| --- | --- |
| Webcam | Any USB or built-in camera |
| ESP32-S3 DevKitC-1 | I²C to the IMU on `GPIO8`/`GPIO9` |
| BNO08x IMU | Address `0x4B`; housed in the printed enclosure under `hardware/` |
| Power source | USB from the laptop, or a power bank for untethered use |
| Garmin Venu 3 | Optional; heart rate and wrist motion context |
| Shared network | Required only for the wireless inertial path and the wearable relay |

The system degrades gracefully: a missing sensor reduces the corroborating
evidence available, it does not stop the session.

## Quick start

On a fresh machine, clone and run the setup script. It creates the environment,
installs dependencies, verifies the install against the test suite, and reports
what still needs doing by hand. It is safe to re-run.

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

The model weights needed to run are committed, so a clone is functional
immediately — no files to obtain separately. Training data is not: see
[Data and training](#data-and-training) if you intend to retrain.

Then, for a normal session:

```powershell
.\run_ironquest.bat
```

That single command starts the camera and sensor pipeline, publishes the local
browser gateway, and opens the client. The OpenCV monitor stays available
alongside it for diagnostics — close it with `q`, toggle its telemetry panel
with `d`.

**Before a session, on the watch:**

1. Wrist heart rate monitoring must be **on** — `Settings > Health & Wellness >
   Heart Rate > Wrist Heart Rate`. The Connect IQ app reads the sensor's current
   value; if wrist monitoring is off there is nothing to read.
2. Open the **FitQuest Telemetry** app. It transmits only while its view is
   active — closing it or letting the watch sleep stops the stream.

`Broadcast Heart Rate` is a *different* setting and is **not** needed for the
default path. It applies only to the BLE fallback, which is off unless you pass
`--garmin-bridge`.

**No hardware to hand?** Exercise the browser client against a synthetic stream:

```powershell
.\ironquest_env\Scripts\python.exe -m tools.simulate_game_control_stream
```

Every value it produces is generated locally. It is for interface testing only,
never for evidence.

## The payload

Each analyzed frame produces:

| Section | Contents |
| --- | --- |
| `motion_analysis` | Body posture, calibration state, normalized arm signals, symmetry, load tokens |
| `object_detection` | Accepted dumbbell/weight boxes |
| `limbs` | Left/right dumbbell association |
| `wearable` | Heart rate and physiological context |
| `esp32` | Inertial glove telemetry |
| `game_control` | The sensor-fusion specification, schema `2026-08-fusion-v2` |
| `signal_log` | Flat, Pandas-friendly record for analysis |

Clients read `game_control`, never raw model output. That separation is what
allows a different application — a rehabilitation task, an adherence monitor,
another game — to be built against the same signals without touching the
sensing code.

```python
import pandas as pd
df = pd.read_json("runs/validate/sensor_fusion.jsonl", lines=True)
signals = pd.json_normalize(df["signal_log"])
```

## Repository layout

| Path | Contents |
| --- | --- |
| `ironquest/` | Runtime package: CLI, pipeline, sensors, motion analysis, payload, HUD, gateway |
| `web/` | Browser client and vendored 3D library |
| `tools/` | Wearable bridges and the offline stream simulator |
| `tests/` | Regression suite — 62 tests, no hardware required |
| `firmware/` | ESP32-S3 sketches |
| `monkey_c/` | Garmin Connect IQ watch application |
| `hardware/` | Enclosure model, STL, and print files |
| `cloudflare/` | Relay worker and its deployment configuration |
| `configs/` | Ultralytics training profiles |
| `docs/` | Technical documentation, evidence figures, and dated reports |

## Data and training

Two weight files are committed because a clone without them cannot start:

| File | Size | Role |
| --- | --- | --- |
| `weights/yolo26n-pose.pt` | 7.6 MB | Body pose, 17 COCO keypoints |
| `runs/detect/dumbbell_combined_yolo26n/weights/best.pt` | 5.2 MB | Dumbbell and weight detector |

Everything else that training produces stays out of version control. To retrain
you additionally need `data/datasets/dumbbell_combined_yolo26` (775 MB, 7,332
images) and the base `weights/yolo26n.pt`, neither of which is in the
repository. Metrics and the figures behind them are committed under
[`docs/figures/`](docs/figures/README.md), together with the caveats that limit
what they support.

## Verification

```powershell
.\ironquest_env\Scripts\python.exe -m pytest tests\ -q
```

The suite exercises the signal specification rather than the hardware, so it
runs in about six seconds with nothing attached. Detector metrics and the
figures behind them are committed under
[`docs/figures/`](docs/figures/README.md), together with the caveats that limit
what they support.

## Documentation

Start with the [Documentation Index](docs/00_DOCUMENTATION_INDEX.md).

| Document | Covers |
| --- | --- |
| [Project Roadmap](docs/01_PROJECT_ROADMAP.md) | Scope, deadline, deliverables |
| [System Architecture](docs/02_SYSTEM_ARCHITECTURE.md) | Runtime layers and frame-level data flow |
| [Run and Demo Guide](docs/03_RUN_AND_DEMO.md) | What a healthy run looks like |
| [Command Reference](docs/04_COMMAND_REFERENCE.md) | Every CLI command and option |
| [Code Reference](docs/05_CODE_REFERENCE.md) | What each module is responsible for |
| [Sensor-Fusion Payload](docs/06_SENSOR_FUSION_PAYLOAD.md) | The `game_control` specification |
| [Web Game Implementation](docs/07_WEB_GAME_IMPLEMENTATION.md) | Browser client and gateway |
| [ESP32/IMU Hardware](docs/09_ESP32_IMU_HARDWARE.md) | Wiring, bring-up, firmware, wireless transport |
| [Garmin Venu 3 Bridge](docs/10_GARMIN_VENU3_BRIDGE.md) | Watch app, relay, and troubleshooting |

Weekly supervisor reports are under [`docs/reports/`](docs/reports/).

## Status and limitations

The system has been validated technically and exercised in full sessions with
all three sensing modalities. It has **not** been evaluated with independent
participants, so no claim is made about usability, engagement, or adherence.
The detector metrics were obtained on a randomly partitioned dataset and should
be read as an upper bound rather than as evidence of generalization. The browser
client is a proof of concept, not a fitness product.

Section 14 of the report states the limitations in full; Section 15 sets out the
improvement path for each subsystem.

## Author

Milton Estuardo Torres Meraz
[ORCID 0009-0005-3217-9935](https://orcid.org/0009-0005-3217-9935)
Universidad Autónoma de San Luis Potosí — Intelligent Systems Engineering

Supervised by Dr. Rita Orji, Dr. Fidelia Orji, and Dr. Grace Ataguba.
