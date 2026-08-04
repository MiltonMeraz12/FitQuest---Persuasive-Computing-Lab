# Code Reference

What each module in the runtime package is responsible for.

## `ironquest/__main__.py`

Entry point for `python -m ironquest`. Calls `ironquest.cli.main()`.

## `ironquest/cli.py`

Owns argument parsing, model loading, camera/video input, frame processing, JSONL output, flat `signal_log` export, UI lifecycle, and sensor bridge setup.

Important functions and classes:

- `build_parser()` — every command. `run` (aliases `full`, `demo`) and `detect` share one `add_detection_arguments()` definition and differ only through `DETECT_DEFAULTS` vs `DETECT_COMMAND_DEFAULTS`, so the two commands cannot drift apart.
- `fill_detection_defaults(args)` — applies the `--mode` presets without overriding anything the user passed explicitly.
- `apply_live_command_defaults(args)` — the live-session defaults and environment overrides for `run`.
- `analyze_frame(...)` — the central per-frame data path.
- `PipelineRunner` — camera lifecycle, background bridges, web gateway, one-instance lock.
- `command_run(args)`, `command_detect(args)`, `command_capture_motion_data(args)`, `command_check_esp32(args)`, `command_check_wearable(args)`.

## `ironquest/keypoints.py`

Everything about YOLO body-pose keypoints:

- COCO joint names and `PoseCandidate`;
- `PoseSmoother` for frame-to-frame joint noise and brief occlusion;
- visibility checks and geometric helpers;
- `pose_stream_state(pose)` — the middleware liveness record (is a pose present, how many joints are visible, how confident). It carries no exercise semantics.

## `ironquest/body_context.py`

Connects object detections to body-side context: accepted boxes, rejected boxes, wrist/forearm proximity, temporal hold across short detector dropouts, and left/right loaded state.

## `ironquest/motion_analysis.py`

Builds calibrated movement signals: arm height zone, reach zone, elbow state, dynamic per-session calibration, normalized arm extension/height/reach/range utilization, bilateral symmetry, wrist motion direction, dumbbell loaded state, torso hinge, and whole-body vertical motion candidates.

## `ironquest/game_controls.py`

Builds the paper-facing `game_control` payload: `body_posture`, `dumbbells`, `arm_signals`, `esp32_glove`, `wearable_watch`, `user_state`, `signal_metrics`, `calibration`, `sensor_status`, `tokens`, `axes`, `events`.

It also owns the shared IMU helpers `imu_motion_intensity()` and `imu_motion_state()`. `ui.py` imports them instead of reimplementing the formula, so the OpenCV monitor and the browser can never disagree about how much the hand is moving.

## `ironquest/sensors.py`

Normalizes hardware inputs: Garmin Venu 3 wearable JSON, BLE heart-rate fields, ESP32 serial and UDP JSON, and BNO08x orientation/acceleration/gyroscope/quaternion/stability fields. `ESP32AutoBridge` listens on serial and UDP together and reports which transports are actually live.

## `ironquest/ui.py`

Draws the OpenCV monitor: body skeleton overlay, dumbbell/weight boxes, clean-mode status, and debug-mode axes, tokens, ESP32 vectors, and raw telemetry. It is a developer monitor, not the game interface.

## `ironquest/web_gateway.py`

A standard-library HTTP server that publishes the payload over SSE (`/events`), an annotated preview over MJPEG (`/preview.mjpg`), the browser client itself, and a small control endpoint (`POST /api/control`) for browser-initiated recalibration and session reset.

## `ironquest/capture_analysis.py`

Summarizes a recorded capture session into `capture_analysis.md`: ESP32 sample health, IMU intensity, pose readiness, wearable quality, and arm visibility.

## `tools/`

| Script | Role |
| --- | --- |
| `garmin_connectiq_http_bridge.py` | Receives Connect IQ telemetry from the watch/phone; started by the runtime. |
| `garmin_ble_heart_rate_bridge.py` | BLE heart-rate fallback; started only with `--garmin-bridge`. |
| `fitquest_worker_pull.py` | Pulls the latest Garmin sample from the Cloudflare Worker. |
| `simulate_game_control_stream.py` | Publishes a synthetic `game_control` stream so the browser client can be exercised with no hardware attached. Its output is for UI testing only, never for the paper. |

## Tests

```powershell
.\ironquest_env\Scripts\python.exe -m pytest tests\ -q
```

| Test file | Covers |
| --- | --- |
| `test_cli_detection_defaults.py` | Command defaults and explicit-flag precedence. |
| `test_sensor_fusion_payload.py` | The `game_control` contract, ESP32 bridges, wearable normalization, event debouncing. |
| `test_signal_motion_analysis.py` | Calibration behavior and normalized motion signals. |
| `test_body_context.py` | Dumbbell-to-limb association. |
| `test_object_temporal_tracking.py` | Detector dropout hold and box smoothing. |
| `test_capture_analysis.py` | Offline capture quality reporting. |
| `test_web_gateway.py` | Client serving, SSE payloads, control queue, path-traversal guard. |
| `test_ui_sensor_labels.py` | HUD sensor status wording. |
| `test_garmin_connectiq_http_bridge.py` | Heart-rate sanitization. |
| `test_fitquest_worker_pull.py` | Worker polling and atomic writes. |
