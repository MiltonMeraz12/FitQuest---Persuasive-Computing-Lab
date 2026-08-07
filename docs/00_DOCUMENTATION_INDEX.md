# Iron Quest 3D Documentation Index

Iron Quest 3D (FitQuest) is a sensor-fusion middleware prototype for physical interaction, plus a small browser game that proves the complete sensor-to-action path. The scope was set by the June 23, 2026 pivot and the research-paper deadline of August 7, 2026.

New to the project? Read [01_PROJECT_ROADMAP](01_PROJECT_ROADMAP.md), then [02_SYSTEM_ARCHITECTURE](02_SYSTEM_ARCHITECTURE.md), then run it with [03_RUN_AND_DEMO](03_RUN_AND_DEMO.md).

## Orientation

| Document | Purpose |
| --- | --- |
| [01_PROJECT_ROADMAP.md](01_PROJECT_ROADMAP.md) | Scope, deadline, and deliverables. |
| [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md) | Runtime layers, repository layout, frame-level data flow, and known limits. |
| [03_RUN_AND_DEMO.md](03_RUN_AND_DEMO.md) | How to start the system and what a healthy run looks like. |

## Reference

| Document | Purpose |
| --- | --- |
| [04_COMMAND_REFERENCE.md](04_COMMAND_REFERENCE.md) | Every CLI command and its useful options. |
| [05_CODE_REFERENCE.md](05_CODE_REFERENCE.md) | What each runtime module is responsible for. |
| [06_SENSOR_FUSION_PAYLOAD.md](06_SENSOR_FUSION_PAYLOAD.md) | The `game_control` JSON contract clients consume. |
| [07_WEB_GAME_IMPLEMENTATION.md](07_WEB_GAME_IMPLEMENTATION.md) | Browser client, local gateway, exercise validation, and the 3D avatar. |

## Hardware

| Document | Purpose |
| --- | --- |
| [08_SENSORS_AND_MATERIALS.md](08_SENSORS_AND_MATERIALS.md) | The sensor set, why each one is present, and what it contributes. |
| [09_ESP32_IMU_HARDWARE.md](09_ESP32_IMU_HARDWARE.md) | ESP32-S3 + BNO08x wiring, bring-up, firmware, Wi-Fi transport, and the glove case. |
| [10_GARMIN_VENU3_BRIDGE.md](10_GARMIN_VENU3_BRIDGE.md) | Garmin Venu 3 watch app, Connect IQ and BLE bridges, sideloading, and troubleshooting. |

## Data and Paper

| Document | Purpose |
| --- | --- |
| [11_DATA_CAPTURE_AND_TRAINING.md](11_DATA_CAPTURE_AND_TRAINING.md) | Capturing sessions, labeling, and the YOLO training profiles. |
| [12_OFFLINE_AND_PRESENTATION.md](12_OFFLINE_AND_PRESENTATION.md) | Fallbacks and guidance for live demos. |
| [13_SENSOR_FUSION_PAPER_PLAN.md](13_SENSOR_FUSION_PAPER_PLAN.md) | Paper milestones and the evidence each one needs. |
| [14_PROJECT_IMPROVEMENT_BACKLOG.md](14_PROJECT_IMPROVEMENT_BACKLOG.md) | Prioritized engineering backlog. |
| [15_DATASET_PROVENANCE.md](15_DATASET_PROVENANCE.md) | Where the training data came from, its unresolved licensing, and why its metrics are an upper bound. |
| [figures/](figures/README.md) | Committed evidence figures: detector metrics, confusion matrix, curves, and capture-session summaries. |

## Supervisor Reports

Dated records of what happened each week, kept in [`reports/`](reports/):

| Report | Covers |
| --- | --- |
| [2026-06-23_project_pivot.md](reports/2026-06-23_project_pivot.md) | The scope pivot and its reasoning. |
| [2026-06-29_weekly_report.md](reports/2026-06-29_weekly_report.md) | Hardware readiness and the integration plan. |
| [2026-07-06_weekly_report.md](reports/2026-07-06_weekly_report.md) | ESP32/IMU validation and next integration steps. |
| [2026-07-13_weekly_report.md](reports/2026-07-13_weekly_report.md) | ESP32/IMU runtime improvements and Garmin Venu 3 integration. |
| [2026-07-13_teams_update.md](reports/2026-07-13_teams_update.md) | Short Teams-format version of the same week. |
| [2026-07-20_weekly_report.md](reports/2026-07-20_weekly_report.md) | Case model, ESP32/Garmin consolidation, confirmed web-game scope. |
| [2026-07-20_vp_visit_talk.md](reports/2026-07-20_vp_visit_talk.md) | Introduction and practice notes for the VPRI lab visit. |
| [2026-07-27_weekly_report.md](reports/2026-07-27_weekly_report.md) | Two real-hardware sessions, the rep-counting fix, the exercise library, and case revision 2. |

## Scope Boundaries

The active vision system is **body pose plus dumbbell/weight detection**, nothing else. Sensor fusion combines that with ESP32/IMU glove telemetry, Garmin wearable context, dynamic per-user calibration, normalized motion signals, and frame-level JSONL export.

Out of scope: complex game development, multiplayer, production platform features, rule-based gym rep counting, and any additional vision model.
