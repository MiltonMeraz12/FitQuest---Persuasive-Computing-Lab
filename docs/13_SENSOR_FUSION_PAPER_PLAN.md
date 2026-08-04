# Sensor Fusion Paper Plan

The project now supports one near-term academic deliverable: a paper about a sensor-fusion middleware that prepares physical dumbbell movement data for future interactive systems.

## Paper Claim

Iron Quest 3D can combine:

- camera-based body posture;
- dumbbell/weight bounding boxes;
- ESP32 + BNO08X-style inertial telemetry;
- Garmin Venu 3 heart-rate context;
- dynamic calibration, normalized arm signals, bilateral symmetry, stability index, and exertion level;
- a stable JSON payload that feeds a small web-based game slice.

The paper should describe the middleware, data pipeline, and the web-based game as a proof-of-concept application. It should not claim that the prototype is a complete commercial game or a fully validated fitness platform.

## Target Deadline

Latest delivery target: **August 7, 2026**.

## Evidence Needed

| Evidence | Minimum useful output |
| --- | --- |
| Live CV pipeline | Video or screenshots showing body skeleton, dumbbell boxes, and UI status. |
| Dumbbell detector | Dataset counts, validation metrics, and controlled failure examples. |
| ESP32/IMU path | Serial JSON samples with acceleration, gyroscope, and orientation fields. |
| Garmin path | Heart-rate sample bridge aligned with frame-level JSONL logs as intensity context. |
| Signal metrics | JSONL showing calibrated arm signals, symmetry, HR, exertion level, and IMU stability. |
| Middleware payload | Example JSONL frame with `body_posture`, `dumbbells`, `arm_signals`, `esp32_glove`, `wearable_watch`, `signal_metrics`, and `signal_log`. |

## Milestones

| Date range | Goal |
| --- | --- |
| June 23-30 | Remove abandoned runtime path, stabilize docs, validate parser/tests. |
| July 1-12 | Improve UI clarity, confirm signal JSONL structure, collect controlled videos. |
| July 13-24 | Bring up ESP32/IMU serial stream and align telemetry with camera frames. |
| July 25-31 | Evaluate Garmin heart-rate bridge, `exertion_level`, asymmetric glove/watch fusion, and begin the minimal web game slice. |
| August 1-7 | Connect the web game to stable `game_control` signals, capture an end-to-end demonstration, and freeze paper figures, tables, commands, and reproducibility notes. |

## Web Game Demonstration

The web prototype should consume `game_control` directly. That payload already contains the movement tokens, analog axes, dumbbell associations, physiology, and IMU orientation needed for a small mapping layer. The implementation should demonstrate a few dependable actions and feedback states, then document the mapping and its limitations.
