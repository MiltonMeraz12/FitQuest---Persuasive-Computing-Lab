# Figures

Evidence figures kept in git for the research paper.

Training and validation output normally lands in `runs/`, which `.gitignore`
excludes because Ultralytics writes hundreds of megabytes of checkpoints and
batch previews there. The small subset that is actual paper evidence is copied
here instead, so it survives independently of one laptop's `runs/` folder.

When a new training run replaces the current detector, re-copy the same files
and update the numbers below in the same commit, so the figures and the claims
never drift apart.

## `dumbbell_detector/`

Dumbbell/weight object detector, run `dumbbell_combined_yolo26n`, trained from
the `dumbbell_detection` profile in `configs/ultralytics_training_config.yaml`.

**Dataset** — `data/datasets/dumbbell_combined_yolo26`, merged from the two
Roboflow dumbbell sets. Classes: `dumbbell`, `weight`, `other`.

| Split | Images |
| --- | --- |
| train | 5668 |
| valid | 1093 |
| test | 571 |

**Final metrics** (epoch 80, from `results.csv`):

| Metric | Value |
| --- | --- |
| precision (B) | 0.919 |
| recall (B) | 0.869 |
| mAP50 (B) | 0.919 |
| mAP50-95 (B) | 0.744 |

**Per-class behavior**, from `confusion_matrix_normalized.png`:

| True class | Correctly predicted |
| --- | --- |
| `weight` | 0.96 |
| `other` | 0.84 |
| `dumbbell` | 0.83 |

The honest caveat for the paper: the background column shows 0.72 of background
regions being predicted as `dumbbell`. The detector finds real dumbbells well,
but it is liberal — it proposes dumbbells in empty regions far more often than
it misses real ones. That is why the runtime does not trust raw boxes: it
applies confidence floors per class, area-ratio bounds, and a wrist/forearm
proximity requirement before a box is allowed to mean "loaded" (see
`ironquest/body_context.py`). Quote the filtered behavior, not the raw mAP,
when describing what the system actually does.

| File | Contents |
| --- | --- |
| `results.csv` | Per-epoch metrics. The source of every number above. |
| `results.png` | Loss and metric curves across all 80 epochs. |
| `confusion_matrix.png` | Raw counts per class. |
| `confusion_matrix_normalized.png` | Column-normalized version; the one to cite. |
| `BoxPR_curve.png` | Precision-recall curve per class. |
| `BoxF1_curve.png` | F1 against confidence threshold; useful for justifying the runtime's confidence floors. |
| `args.yaml` | The exact Ultralytics arguments this run used. |
