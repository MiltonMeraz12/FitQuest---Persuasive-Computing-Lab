# Data Capture and Training

The active training scope is body pose and dumbbell/weight detection. Extra keypoint-model training is no longer part of this project.

## Different Problems Require Different Data

| Problem | Active source | Output |
| --- | --- | --- |
| Body posture | YOLO body-pose model | 17 body joints and movement primitives. |
| Dumbbell detection | Local YOLO object dataset | Boxes for `dumbbell` and `weight`. |
| Direct object motion | ESP32/IMU telemetry | Acceleration, angular velocity, and orientation. |
| Physiology context | Garmin Venu 3 bridge | Heart rate and activity/session context. |

## Current Local Dumbbell Model

The active dataset is:

```text
data/datasets/dumbbell_combined_yolo26
```

Check dataset counts and metrics:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest dataset-report
```

Validate a detector:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest validate-object-detector --data .\data\datasets\dumbbell_combined_yolo26\data.local.yaml --model .\runs\detect\dumbbell_combined_yolo26n\weights\best.pt
```

## Capture a Local Session

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --label right_overhead_left_front --source 0 --duration 30 --save-every 5 --video
```

Each capture session creates:

- still frames for labeling;
- optional raw video;
- `motion_payloads.jsonl`;
- `metadata.json`.

Analyze the newest capture after recording:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture
```

Or analyze a specific session:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture .\data\captures\SESSION_FOLDER
```

The analysis writes `capture_analysis.md` inside the session folder. Use it to check ESP32 sample health, IMU movement intensity, pose readiness, and whether the arms were visible enough for camera-derived metrics.

## Recommended Capture Plan

Collect short, repeatable clips:

| Scenario | Purpose |
| --- | --- |
| one dumbbell, left side | Left-side object association. |
| one dumbbell, right side | Right-side object association. |
| two dumbbells, both sides | Bilateral association. |
| one arm overhead, one arm forward | Future game-control primitive. |
| slow curls and holds | Object continuity and UI behavior. |
| camera-lighting variations | Dataset robustness. |
| false object examples | Watches, sleeves, chairs, and dark background objects. |
| ESP32 still / slow tilt / motion burst | IMU threshold calibration and hardware repeatability. |

## Labeling for YOLO Object Detection

Use only the classes needed by the active detector:

- `dumbbell`
- `weight`

Do not add unrelated body-part classes. If a labeling tool requires a hard-negative class, use `other` only for confusing non-dumbbell objects.

## Train With Both Dumbbell Datasets

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-combined-dumbbell-detector --device 0
```

The command uses the `dumbbell_detection` profile from:

```text
configs/ultralytics_training_config.yaml
```

## Train Body Pose

Body-pose training remains optional until the project has a local 17-point dataset.

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-body-pose --device 0
```

## When Not to Train

Do not train when:

- the issue is only UI display;
- the data is not from the real camera setup;
- labels are inconsistent;
- the paper needs analysis evidence more urgently than a new model run.
