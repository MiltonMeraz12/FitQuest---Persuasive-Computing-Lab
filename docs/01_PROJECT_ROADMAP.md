# Project Roadmap

Iron Quest 3D is now a research prototype for a **universal sensor-fusion engine for physical interaction** with a small web-based game as its application layer. The project must finish a reliable normalized signal pipeline and connect it to a simple playable browser prototype before the August 7, 2026 paper deadline.

## Current Goal

Build and document a system that produces synchronized frame-level signals from:

- body-pose tracking;
- dumbbell/weight detection;
- ESP32 + IMU telemetry;
- Garmin Venu 3 heart-rate context;
- dynamically calibrated signals: arm extension, range utilization, reach, height, and bilateral symmetry;
- neutral user-state signals such as exertion level and intensity zone;
- a future-application JSON payload that can also be parsed for longitudinal movement analysis.
- a lightweight web-based game that consumes the normalized game-control payload.

## Scope Decision

| Area | Status | Reason |
| --- | --- | --- |
| Body pose | Active | Required for posture and movement primitives. |
| Dumbbell detector | Active | Required to prove object-aware exercise context. |
| UI monitor | Active | Needed for demos, debugging, and supervisor review. |
| ESP32 + IMU | Active | Adds direct orientation and acceleration evidence. |
| Garmin Venu 3 | Active wearable choice | Practical heart-rate path for the current sprint. |
| Signal logging | Active | Required for paper figures and researcher review. |
| Web-based game slice | Active, intentionally small | Required to demonstrate that the normalized signals can drive an interactive application. |

## Recommended Phases

| Phase | Focus | Output |
| --- | --- | --- |
| 1 | Runtime cleanup | Body+dumbbell+sensors pipeline without abandoned extra model path. |
| 2 | UI improvement | Cleaner monitor with clear status for vision, ESP32, and wearable data. |
| 3 | Local dumbbell evidence | Controlled captures, object metrics, and failure cases. |
| 4 | Dynamic calibration | Session-specific min/max bounds and normalized 0.0-1.0 signals. |
| 5 | ESP32/IMU bring-up | Serial JSON with acceleration, gyroscope, pitch, roll, yaw, and stability index. |
| 6 | Garmin bridge | Heart-rate samples aligned with JSONL frame logs as intensity signals. |
| 7 | Web game vertical slice | Browser client that consumes `game_control` and maps a few movement primitives to visible actions and feedback. |
| 8 | Paper package | Figures, example payloads, game evidence, limitations, and reproducible commands. |

## Near-Term Deliverables

- Passing CLI and test suite after the cleanup.
- JSONL examples containing `body_posture`, `dumbbells`, `arm_signals`, `esp32_glove`, `wearable_watch`, `signal_metrics`, and `signal_log`.
- Updated `docs/05_SENSORS_AND_MATERIALS.md` with the wearable decision.
- Updated UI that clearly separates camera, ESP32, and Garmin readiness.
- A small capture set with the real project dumbbells.
- A simple web-based game prototype with a clear input-to-action mapping, such as movement signals controlling navigation, an attack, a shield, or a target interaction.

## Web Game Scope

The game is a proof-of-concept application, not a full RPG or commercial fitness platform. It should be simple enough to finish and document within the internship while still proving the complete path from physical movement to interaction:

- browser-based interface, preferably using the existing local JSON/JSONL or WebSocket/HTTP bridge;
- two or three mapped actions based on stable signals such as arm extension, height, symmetry, stability, or a movement event;
- visible feedback such as a character/target state, score, progress, or success indicator;
- no requirement for multiplayer, complex world design, large content systems, or production-grade backend services.

## Questions for Supervisor

1. Is Garmin Venu 3 physically available for repeated tests?
2. Which dumbbells will be used in the lab videos?
3. Should the ESP32/IMU be mounted on a dumbbell or tested first as a free-moving fixture?
4. What exact paper venue or format should guide the final report structure?
5. Which hand should wear the ESP32 glove and which hand should wear the Garmin watch during pilot sessions?
