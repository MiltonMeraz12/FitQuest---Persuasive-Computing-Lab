# Project Pivot Report - Iron Quest 3D

| Field | Value |
| --- | --- |
| Date | 2026-06-23 |
| Focus | Universal sensor-fusion middleware for physical interaction |
| Deadline | 2026-08-07 |
| Primary output | Stable normalized body+dumbbell+sensors JSON pipeline |

## 1. Summary

The project has been narrowed to match the research-paper timeline. The final game is deferred. The active work is to finish a reliable sensor-fusion middleware pipeline that combines camera-based body posture, dumbbell detection, ESP32 glove telemetry, and Garmin Venu 3 heart-rate context into normalized digital signals.

## 2. Engineering Changes

- Removed the abandoned extra keypoint-analysis runtime path.
- Removed matching CLI flags, training commands, tests, tools, model runs, and dataset folders.
- Reworked `game_control` into a sensor-fusion payload.
- Added dynamic auto-calibration and normalized arm signals.
- Added Garmin heart-rate mapping to `exertion_level` and `intensity_zone`.
- Added flat `signal_log` JSONL records for Pandas-based signal analysis.
- Updated `sensors.py` for Garmin-style heart-rate data and ESP32/BNO08X-style orientation data.
- Added ESP32 motion deltas, `stability_index`, and bounded serial parsing per frame.
- Prepared the ESP32 serial firmware path for pitch, roll, yaw, acceleration, and gyroscope telemetry.
- Rewrote the documentation around the paper deadline and active deliverables.

## 3. Current Technical Status

| Area | Status |
| --- | --- |
| Body pose | Active model. |
| Dumbbell detector | Active and still needs controlled local evidence. |
| UI | Active monitor; should be polished for demos. |
| ESP32/IMU glove | Mock serial path ready; real IMU bring-up next. |
| Garmin Venu 3 | Selected wearable path; bridge contract and exertion mapping ready. |
| Signal metrics | Auto-calibration, symmetry, normalized axes, and flat logging ready. |
| Final game | Deferred. |

## 4. Recommended Next Steps

1. Run the full verification stack.
2. Record a short signal-fusion JSONL smoke sample.
3. Capture controlled dumbbell videos.
4. Bring up real ESP32/IMU telemetry.
5. Confirm Garmin heart-rate access path and glove/watch side assignment.
6. Freeze example payloads and figures for the paper.

## 5. Risks

- Dumbbell detection may need more local examples before it is paper-ready.
- ESP32/IMU mounting may introduce noisy orientation data.
- Garmin access may depend on SDK/API permissions or a bridge workaround.
- Normalized signals are camera-derived estimates and need careful validation before user-facing deployment.
- The paper should describe the middleware honestly and avoid implying that the final game is complete.
