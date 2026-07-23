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
| Keypoint utilities | `ironquest/keypoints.py` | Reads YOLO body-pose keypoints, smooths joints, and calculates geometry. |
| Dumbbell/body context | `ironquest/body_context.py` | Links detected objects to left/right wrist or forearm context. |
| Middleware pose state | `ironquest/movement.py` | Reports whether the pose stream is alive. |
| Motion signal analysis | `ironquest/motion_analysis.py` | Calibrates each session and describes normalized arm extension, height, reach, range utilization, load, and bilateral symmetry. |
| Sensor adapters | `ironquest/sensors.py` | Normalizes Garmin-style wearable JSON and ESP32 serial telemetry. |
| Sensor-fusion payload | `ironquest/game_controls.py` | Converts detector and sensor output into asymmetric hardware fusion and future-application JSON. |

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
| `esp32` | Direct IMU telemetry from serial JSON. |
| `game_control` | Paper-facing sensor-fusion payload with normalized signals and asymmetric hardware fusion. |
| `signal_log` | Flat Pandas-friendly frame record for signal analysis. |

## Current Limitations

- A single camera is still a 2D source, so true depth is approximate.
- Dumbbell detection depends on local labeled examples from the real lab setup.
- Garmin data adds physiology and session context, not object pose.
- ESP32/IMU data requires stable mounting, firmware, timing, and calibration.
- The web game is intentionally limited to a few reliable actions and feedback states so it can be completed, tested, and documented within the internship.
