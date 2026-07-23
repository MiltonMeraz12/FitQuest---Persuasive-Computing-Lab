# Command Reference

For normal project use, run only this from the project root:

```powershell
.\run_ironquest.bat
```

That launcher starts the live model, camera UI, automatic ESP32+IMU USB/Wi-Fi listener, and Garmin-ready wearable slot with the project defaults.

Advanced commands below are kept for debugging, data capture, and maintenance.

Internal Python entry point:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest
```

## Command Overview

| Command | Purpose |
| --- | --- |
| `full` | Run body pose, dumbbell detection, UI, Garmin JSON polling, and ESP32 polling. |
| `detect` | Run the configurable camera/video middleware. |
| `capture-motion-data` | Save frames, video, metadata, and JSONL payloads. |
| `analyze-capture` | Summarize a recorded capture and write a markdown quality report. |
| `dataset-report` | Show active dumbbell dataset counts and object-training metrics. |
| `prepare-combined-dumbbell-data` | Merge dumbbell datasets. |
| `train-combined-dumbbell-detector` | Train the active combined dumbbell detector. |
| `train-object-detector` | Train any YOLO object detector from a data YAML. |
| `validate-object-detector` | Validate a YOLO object detector. |
| `train-body-pose` | Train or refit a 17-point body-pose model. |
| `export-pose` | Export a pose model for deployment experiments. |
| `check-wearable` | Read Garmin-style wearable JSON. |
| `check-esp32` | Read ESP32 newline-delimited JSON over USB serial or Wi-Fi UDP. |

## `full`

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest run
```

Useful options:

- `--object-model path\best.pt`
- `--object-imgsz 960`
- `--object-conf 0.20`
- `--wearable-json .\docs\wearable_sample.json`
- `--calibration-seconds 7`
- `--esp32-side right`
- `--esp32-transport serial`
- `--esp32-transport none`
- `--wearable-side left`
- `--esp32-port auto`
- `--esp32-udp-port 4210`
- `--jsonl .\runs\validate\sensor_fusion.jsonl`
- `--no-show`
- `--max-frames 30`

## `detect`

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest detect --mode full --source 0
```

Valid modes:

- `vision`
- `dumbbells`
- `full`

## `capture-motion-data`

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --label controlled_dumbbell_sequence --source 0 --duration 30 --save-every 5 --video
```

Use this to collect project-specific images, video, metadata, and JSONL payloads.

Configure calibration and hardware sides when needed:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --label accessible_signal_trial --source 0 --calibration-seconds 7 --esp32-side right --wearable-side left --duration 30 --video
```

`--calibration-seconds` lets the system learn each user's comfortable range at startup. `--esp32-side` and `--wearable-side` describe the asymmetric glove/watch setup without editing code.

## `analyze-capture`

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture
```

By default this analyzes the newest session in `data/captures` and writes `capture_analysis.md` beside `motion_payloads.jsonl`.

Analyze a specific capture:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture .\data\captures\SESSION_FOLDER
```

Useful options:

- `--out .\runs\validate\capture_analysis.md`
- `--json`

## Training

Train the active dumbbell detector:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-combined-dumbbell-detector --device 0
```

Train from a custom object dataset:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-object-detector --data .\data\datasets\my_dataset\data.yaml --model yolo26n.pt
```

Train body pose only when a valid 17-point body-pose dataset exists:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-body-pose --device 0
```

## Removed Commands

Specialized extra keypoint-model training and validation commands were removed during the June 23, 2026 scope pivot. The active paper pipeline is body pose plus dumbbell boxes plus external sensors.

## Sensor Checks

The normal one-command launcher starts one live IronQuest session with the ESP32 auto bridge, Garmin Connect IQ receiver, camera, UI, and JSON polling:

```powershell
.\run_ironquest.bat
```

For richer Garmin data, open the sideloaded `IronQuest Telemetry` Connect IQ app on the Venu 3 after launching the system. The watch app sends to:

```text
http://<laptop-wifi-ip>:8765/garmin
```

For the optional BLE-only fallback heart rate, enable this on the Garmin Venu 3 and opt in with `--garmin-bridge`:

```text
Settings > Watch Sensors > Wrist Heart Rate > Broadcast Heart Rate
```

Connect IQ is the default Garmin source because it carries the richer watch payload. The BLE fallback is intentionally disabled by default to prevent competing writers from replacing the shared wearable file with `MISSING DEVICE`.

Disable the background Garmin bridges only for diagnostics:

```powershell
.\run_ironquest.bat --no-garmin-bridge
```

```powershell
.\run_ironquest.bat --no-garmin-connectiq-bridge
```

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-wearable --path .\docs\wearable_sample.json --seconds 2 --stale-seconds 0
```

Run the Connect IQ HTTP receiver manually only when diagnosing the phone/watch app:

```powershell
.\ironquest_env\Scripts\python.exe .\tools\garmin_connectiq_http_bridge.py --host 0.0.0.0 --port 8765 --out .\runs\validate\wearable_live.json --print-samples
```

Simulate a live Garmin-style wearable JSON file while the real watch bridge is being evaluated:

```powershell
.\ironquest_env\Scripts\python.exe .\tools\simulate_wearable_json.py --out .\runs\validate\wearable_live.json
```

Try the Garmin Venu 3 BLE heart-rate bridge manually only when diagnosing Bluetooth:

```powershell
.\ironquest_env\Scripts\python.exe .\tools\garmin_ble_heart_rate_bridge.py --out .\runs\validate\wearable_live.json --name Venu --resting-bpm 65 --max-bpm 180
```

Then run the UI without ESP32 hardware:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest detect --mode full --source 0 --wearable-json .\runs\validate\wearable_live.json --wearable-stale-seconds 5 --esp32-transport none --ui-detail debug
```

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --port auto --seconds 10
```

For the validated BNO08x ESP32 glove prototype, start with auto-detection. If Windows exposes multiple serial devices, pass the visible ESP32 port explicitly, for example `--port COMx`.

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --port auto --seconds 10 --list-ports
```

For the Wi-Fi/UDP prototype, first start the Python listener:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --transport udp --udp-host 0.0.0.0 --udp-port 4210 --seconds 30
```

Then copy `firmware/esp32_s3_bno08x_udp/wifi_config.example.h` to `firmware/esp32_s3_bno08x_udp/wifi_config.h`, set `WIFI_SSID` and `WIFI_PASSWORD`, keep broadcast enabled, then flash `firmware/esp32_s3_bno08x_udp/esp32_s3_bno08x_udp.ino`. The normal runtime also sends UDP discovery packets, so the ESP32 can learn the laptop address when the hotspot or network changes.

Run the live UI with UDP:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest detect --mode full --source 0 --esp32-transport udp --esp32-udp-port 4210 --esp32-side right --ui-detail debug
```
