# Command Reference

For normal project use, run only this from the project root:

```powershell
.\run_ironquest.bat
```

That launcher starts the live model, camera UI, browser client, automatic ESP32+IMU USB/Wi-Fi listener, and the Garmin wearable path with the project defaults.

Everything below is for debugging, data capture, and maintenance. The internal Python entry point is:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest
```

## Command Overview

| Command | Purpose |
| --- | --- |
| `run` (aliases `full`, `demo`) | The live session: body pose, dumbbell detection, sensors, UI, and browser client. |
| `detect` | The same pipeline with neutral defaults for camera/video debugging. |
| `capture-motion-data` | Save frames, video, metadata, and JSONL payloads. |
| `analyze-capture` | Summarize a recorded capture and write a markdown quality report. |
| `dataset-report` | Show dumbbell dataset counts and object-training metrics. |
| `prepare-combined-dumbbell-data` | Merge the dumbbell datasets. |
| `train-combined-dumbbell-detector` | Train the combined dumbbell detector. |
| `train-object-detector` | Train any YOLO object detector from a data YAML. |
| `validate-object-detector` | Validate a YOLO object detector. |
| `train-body-pose` | Train or refit a 17-point body-pose model. |
| `export-pose` | Export a pose model for deployment experiments. |
| `check-esp32` | Read ESP32 newline-delimited JSON over USB serial or Wi-Fi UDP. |
| `check-wearable` | Read Garmin-style wearable JSON. |

## `run` vs `detect`

Both drive the same `PipelineRunner` and accept the same options. They differ only in defaults:

| Option | `run` | `detect` |
| --- | --- | --- |
| `--mode` | `full` | unset (no preset applied) |
| `--mirror` | on | off |
| `--display-width` | 1100 | 960 |
| `--object-imgsz` | 640 | 960 |
| `--pose-smoothing` | 0.45 | 0.55 |
| `--ui-detail` | `debug` | `simple` |
| `--wearable-stale-seconds` | 5 | 10 |
| Garmin bridges | started automatically | off unless requested |

`run` also reads environment overrides (`FITQUEST_WORKER_URL`, `IRONQUEST_WEARABLE_JSON`, `IRONQUEST_GARMIN_CONNECTIQ_BRIDGE`, `IRONQUEST_GARMIN_BRIDGE`) and takes a single-instance lock so two live sessions cannot fight over the camera.

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest run
```

Useful options:

- `--source 0` — camera index, video path, or stream URL
- `--mode vision|dumbbells|full`
- `--object-model path\best.pt`
- `--object-conf 0.20`
- `--calibration-seconds 7`
- `--esp32-side right` / `--wearable-side left`
- `--esp32-transport auto|serial|udp|none`
- `--esp32-port auto` / `--esp32-udp-port 4210`
- `--jsonl .\runs\validate\sensor_fusion.jsonl`
- `--web` / `--web-port 8787`
- `--no-show` — no OpenCV window
- `--max-frames 30`

## `capture-motion-data`

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --label controlled_dumbbell_sequence --source 0 --duration 30 --save-every 5 --video
```

Collects project-specific images, video, metadata, and JSONL payloads. Configure calibration and hardware sides when needed:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --label accessible_signal_trial --source 0 --calibration-seconds 7 --esp32-side right --wearable-side left --duration 30 --video
```

`--calibration-seconds` lets the system learn each user's comfortable range at startup. `--esp32-side` and `--wearable-side` describe the asymmetric glove/watch setup without editing code.

## `analyze-capture`

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture
```

Analyzes the newest session in `data/captures` and writes `capture_analysis.md` beside `motion_payloads.jsonl`. Analyze a specific capture:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture .\data\captures\SESSION_FOLDER
```

Options: `--out .\runs\validate\capture_analysis.md`, `--json`.

## Training

Train the dumbbell detector:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-combined-dumbbell-detector --device 0
```

Train from a custom object dataset:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-object-detector --data .\data\datasets\my_dataset\data.yaml --model yolo26n.pt
```

Train body pose only when a valid 17-point dataset exists:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-body-pose --device 0
```

Hyperparameters come from `configs/ultralytics_training_config.yaml`. See [11_DATA_CAPTURE_AND_TRAINING.md](11_DATA_CAPTURE_AND_TRAINING.md).

## ESP32 Checks

USB serial, with auto-detection:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --port auto --seconds 10 --list-ports
```

If Windows exposes multiple serial devices, pass the port explicitly, for example `--port COM4`. Close the Arduino Serial Monitor first; it holds the port.

Wi-Fi UDP:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --transport udp --udp-host 0.0.0.0 --udp-port 4210 --seconds 30
```

Full setup instructions are in [09_ESP32_IMU_HARDWARE.md](09_ESP32_IMU_HARDWARE.md).

## Garmin Checks

The normal launcher starts the Connect IQ receiver automatically. Connect IQ is the default source because it carries the richer watch payload; the BLE fallback stays off by default so two writers cannot overwrite each other's samples in the shared wearable file.

Disable a bridge only for diagnostics:

```powershell
.\run_ironquest.bat --no-garmin-connectiq-bridge
```

```powershell
.\run_ironquest.bat --no-garmin-bridge
```

Run the Connect IQ HTTP receiver manually when diagnosing the phone/watch app:

```powershell
.\ironquest_env\Scripts\python.exe .\tools\garmin_connectiq_http_bridge.py --host 0.0.0.0 --port 8765 --out .\runs\validate\wearable_live.json --print-samples
```

Try the BLE heart-rate bridge manually only when diagnosing Bluetooth:

```powershell
.\ironquest_env\Scripts\python.exe .\tools\garmin_ble_heart_rate_bridge.py --out .\runs\validate\wearable_live.json --name Venu --resting-bpm 65 --max-bpm 180
```

Read whatever a bridge has written:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-wearable --path .\runs\validate\wearable_live.json --seconds 2 --stale-seconds 5
```

Full setup and troubleshooting are in [10_GARMIN_VENU3_BRIDGE.md](10_GARMIN_VENU3_BRIDGE.md).

## Browser Client Without Hardware

To exercise the web client with no camera, ESP32, or watch attached:

```powershell
.\ironquest_env\Scripts\python.exe -m tools.simulate_game_control_stream
```

This publishes a synthetic stream through the real payload builders. Every value it produces is generated locally, so it is for UI testing only and never for paper evidence.

## Removed Commands

Specialized extra keypoint-model training and validation commands were removed in the June 23, 2026 scope pivot. The active pipeline is body pose plus dumbbell boxes plus external sensors.
