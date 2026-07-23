"""Organize the Iron Quest 3D workspace into predictable research folders.

The script is intentionally conservative:

- By default it runs in dry-run mode and only prints planned moves.
- Use ``--apply`` when the plan looks correct.
- It moves only root-level files by extension, so it will not disturb the
  ``ironquest/`` package, documentation, or prepared dataset internals.
- It migrates legacy root-level ``datasets/<name>`` folders into
  ``data/datasets/<name>`` when they exist.
- Use ``--fix-runs`` to move nested Ultralytics folders such as
  ``runs/detect/runs/detect/<run_name>`` back to ``runs/detect/<run_name>``.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

MEDIA_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
WEIGHT_EXTENSIONS = {".pt", ".onnx", ".engine", ".tflite"}
CONFIG_EXTENSIONS = {".yaml", ".yml"}
ARCHIVE_EXTENSIONS = {".zip"}

TARGETS = {
    "media": PROJECT_ROOT / "data" / "raw_videos",
    "weights": PROJECT_ROOT / "weights",
    "configs": PROJECT_ROOT / "configs",
    "archives": PROJECT_ROOT / "data" / "archives",
    "datasets": PROJECT_ROOT / "data" / "datasets",
}

LEGACY_DATASETS_ROOT = PROJECT_ROOT / "datasets"

NESTED_RUN_PATTERNS = (
    (PROJECT_ROOT / "runs" / "detect" / "runs" / "detect", PROJECT_ROOT / "runs" / "detect"),
    (PROJECT_ROOT / "runs" / "detect" / "runs" / "validate", PROJECT_ROOT / "runs" / "validate"),
    (PROJECT_ROOT / "runs" / "pose" / "runs" / "pose", PROJECT_ROOT / "runs" / "pose"),
    (PROJECT_ROOT / "runs" / "pose" / "runs" / "validate", PROJECT_ROOT / "runs" / "validate"),
)


@dataclass(frozen=True)
class PlannedMove:
    """One filesystem move planned by the organizer."""

    source: Path
    destination: Path
    reason: str


def unique_destination(destination: Path) -> Path:
    """Return a non-conflicting destination path."""

    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def classify_root_file(path: Path) -> tuple[Path, str] | None:
    """Return the destination folder and reason for a root-level file."""

    suffix = path.suffix.lower()
    if suffix in MEDIA_EXTENSIONS:
        return TARGETS["media"], "raw test video"
    if suffix in WEIGHT_EXTENSIONS:
        return TARGETS["weights"], "model weight or export"
    if suffix in CONFIG_EXTENSIONS:
        return TARGETS["configs"], "configuration file"
    if suffix in ARCHIVE_EXTENSIONS:
        return TARGETS["archives"], "dataset/archive file"
    return None


def plan_root_file_moves() -> list[PlannedMove]:
    """Plan moves for clutter files located directly in the project root."""

    moves: list[PlannedMove] = []
    for path in PROJECT_ROOT.iterdir():
        if not path.is_file():
            continue
        classification = classify_root_file(path)
        if classification is None:
            continue
        target_dir, reason = classification
        moves.append(
            PlannedMove(
                source=path,
                destination=unique_destination(target_dir / path.name),
                reason=reason,
            )
        )
    return moves


def plan_nested_run_moves() -> list[PlannedMove]:
    """Plan moves that flatten nested Ultralytics run folders."""

    moves: list[PlannedMove] = []
    for nested_root, target_root in NESTED_RUN_PATTERNS:
        if not nested_root.exists():
            continue
        for run_dir in nested_root.iterdir():
            if not run_dir.is_dir():
                continue
            moves.append(
                PlannedMove(
                    source=run_dir,
                    destination=unique_destination(target_root / run_dir.name),
                    reason="flatten nested Ultralytics run",
                )
            )
    return moves


def plan_legacy_dataset_moves() -> list[PlannedMove]:
    """Plan moves from the old root ``datasets/`` folder into ``data/datasets/``."""

    moves: list[PlannedMove] = []
    if not LEGACY_DATASETS_ROOT.exists():
        return moves
    for dataset_dir in LEGACY_DATASETS_ROOT.iterdir():
        if not dataset_dir.is_dir():
            continue
        moves.append(
            PlannedMove(
                source=dataset_dir,
                destination=unique_destination(TARGETS["datasets"] / dataset_dir.name),
                reason="migrate legacy dataset folder",
            )
        )
    return moves


def apply_moves(moves: list[PlannedMove], apply: bool) -> None:
    """Print or perform a list of planned moves."""

    if not moves:
        print("No moves needed.")
        return

    for move in moves:
        print(f"{move.reason}:")
        print(f"  {move.source}")
        print(f"  -> {move.destination}")
        if apply:
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(move.source), str(move.destination))

    if apply:
        print(f"\nApplied {len(moves)} move(s).")
    else:
        print(f"\nDry run only. Re-run with --apply to move {len(moves)} item(s).")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(description="Organize Iron Quest 3D project files.")
    parser.add_argument("--apply", action="store_true", help="Actually move files. Default is dry-run.")
    parser.add_argument(
        "--fix-runs",
        action="store_true",
        help="Also flatten nested Ultralytics folders such as runs/detect/runs/detect.",
    )
    return parser


def main() -> int:
    """Plan and optionally apply workspace organization moves."""

    args = build_parser().parse_args()
    moves = plan_root_file_moves()
    moves.extend(plan_legacy_dataset_moves())
    if args.fix_runs:
        moves.extend(plan_nested_run_moves())
    apply_moves(moves, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
