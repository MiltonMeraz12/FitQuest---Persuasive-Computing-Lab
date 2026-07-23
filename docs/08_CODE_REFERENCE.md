# Code Reference

This file maps the current source tree after the June 23, 2026 cleanup.

## `ironquest/__main__.py`

Entry point for:

```powershell
python -m ironquest
```

It calls `ironquest.cli.main()`.

## `ironquest/cli.py`

Owns:

- argument parsing;
- model loading;
- camera/video input;
- frame processing;
- JSONL output;
- flat `signal_log` export;
- UI lifecycle;
- sensor bridge setup.

Important functions/classes:

- `fill_detection_defaults(args)`
- `analyze_frame(...)`
- `PipelineRunner`
- `command_detect(args)`
- `command_demo(args)`
- `command_capture_motion_data(args)`
- `command_check_wearable(args)`
- `command_check_esp32(args)`

## `ironquest/ui.py`

Draws the OpenCV monitor:

- body skeleton overlay;
- dumbbell/weight boxes;
- clean mode status;
- debug mode axes, tokens, ESP32 vectors, and raw ESP32 JSON.

## `ironquest/keypoints.py`

Handles YOLO body-pose keypoints:

- COCO joint names;
- `PoseCandidate`;
- smoothing;
- visibility checks;
- geometric helpers.

## `ironquest/body_context.py`

Connects object detections to body-side context:

- accepted boxes;
- rejected boxes;
- wrist/forearm proximity;
- temporal hold for short dumbbell detector dropouts;
- left/right loaded state.

## `ironquest/movement.py`

Keeps a lightweight middleware pose state for compatibility. It does not count reps or enforce exercise labels.

## `ironquest/motion_analysis.py`

Builds calibrated movement signals:

- arm height zone;
- reach zone;
- elbow state;
- dynamic session calibration;
- normalized arm extension, height, reach, and range utilization;
- bilateral symmetry score;
- wrist motion direction;
- dumbbell loaded state;
- whole-body vertical motion candidate.

## `ironquest/game_controls.py`

Builds the paper-facing `game_control` payload:

- `body_posture`
- `dumbbells`
- `arm_signals`
- `esp32_glove`
- `wearable_watch`
- `user_state`
- `signal_metrics`
- `calibration`
- `sensor_status`
- `tokens`
- `axes`
- `events`

## `ironquest/sensors.py`

Normalizes optional hardware inputs:

- Garmin Venu 3 style wearable JSON;
- BLE heart-rate shaped fields;
- ESP32 serial JSON;
- BNO08X-style orientation, acceleration, gyroscope, quaternion, and stability fields.

## Tests

Active tests:

- `tests/test_cli_detection_defaults.py`
- `tests/test_object_temporal_tracking.py`
- `tests/test_sensor_fusion_payload.py`
- `tests/test_signal_motion_analysis.py`

Run:

```powershell
.\ironquest_env\Scripts\python.exe -m pytest
```
