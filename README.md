# Iron Quest 3D

Iron Quest 3D is now scoped as a **universal sensor-fusion engine for physical interaction** with a small web-based game application for the August 7, 2026 research-paper deadline. The active goal is to finish a reliable pipeline that converts camera, dumbbell, ESP32/IMU, and wearable data into normalized JSON signals, then demonstrate those signals through a simple browser-based interaction.

## Active Scope

- YOLO body-pose tracking for upper-body posture and movement primitives.
- YOLO dumbbell/weight object detection linked to body-side context.
- OpenCV monitoring UI for supervisor demos and debugging.
- ESP32-S3 + BNO08X IMU telemetry over USB serial or Wi-Fi UDP.
- Heart-rate wearable context through a bridge JSON contract.
- Dynamic auto-calibration so different users can produce the same 0.0-1.0 signal contract without code changes.
- Bilateral symmetry, arm extension, range utilization, stability index, exertion level, and intensity zones.
- Sensor-fusion payloads plus flat `signal_log` records saved to JSONL for later analysis and paper figures.
- A lightweight web-based game slice that consumes `game_control` and maps a few stable movement signals to visible actions and feedback.

The browser game is a live client of the existing sensor-fusion pipeline. Start the complete application with one command:

```powershell
.\run_ironquest.bat
```

The launcher starts the camera and sensor pipeline, publishes the local browser gateway, and opens the FitQuest client automatically. The browser receives a clean movement preview; the technical OpenCV monitor remains available separately for diagnostics. See [Web Game Implementation](docs/23_WEB_GAME_IMPLEMENTATION.md) for the system contract.

## Out of Scope

- Complex game development, multiplayer, and production-grade platform features.
- Rule-based gym rep counting.
- Any extra vision model outside body pose plus dumbbell/weight detection.

## Main Command

```powershell
.\run_ironquest.bat
```

This is the normal project entry point. It starts the camera, YOLO pose model, dumbbell detector, sensor bridges, local web gateway, and browser client with the project defaults.

Advanced checks and maintenance commands live in [Command Reference](docs/07_COMMAND_REFERENCE.md). Daily use should stay on the launcher above.

## Dumbbell Detector Dataset

The active local object dataset is:

```text
data/datasets/dumbbell_combined_yolo26
```

Inspect the dataset and latest object-detection metrics:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest dataset-report
```

Train the combined dumbbell detector:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-combined-dumbbell-detector --device 0
```

## Sensor Payload

Each analyzed frame includes:

- `motion_analysis`: body posture, calibration state, normalized arm signals, symmetry, and load tokens.
- `object_detection`: accepted dumbbell/weight boxes.
- `limbs`: left/right dumbbell association.
- `wearable`: Garmin-style heart-rate context.
- `esp32`: ESP32/IMU telemetry.
- `game_control`: paper-facing sensor-fusion JSON contract with asymmetric hardware fusion.
- `signal_log`: flat Pandas-friendly signal record.

The web game should read `game_control`, not raw YOLO outputs. The browser prototype is intentionally small and exists to demonstrate the complete sensor-to-action path.

## Documentation

Start with:

- [Documentation Index](docs/00_DOCUMENTATION_INDEX.md)
- [Project Roadmap](docs/01_PROJECT_ROADMAP.md)
- [System Architecture](docs/02_SYSTEM_ARCHITECTURE.md)
- [Run and Demo Guide](docs/03_RUN_AND_DEMO.md)
- [Sensors and Materials](docs/05_SENSORS_AND_MATERIALS.md)
