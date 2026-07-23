# Iron Quest 3D Training Pipeline

The active training pipeline has two profiles:

1. `body_pose`: 17-point body-pose model.
2. `dumbbell_detection`: object detector for dumbbells and weights.

The config source of truth is:

```text
configs/ultralytics_training_config.yaml
```

## Body Pose

The default body-pose path uses the base YOLO pose weights:

```text
weights/yolo26n-pose.pt
```

Train or refit only when a valid 17-point body-pose dataset is available:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-body-pose --device 0
```

## Dumbbell Detection

The active dataset is:

```text
data/datasets/dumbbell_combined_yolo26/data.local.yaml
```

Train:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest train-combined-dumbbell-detector --device 0
```

Validate:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest validate-object-detector --data .\data\datasets\dumbbell_combined_yolo26\data.local.yaml --model .\runs\detect\dumbbell_combined_yolo26n\weights\best.pt
```

## Train From Profile

Use the profile launcher for exact config reproduction:

```powershell
.\ironquest_env\Scripts\python.exe tools\train_ultralytics_profile.py --profile dumbbell_detection --dry-run
```

```powershell
.\ironquest_env\Scripts\python.exe tools\train_ultralytics_profile.py --profile body_pose --dry-run
```

## Runtime Defaults

The full runtime prefers:

- configured or latest body-pose weights;
- configured or latest dumbbell-detector weights;
- no extra vision model outside the active paper scope.

## Evidence to Save

- dataset counts;
- `results.csv`;
- validation metrics;
- confusion matrix or representative plots;
- short success/failure screenshots;
- JSONL payloads from the same scenario.
