# System Architecture

Iron Quest 3D runs through:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest
```

The active architecture is a camera-plus-sensor middleware pipeline for normalized physical-interaction signals.

## Data Flow

```text
Camera frame
  -> YOLO26 body pose
  -> pose smoothing
  -> dumbbell/weight detector
  -> body/object side association
  -> middleware pose state
  -> auto-calibrated motion signal analysis
  -> Garmin-style wearable context payload
  -> ESP32/IMU serial payload
  -> sensor-fusion game_control payload
  -> flat signal_log record
  -> preview window / JSONL / web-based game bridge
```

## Runtime Layers

| Layer | File | Purpose |
| --- | --- | --- |
| Command-line interface | `ironquest/cli.py` | Defines commands and connects the full program. |
| Detector UI | `ironquest/ui.py` | Draws body pose, dumbbell boxes, sensor status, and debug telemetry. |
| Keypoint utilities | `ironquest/keypoints.py` | Reads YOLO body-pose keypoints, smooths joints, calculates geometry, and reports middleware pose-stream state. |
| Dumbbell/body context | `ironquest/body_context.py` | Links detected objects to left/right wrist or forearm context. |
| Motion signal analysis | `ironquest/motion_analysis.py` | Calibrates each session and describes normalized arm extension, height, reach, range utilization, load, and bilateral symmetry. |
| Sensor adapters | `ironquest/sensors.py` | Normalizes Garmin-style wearable JSON and ESP32 serial/UDP telemetry. |
| Sensor-fusion payload | `ironquest/game_controls.py` | Converts detector and sensor output into asymmetric hardware fusion and future-application JSON. |
| Browser gateway | `ironquest/web_gateway.py` | Publishes the payload and an annotated preview to the FitQuest web client over SSE/MJPEG. |
| Capture analysis | `ironquest/capture_analysis.py` | Summarizes a recorded capture session into a quality report. |

`game_controls.py` owns the shared IMU intensity formula (`imu_motion_intensity`
and `imu_motion_state`). `ui.py` imports it rather than reimplementing it, so
the OpenCV monitor and the browser client can never disagree about how much the
hand is moving.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `ironquest/` | Runtime package. |
| `web/` | FitQuest browser client and its vendored Three.js build. |
| `tools/` | Support scripts started by the runtime or run manually for diagnostics. |
| `tests/` | Regression tests for active runtime behavior. |
| `firmware/` | ESP32-S3 sketches (BNO08x telemetry over serial + Wi-Fi UDP, and an I2C scanner). |
| `monkey_c/` | Garmin Connect IQ watch app. |
| `hardware/` | ESP32/IMU glove case model and print files. |
| `cloudflare/` | Worker that relays Garmin Connect IQ samples to the laptop. |
| `configs/` | Ultralytics training profiles. |
| `docs/` | Technical documentation; `docs/reports/` holds the dated supervisor reports. |
| `presentations/` | Slide deck exported for lab presentations. |
| `data/datasets/` | Local datasets (not in git). |
| `data/captures/` | Captured videos, frames, metadata, and JSONL (not in git). |
| `runs/detect/` | Object-detection training and validation outputs (not in git). |
| `runs/pose/` | Body-pose outputs (not in git). |
| `runs/validate/` | Smoke-test, bridge logs, and validation artifacts (not in git). |
| `weights/` | Base model weights (not in git). |

## Active Model Boundaries

| Model path | Role |
| --- | --- |
| `weights/yolo26n-pose.pt` | Base body-pose model. |
| `runs/detect/dumbbell_combined_yolo26n/weights/best.pt` | Dumbbell/weight detector. |

The paper scope uses only body pose and dumbbell/weight boxes on the vision side.

## Why Motion Primitives?

The project needs stable normalized signals before mapping them to game rules. The final application will use a deliberately small web-based game slice, so the signal layer remains the important reusable contribution while the game provides a concrete end-to-end demonstration.

Examples:

- `right_arm_overhead`
- `left_arm_torso_height`
- `right_arm_extended`
- `left_dumbbell_loaded`
- `both_dumbbells_loaded`
- `body_jump_candidate`
- `right_overhead_left_front_candidate`

Normalized signal examples:

- `left_arm_extension`
- `right_height_signal`
- `left_range_utilization`
- `symmetry_score`
- `stability_index`
- `exertion_level`

## Payload Design

Each frame produces a dictionary that can be printed, saved to JSONL, or used by the UI.

| Section | Meaning |
| --- | --- |
| `motion_analysis` | Body posture, side states, and movement tokens. |
| `object_detection` | Accepted dumbbell/weight boxes and filtered candidates. |
| `limbs` | Left/right object association. |
| `wearable` | Garmin-style heart-rate and session context. |
| `esp32` | Direct IMU telemetry from serial/UDP JSON. |
| `game_control` | Paper-facing sensor-fusion payload with normalized signals and asymmetric hardware fusion. |
| `signal_log` | Flat Pandas-friendly frame record for signal analysis. |

## Current Limitations

- A single camera is still a 2D source, so true depth is approximate.
- Dumbbell boxes can be missed when the object is small, blurred, or visually merged with the body; reliable paper claims need local lab data.
- Garmin data adds physiology and session context, not object pose, and its samples can arrive with latency.
- ESP32/IMU data requires stable mounting, firmware, timing, and calibration. The forearm case rotation sets an absolute pitch offset, so per-rep validation keys off excursion rather than absolute angle.
- The web game is intentionally limited to a few reliable actions and feedback states so it can be completed, tested, and documented within the internship.
