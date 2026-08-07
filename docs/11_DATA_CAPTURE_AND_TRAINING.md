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

## Training Profiles

Every training hyperparameter and augmentation lives in one file:

```text
configs/ultralytics_training_config.yaml
```

It defines two profiles, and the CLI reads them directly, so there is no second launcher to keep in sync:

| Profile | Task | Purpose |
| --- | --- | --- |
| `body_pose` | pose | 17-point body-pose model. |
| `dumbbell_detection` | detect | Object detector for dumbbells and weights. |

Body pose and dumbbell detection stay separate because their outputs differ: COCO body pose has 17 joints, dumbbells are object boxes.

## Train With Both Dumbbell Datasets

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-combined-dumbbell-detector --device 0
```

This uses the `dumbbell_detection` profile. The active dataset is `data/datasets/dumbbell_combined_yolo26/data.local.yaml`.

Before redistributing that dataset or quoting its metrics, read [Dataset Provenance and Redistribution](15_DATASET_PROVENANCE.md). Its source licenses are unrecorded, and its random split overlaps across near-duplicate frames.

## Train Body Pose

Body-pose training remains optional until the project has a local 17-point dataset. The default path uses the base weights at `weights/yolo26n-pose.pt`.

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-body-pose --device 0
```

## Runtime Weight Resolution

The live runtime does not need a `--model` flag. It prefers, in order:

1. the weights named by `IRONQUEST_POSE_WEIGHTS` / `IRONQUEST_DUMBBELL_WEIGHTS`;
2. the configured default run checkpoint;
3. the newest matching `best.pt` under `runs/`;
4. the base weights in `weights/`.

No extra vision model outside the active paper scope is loaded.

## Evidence to Save

Ultralytics writes everything to `runs/`, which is gitignored because a run is
hundreds of megabytes of checkpoints and batch previews. The small subset that
is actual paper evidence gets copied into [`docs/figures/`](figures/README.md)
and committed, so it does not depend on one laptop surviving.

For each training run, copy over:

- `results.csv` (the source of every metric you quote);
- `results.png` (loss and metric curves);
- `confusion_matrix_normalized.png`;
- `BoxPR_curve.png` and `BoxF1_curve.png`;
- `args.yaml` (the exact arguments that run used);

and update the numbers in `docs/figures/README.md` in the same commit, so the
figures and the claims cannot drift apart.

Also keep, per capture session: dataset counts, the `capture_analysis.md`
summary, and JSONL payloads from the same scenario. The session summaries in
[`docs/figures/capture_sessions/`](figures/capture_sessions/) are the distilled
text form of captures whose raw video and frames were not worth keeping.

## When Not to Train

Do not train when:

- the issue is only UI display;
- the data is not from the real camera setup;
- labels are inconsistent;
- the paper needs analysis evidence more urgently than a new model run.
