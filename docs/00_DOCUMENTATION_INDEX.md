# Iron Quest 3D Documentation Index

This documentation reflects the June 23, 2026 project pivot. The project is now a universal sensor-fusion middleware prototype for physical interaction and a research-paper deliverable due no later than August 7, 2026.

## Recommended Reading Order

| Document | Purpose |
| --- | --- |
| [01_PROJECT_ROADMAP.md](01_PROJECT_ROADMAP.md) | Defines the new paper-oriented scope, deadline, and deliverables. |
| [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md) | Describes the active runtime layers and frame-level data flow. |
| [03_RUN_AND_DEMO.md](03_RUN_AND_DEMO.md) | Shows how to run the detector, UI, Garmin sample, and ESP32 sample. |
| [04_DATA_CAPTURE_AND_TRAINING.md](04_DATA_CAPTURE_AND_TRAINING.md) | Covers dumbbell/body data capture and active YOLO training only. |
| [05_SENSORS_AND_MATERIALS.md](05_SENSORS_AND_MATERIALS.md) | Defines the active Garmin Venu 3 plus ESP32/IMU sensor path. |
| [06_GAME_PAYLOAD_AND_CONTROLS.md](06_GAME_PAYLOAD_AND_CONTROLS.md) | Defines the sensor-fusion JSON payload and the scope of the small web-game integration. |
| [07_COMMAND_REFERENCE.md](07_COMMAND_REFERENCE.md) | Lists active commands and removed commands. |
| [08_CODE_REFERENCE.md](08_CODE_REFERENCE.md) | Maps the current code modules to their responsibilities. |
| [09_OFFLINE_AND_PRESENTATION.md](09_OFFLINE_AND_PRESENTATION.md) | Gives fallback and presentation guidance. |
| [10_WEEKLY_PROGRESS_UPDATE.md](10_WEEKLY_PROGRESS_UPDATE.md) | Short supervisor update after the scope pivot. |
| [11_PROJECT_IMPROVEMENT_BACKLOG.md](11_PROJECT_IMPROVEMENT_BACKLOG.md) | Prioritized engineering backlog. |
| [12_SENSOR_FUSION_PAPER_PLAN.md](12_SENSOR_FUSION_PAPER_PLAN.md) | Paper-oriented milestone plan and expected evidence. |
| [13_WORKSPACE_ARCHITECTURE_AND_MODEL_LIMITS.md](13_WORKSPACE_ARCHITECTURE_AND_MODEL_LIMITS.md) | Repo layout, active model boundaries, and known limits. |
| [14_PROJECT_PIVOT_REPORT_2026_06_23.md](14_PROJECT_PIVOT_REPORT_2026_06_23.md) | Detailed report explaining the pivot and next milestones. |
| [15_WEEKLY_DETAILED_REPORT_2026_06_29.md](15_WEEKLY_DETAILED_REPORT_2026_06_29.md) | Weekly supervisor report covering hardware readiness and this week's integration plan. |
| [16_ESP32_IMU_WIRELESS_NEXT_STEP.md](16_ESP32_IMU_WIRELESS_NEXT_STEP.md) | Defines the next ESP32/IMU step from USB serial toward Wi-Fi telemetry and a future portable case. |
| [17_WEEKLY_DETAILED_REPORT_2026_07_06.md](17_WEEKLY_DETAILED_REPORT_2026_07_06.md) | Weekly supervisor report covering ESP32/IMU validation and the next full-system integration steps. |
| [18_GARMIN_VENU3_BRIDGE_PLAN.md](18_GARMIN_VENU3_BRIDGE_PLAN.md) | Defines the Garmin Venu 3 Connect IQ bridge, BLE fallback, and wearable JSON path. |
| [19_WEEKLY_DETAILED_REPORT_2026_07_13.md](19_WEEKLY_DETAILED_REPORT_2026_07_13.md) | Weekly supervisor report covering ESP32/IMU runtime improvements and Garmin Venu 3 integration. |
| [20_GARMIN_CONNECTIQ_TROUBLESHOOTING.md](20_GARMIN_CONNECTIQ_TROUBLESHOOTING.md) | Step-by-step Garmin Connect IQ sideload and telemetry troubleshooting. |
| [23_WEB_GAME_IMPLEMENTATION.md](23_WEB_GAME_IMPLEMENTATION.md) | Browser client, local gateway, demo/replay/live modes, and web-game commands. |
| [ESP32_PLANNING.md](ESP32_PLANNING.md) | ESP32-S3 and IMU bring-up plan. |
| [TRAINING_PIPELINE.md](TRAINING_PIPELINE.md) | Active YOLO body-pose and dumbbell training profiles. |

## What Was Removed

- The standalone extra keypoint-analysis runtime module.
- The extra keypoint-training and validation CLI commands.
- The previous specialized analysis test and helper tool for that abandoned path.
- Historical docs centered on that abandoned model path.

The active vision system is body pose plus dumbbell/weight detection. Sensor fusion is handled through Garmin-style context data, ESP32/IMU glove telemetry, dynamic calibration, normalized motion signals, and frame-level JSONL export.
