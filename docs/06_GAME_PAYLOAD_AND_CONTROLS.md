# Sensor-Fusion Payload and Web Game Controls

The active deliverable includes a small web-based game vertical slice. The game consumes the universal middleware payload, which can also be logged, analyzed, and reused by future applications.

## Web Game Scope

The browser prototype is intentionally simple. It should demonstrate the complete path from physical movement to interaction without attempting to implement a full RPG, multiplayer system, or commercial fitness platform.

Minimum target:

- a browser client connected to the local `game_control` stream through JSON/JSONL, HTTP, or WebSocket;
- two or three movement-to-action mappings;
- visible feedback such as a target, character state, score, progress, or success indicator;
- a short reproducible demonstration that can be captured for the final report and paper.

## Control Mode

The active `game_control.control_mode` is:

```text
sensor_fusion_engine
```

## Main Idea

The system transforms physical inputs into standardized digital signals:

- normalized values from `0.0` to `1.0`;
- booleans such as dumbbell loaded or not loaded;
- vectors such as pitch, roll, yaw, and acceleration;
- labels such as `intensity_zone`.

## Auto-Calibration

At session start, the first few seconds run in `calibrating` mode. The user moves through a comfortable range, and the system records personal min/max bounds for each side. After that, the same physical effort maps into normalized signals such as:

- `left_arm_extension`
- `right_height_signal`
- `left_range_utilization`
- `symmetry_score`

This keeps the pipeline accessible without changing model weights or editing source code for each user.

## Main Sections

| Section | Meaning |
| --- | --- |
| `body_posture` | YOLO body-pose posture array and side summaries. |
| `dumbbells` | Accepted dumbbell/weight boxes and left/right associations. |
| `arm_signals` | Per-side fusion of camera pose, dumbbell association, and attached hardware. |
| `esp32_glove` | High-resolution glove IMU stream: orientation, motion deltas, and `stability_index`. |
| `wearable_watch` | Garmin watch stream: heart rate plus derived exertion values. |
| `user_state` | Overall normalized user state, including `exertion_level` and `intensity_zone`. |
| `signal_metrics` | Calibrated camera signals and bilateral comparison. |
| `calibration` | Current calibration state and observed min/max bounds. |
| `axes` | Compact normalized values for UI and future mapping. |
| `events` | Neutral event candidates such as `CALIBRATING` or `BODY_JUMP_CANDIDATE`. |

## Asymmetric Hardware Setup

Default runtime assumption:

- ESP32 + IMU gym glove: `--esp32-side right`
- Garmin smartwatch: `--wearable-side left`

Both can be changed from the CLI without changing code.

## Example Payload

```json
{
  "status": "ready",
  "control_mode": "sensor_fusion_engine",
  "schema_version": "2026-08-fusion-v2",
  "axes": {
    "left_arm_extension": 0.72,
    "right_arm_extension": 0.64,
    "left_height_signal": 0.81,
    "right_height_signal": 0.44,
    "symmetry_score": 0.91,
    "stability_index": 0.84,
    "exertion_level": 0.38
  },
  "arm_signals": {
    "left": {
      "pose": {
        "arm_extension": 0.72,
        "height_signal": 0.81,
        "range_utilization": 0.66
      },
      "hardware": {
        "wearable_watch": {
          "device": "garmin_venu_3",
          "heart_rate_bpm": 96
        }
      }
    },
    "right": {
      "pose": {
        "arm_extension": 0.64,
        "height_signal": 0.44,
        "range_utilization": 0.58
      },
      "hardware": {
        "esp32_glove": {
          "mounted_side": "right",
          "transport": "udp",
          "remote": "192.168.1.50:4211",
          "orientation_euler_deg": {
            "pitch": 4.1,
            "roll": -2.0,
            "yaw": 91.5
          },
          "motion_intensity": 0.42,
          "motion_state": "active",
          "sample_rate_hz": 15.15,
          "stability_index": 0.84
        }
      }
    }
  },
  "user_state": {
    "heart_rate_bpm": 96,
    "exertion_level": 0.3,
    "intensity_zone": "low"
  }
}
```

## JSONL Signal Export

Each saved frame also includes `signal_log`, a flat record for Pandas:

```python
import pandas as pd

df = pd.read_json("runs/validate/sensor_fusion.jsonl", lines=True)
signals = pd.json_normalize(df["signal_log"])
```

Useful columns include `left_arm_extension`, `right_arm_extension`, `symmetry_score`, `heart_rate_bpm`, `exertion_level`, `intensity_zone`, `stability_index`, `imu_motion_delta_mps2`, `imu_motion_intensity`, `imu_rotation_intensity`, `imu_motion_state`, and `imu_sample_rate_hz`.

## Current Limits

- Camera posture is 2D.
- Object boxes can fail during occlusion or poor lighting.
- IMU values need stable mounting and calibration before they can be treated as reliable controls.
- Heart rate is an intensity/context signal, not a hard stop.
- The web game is a proof of concept; it should not be presented as a complete fitness product.
