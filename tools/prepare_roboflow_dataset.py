"""Prepare a local Roboflow YOLO dataset for Ultralytics training.

The script extracts a Roboflow zip and writes ``data.local.yaml`` with an
absolute ``path`` entry, while preserving Roboflow metadata such as
``names``, ``kpt_shape``, and ``flip_idx``.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Extract a Roboflow YOLO zip and write data.local.yaml.")
    parser.add_argument("--zip", type=Path, required=True, help="Roboflow .zip file.")
    parser.add_argument("--out", type=Path, required=True, help="Dataset output directory under data/datasets.")
    parser.add_argument("--force", action="store_true", help="Delete the output directory before extracting.")
    return parser.parse_args()


def resolve_workspace_path(path: Path) -> Path:
    """Resolve relative paths from the project root."""

    return path if path.is_absolute() else PROJECT_ROOT / path


def extract_zip(zip_path: Path, out_dir: Path, force: bool) -> None:
    """Extract the zip into ``out_dir``."""

    if not zip_path.exists():
        raise FileNotFoundError(f"Dataset zip not found: {zip_path}")
    if force and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_yaml = out_dir / "data.yaml"
    if data_yaml.exists() and not force:
        return
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(out_dir)


def find_data_yaml(out_dir: Path) -> Path:
    """Find the Roboflow ``data.yaml`` file after extraction."""

    direct = out_dir / "data.yaml"
    if direct.exists():
        return direct
    matches = sorted(out_dir.rglob("data.yaml"))
    if not matches:
        raise FileNotFoundError(f"No data.yaml found under {out_dir}")
    return matches[0]


def normalise_split(raw_value: Any, dataset_root: Path) -> Any:
    """Return a split path compatible with an absolute Ultralytics ``path``."""

    if raw_value is None or isinstance(raw_value, list):
        return raw_value
    text = str(raw_value).replace("\\", "/").strip()
    if not text:
        return text
    path_value = Path(text)
    if path_value.is_absolute():
        return path_value.as_posix()

    candidates = [text]
    while candidates[-1].startswith("../"):
        candidates.append(candidates[-1][3:])
    for candidate in candidates:
        if (dataset_root / candidate).exists():
            return Path(candidate).as_posix()
    return Path(candidates[-1]).as_posix()


def write_local_yaml(data_yaml: Path) -> Path:
    """Write ``data.local.yaml`` with an absolute dataset path."""

    dataset_root = data_yaml.parent.resolve()
    raw = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    local: dict[str, Any] = {
        "path": dataset_root.as_posix(),
    }
    for split in ("train", "val", "valid", "test"):
        if split in raw:
            local[split] = normalise_split(raw[split], dataset_root)
    for key in ("names", "nc", "kpt_shape", "flip_idx", "roboflow"):
        if key in raw:
            local[key] = raw[key]

    local_yaml = dataset_root / "data.local.yaml"
    local_yaml.write_text(yaml.safe_dump(local, sort_keys=False), encoding="utf-8")
    return local_yaml


def main() -> int:
    """Extract and normalize the dataset."""

    args = parse_args()
    zip_path = resolve_workspace_path(args.zip)
    out_dir = resolve_workspace_path(args.out)
    extract_zip(zip_path, out_dir, args.force)
    local_yaml = write_local_yaml(find_data_yaml(out_dir))
    print(local_yaml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
