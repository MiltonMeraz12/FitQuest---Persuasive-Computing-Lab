# Workspace Architecture and Model Limits

This document defines the active repository structure after the June 23, 2026 scope pivot.

## Current Folder Architecture

| Path | Purpose |
| --- | --- |
| `ironquest/` | Runtime package. |
| `configs/` | Active Ultralytics training profiles. |
| `data/datasets/` | Local datasets. |
| `data/captures/` | Captured local videos, frames, metadata, and JSONL. |
| `firmware/` | ESP32 test firmware. |
| `runs/detect/` | Object-detection training and validation outputs. |
| `runs/pose/` | Body-pose outputs only. |
| `runs/validate/` | Smoke-test and validation artifacts. |
| `tests/` | Regression tests for active runtime behavior. |
| `tools/` | Utility scripts that support active training workflows. |
| `weights/` | Base model weights. |

## Active Model Boundaries

| Model path | Role |
| --- | --- |
| `weights/yolo26n-pose.pt` | Base body-pose model. |
| `runs/detect/dumbbell_combined_yolo26n/weights/best.pt` | Existing dumbbell/weight detector. |

The paper scope uses only body pose and dumbbell/weight boxes on the vision side.

## Cleanup Rule

Generated caches and nested run folders can be cleaned after verification. Keep:

- `.gitkeep` placeholders;
- active dataset YAMLs;
- active detector checkpoints;
- reproducible JSONL examples;
- paper figures and screenshots.

## Current Limits

- Body pose is a 2D estimate from the camera.
- Dumbbell boxes can be missed when the object is small, blurred, or visually merged with the body.
- The object detector needs local lab data for reliable paper claims.
- ESP32/IMU readings require calibration and stable mounting.
- Garmin heart-rate samples may have latency and API/platform constraints.

## Practical Next Steps

1. Validate the cleaned CLI.
2. Run the tests.
3. Capture new dumbbell videos.
4. Confirm ESP32 serial telemetry.
5. Confirm Garmin heart-rate bridge.
6. Save one complete JSONL sample for the paper package.
