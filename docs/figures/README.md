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

**Per-class behaviour**, derived from the raw counts in `confusion_matrix.png`:

| Class | Instances | Predictions | Missed | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dumbbell` | 2,153 | 2,091 | 361 | 0.857 | 0.832 |
| `weight` | 512 | 518 | 19 | 0.952 | 0.963 |
| `other` | 977 | 919 | 153 | 0.897 | 0.843 |

### How to read the background column

The normalized matrix is **column-scaled by true class**, so each column sums to
1. The background column therefore shows how the detector's *unmatched*
detections distribute across classes — not a false-positive rate over background
regions.

There were 403 detections that matched no annotation: 289 `dumbbell` (0.72),
91 `other` (0.23), 23 `weight` (0.06). The 0.72 means "72% of the false positives
were dumbbell predictions". It does **not** mean "72% of background regions are
detected as dumbbells" — that statement would need a denominator this evaluation
does not define, which requires a negative set or dumbbell-free video.

For `dumbbell` specifically: 289 of 2,091 predictions (13.8%) matched nothing,
while 361 of 2,153 annotated instances (16.8%) were missed. The detector fails
slightly more by omission than by spurious detection.

### Threat to validity: split contamination

A SHA-1 audit of all 7,332 images found 7,276 unique digests: 49 duplicate
groups, 24 of which span splits. 24 evaluation images are byte-identical to a
training image (20 of 1,093 validation, 4 of 571 test).

More significantly, grouping filenames by source prefix shows **5,669 of 7,332
images (77.3%) belong to source groups whose frames appear in more than one
split** — these are consecutive frames from continuous video, split randomly.
Evaluation images are therefore frequently near-duplicates of training images.

**Treat these metrics as an upper bound, not as an estimate of generalization.**
They document the model deployed in the system. Any generalization claim, or any
comparison against another detector, needs a source-disjoint re-partition and a
retrain first.

### Training configuration

`yolo26n.pt`, 80 epochs, 640 px, single GPU, seed 0, deterministic, ~3 h 05 min.
Note that the `dumbbell_detection` profile in
`configs/ultralytics_training_config.yaml` now specifies 120 epochs; this
archived run predates that value. `args.yaml` records what was actually used.

| File | Contents |
| --- | --- |
| `results.csv` | Per-epoch metrics. The source of every number above. |
| `results.png` | Loss and metric curves across all 80 epochs. |
| `confusion_matrix.png` | Raw counts per class. |
| `confusion_matrix_normalized.png` | Column-normalized version; the one to cite. |
| `BoxPR_curve.png` | Precision-recall curve per class. |
| `BoxF1_curve.png` | F1 against confidence threshold; useful for justifying the runtime's confidence floors. |
| `args.yaml` | The exact Ultralytics arguments this run used. |
