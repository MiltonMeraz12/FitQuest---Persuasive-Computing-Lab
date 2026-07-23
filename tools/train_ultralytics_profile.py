"""Train an Ultralytics model from an Iron Quest profile YAML.

This launcher guarantees that every augmentation and hyperparameter in
``configs/ultralytics_training_config.yaml`` is passed to ``YOLO.train``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "ultralytics_training_config.yaml"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Train a YOLO model from a named Iron Quest profile.")
    parser.add_argument("--profile", required=True, help="Profile name from the config, or 'all'.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--data", type=Path, help="Override profile dataset YAML.")
    parser.add_argument("--model", help="Override profile base model or checkpoint.")
    parser.add_argument("--device", help="Training device, for example 0, cpu, or cuda:0.")
    parser.add_argument("--project", type=Path, help="Override output project directory.")
    parser.add_argument("--name", help="Override run name.")
    parser.add_argument("--epochs", type=int, help="Override epoch count.")
    parser.add_argument("--imgsz", type=int, help="Override image size.")
    parser.add_argument("--batch", type=int, help="Override batch size.")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved train kwargs without training.")
    return parser.parse_args()


def workspace_path(value: Any) -> Any:
    """Resolve local path-like values from the project root."""

    if value is None:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path.as_posix()
    return (PROJECT_ROOT / path).resolve().as_posix()


def model_reference(value: Any) -> str:
    """Resolve local checkpoint paths while preserving official model names."""

    text = str(value)
    path = Path(text)
    if path.suffix == ".pt":
        candidates = [path] if path.is_absolute() else [PROJECT_ROOT / path, PROJECT_ROOT / "weights" / path.name]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve().as_posix()
    return text


def dataset_reference(value: Any) -> str:
    """Resolve local dataset YAMLs while preserving Ultralytics dataset names."""

    text = str(value)
    path = Path(text)
    if path.is_absolute():
        return path.as_posix()
    local_path = PROJECT_ROOT / path
    if len(path.parts) > 1 or local_path.exists():
        return local_path.resolve().as_posix()
    return text


def load_profile(config_path: Path, profile_name: str) -> dict[str, Any]:
    """Load one profile from the training config."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        raise KeyError(f"Unknown profile {profile_name!r}. Available: {', '.join(sorted(profiles))}")
    return dict(profiles[profile_name])


def build_train_kwargs(args: argparse.Namespace, profile_name: str) -> tuple[str, dict[str, Any]]:
    """Return the model reference and kwargs passed to ``YOLO.train``."""

    profile = load_profile(args.config, profile_name)
    profile.pop("mode", None)
    for key in list(profile):
        if key.startswith("ironquest_"):
            profile.pop(key)
    model_ref = model_reference(args.model or profile.pop("model"))
    if args.data is not None:
        profile["data"] = args.data
    if args.project is not None:
        profile["project"] = args.project
    for key in ("name", "device", "epochs", "imgsz", "batch"):
        value = getattr(args, key)
        if value is not None:
            profile[key] = value

    if "data" in profile:
        profile["data"] = dataset_reference(profile["data"])
    if "project" in profile:
        profile["project"] = workspace_path(profile["project"])
    return model_ref, profile


def profile_names(config_path: Path) -> list[str]:
    """Return profile names in YAML order."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return list((config.get("profiles") or {}).keys())


def main() -> int:
    """Train the configured profile."""

    args = parse_args()
    available_profiles = profile_names(args.config)
    selected_profiles = available_profiles if args.profile == "all" else [args.profile]
    unknown = [name for name in selected_profiles if name not in available_profiles]
    if unknown:
        raise KeyError(f"Unknown profile(s): {', '.join(unknown)}. Available: {', '.join(available_profiles)}")

    resolved_runs = []
    for profile_name in selected_profiles:
        model_ref, train_kwargs = build_train_kwargs(args, profile_name)
        resolved = {"profile": profile_name, "model": model_ref, "train_kwargs": train_kwargs}
        resolved_runs.append(resolved)
        print(json.dumps(resolved, indent=2))
        if not args.dry_run:
            model = YOLO(model_ref)
            model.train(**train_kwargs)
    if args.dry_run and len(resolved_runs) > 1:
        print(json.dumps({"profiles": resolved_runs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
