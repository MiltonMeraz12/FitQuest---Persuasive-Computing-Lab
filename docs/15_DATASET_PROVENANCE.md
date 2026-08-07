# Dataset Provenance and Redistribution

This file must travel with the dataset. It records what the training data is,
where it came from, and the two things that limit what anyone can conclude from
it or do with it.

## What the dataset is

`dumbbell_combined_yolo26` — 7,332 annotated images, three classes (`dumbbell`,
`weight`, `other`), YOLO box format, assembled by merging two Roboflow exports
with `ironquest prepare-combined-dumbbell-data`.

| Split | Images |
| --- | --- |
| `train` | 5,668 |
| `valid` | 1,093 |
| `test` | 571 |

The merge prefixes every filename with its source: `d1_` or `d2_`. That prefix
is the only surviving record of which export an image came from.

| Prefix | Images | Filename pattern |
| --- | --- | --- |
| `d1_` | 2,918 | `frame_NNN_jpg.rf.<hash>.jpg` — extracted video frames |
| `d2_` | 4,414 | `<16-hex-id>_jpg.rf.<hash>.jpg` |

## Provenance gap — read before redistributing

**The specific Roboflow datasets these came from, and their licenses, are not
recorded anywhere in this repository.** The merge command consumed two ZIP
files passed on the command line; neither the filenames nor the source URLs
were captured in the code, the documentation, or the training run metadata.

Two Roboflow ZIPs remain on the original author's machine, both CC BY 4.0:

- `szarmander/dumbbell-detector` v5 — 134 images
- `johnsonfitness/Dumbbell-Bench` v2 — 8,383 images

**Neither is the source.** Comparing filename stems (the portion before
Roboflow's per-export `.rf.<hash>` suffix, which is stable across exports)
gives zero matches against either export, for either prefix, and the naming
conventions differ entirely from both. They are unrelated downloads.

The consequence is that the redistribution terms of these 7,332 images are
**unverified**. Most Roboflow Universe datasets are CC BY 4.0, which permits
redistribution with attribution, but not all are, and "probably CC BY" is not a
license. Before publishing this data anywhere public:

1. Recover the two source datasets from the Roboflow account download history.
2. Record their URLs, authors, versions, and licenses in this file.
3. Provide the attribution each license requires.

Sharing privately with collaborators for research use is a materially different
act from public redistribution, and is the lower-risk path while the above is
outstanding.

## Validity gap — read before quoting the metrics

The reported detector figures (mAP@50 = 0.919) come from this dataset's random
partition, and a random partition is the wrong one here:

- 5,669 of 7,332 images (77.3 %) belong to source groups — near-duplicate
  frames from the same underlying capture — that span more than one split.
- 24 evaluation images are byte-identical to training images.

Frames from one recording therefore appear on both sides of the split, so the
model is partly evaluated on what it memorized. **Treat the metrics as an upper
bound, not as evidence of generalization.** A source-disjoint re-partition and
retraining would be needed before these numbers support a claim about unseen
data. See Section 11 of the final report for the full analysis.

## Not included

Body-pose training data. The pose model is the unmodified `yolo26n-pose.pt`
released by Ultralytics, trained on COCO keypoints; nothing in this project
retrained it.
