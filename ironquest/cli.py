"""Command-line interface for the Iron Quest 3D prototype."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import yaml
from ultralytics import YOLO

from .body_context import ObjectTemporalTracker, build_body_context
from .capture_analysis import analyze_capture, print_capture_summary, resolve_capture_jsonl, write_capture_report
from .game_controls import EventDebouncer, build_game_control_payload
from .keypoints import PoseSmoother, extract_primary_pose
from .motion_analysis import MotionAnalyzer
from .movement import MovementClassifier
from .sensors import (
    ESP32AutoBridge,
    ESP32SerialBridge,
    ESP32UdpBridge,
    WearableFileBridge,
    build_empty_esp32_payload,
    build_empty_wearable_payload,
    list_serial_ports,
)
from .web_gateway import WebGateway
from .ui import (
    WINDOW_NAME,
    compose_camera_detection_preview,
    compose_detector_preview,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"
WEIGHTS_ROOT = PROJECT_ROOT / "weights"
DEFAULT_DETECT_PROJECT = RUNS_ROOT / "detect"
DEFAULT_POSE_PROJECT = RUNS_ROOT / "pose"
DEFAULT_VALIDATE_PROJECT = RUNS_ROOT / "validate"
LIVE_INSTANCE_LOCK_PATH = DEFAULT_VALIDATE_PROJECT / "ironquest_live.lock"

# "full", "demo", and "run" are aliases of one subparser (see build_parser)
# and are meant to share the same live-session behavior: the one-instance
# lock and the live ESP32/UI defaults. run_ironquest.bat always invokes
# "run", so this only matters for someone invoking the CLI directly.
LIVE_COMMAND_ALIASES = frozenset({"full", "demo", "run"})

DEFAULT_DUMBBELL_ZIP = Path(os.getenv("IRONQUEST_DUMBBELL_ZIP", "docs/Dumbbell-detetion-new.v23i.yolo26.zip"))
DEFAULT_DUMBBELL_ZIP_2 = Path(os.getenv("IRONQUEST_DUMBBELL_ZIP_2", "docs/Dumbbell_2.4.v8i.yolo26.zip"))
DEFAULT_COMBINED_DUMBBELL_OUT = Path("data/datasets/dumbbell_combined_yolo26")
DEFAULT_POSE_WEIGHTS = Path(os.getenv("IRONQUEST_POSE_WEIGHTS", "runs/pose/body_pose_yolo26n_improved/weights/best.pt"))
BASE_POSE_WEIGHTS = Path("weights/yolo26n-pose.pt")
BASE_DUMBBELL_WEIGHTS = Path("runs/detect/dumbbell_combined_yolo26n/weights/best.pt")
DEFAULT_DUMBBELL_WEIGHTS = Path(os.getenv("IRONQUEST_DUMBBELL_WEIGHTS", "runs/detect/dumbbell_combined_yolo26n/weights/best.pt"))
DEFAULT_TRAINING_CONFIG = PROJECT_ROOT / "configs" / "ultralytics_training_config.yaml"
DEFAULT_WEARABLE_LIVE_JSON = DEFAULT_VALIDATE_PROJECT / "wearable_live.json"
DEFAULT_GARMIN_BRIDGE_SCRIPT = PROJECT_ROOT / "tools" / "garmin_ble_heart_rate_bridge.py"
DEFAULT_GARMIN_BRIDGE_LOG = DEFAULT_VALIDATE_PROJECT / "garmin_ble_bridge.log"
DEFAULT_GARMIN_CONNECTIQ_BRIDGE_SCRIPT = PROJECT_ROOT / "tools" / "garmin_connectiq_http_bridge.py"
DEFAULT_GARMIN_CONNECTIQ_BRIDGE_LOG = DEFAULT_VALIDATE_PROJECT / "garmin_connectiq_bridge.log"
DEFAULT_FITQUEST_WORKER_PULL_SCRIPT = PROJECT_ROOT / "tools" / "fitquest_worker_pull.py"
DEFAULT_FITQUEST_WORKER_PULL_LOG = DEFAULT_VALIDATE_PROJECT / "fitquest_worker_pull.log"
ESP32_TRANSPORT_CHOICES = ("none", "serial", "udp", "auto")

DETECT_DEFAULTS = {
    "model": "yolo26n-pose.pt",
    "source": "0",
    "imgsz": 640,
    "conf": 0.20,
    "pose_track": False,
    "pose_smoothing": 0.45,
    "pose_hold_frames": 2,
    "object_model": None,
    "object_imgsz": 640,
    "object_conf": 0.20,
    "object_frame_stride": 2,
    "object_track_hold_frames": 4,
    "object_track_smoothing": 0.55,
    "object_track_max_center_distance": 160.0,
    "dumbbell_conf": 0.30,
    "weight_conf": 0.50,
    "min_object_area_ratio": 0.0015,
    "max_object_area_ratio": 0.12,
    "require_object_body_match": True,
    "pose_joint_conf": 0.25,
    "max_wrist_distance": 90.0,
    "max_forearm_distance": 70.0,
    "analysis_window": 12,
    "calibration_seconds": 7.0,
    "esp32_side": "right",
    "esp32_transport": "auto",
    "wearable_side": "left",
    "esp32_port": None,
    "esp32_baud": 115200,
    "esp32_udp_host": "0.0.0.0",
    "esp32_udp_port": 4210,
    "wearable_json": None,
    "wearable_stale_seconds": 10.0,
    "jsonl": None,
    "print_json": False,
    "no_show": False,
    "display_width": 1100,
    "panel_width": 520,
    "ui_detail": "simple",
    "mirror": True,
    "fullscreen": True,
    "device": "auto",
    "max_frames": None,
    "auto_object_model": False,
    "garmin_bridge": False,
    "garmin_connectiq_bridge": False,
    "garmin_connectiq_host": "0.0.0.0",
    "garmin_connectiq_port": 8765,
    "fitquest_worker_url": None,
}


def preferred_existing_weights(*candidates: Path) -> Path:
    """Return the first configured weights path that exists, preserving relative paths."""

    for candidate in candidates:
        if candidate.is_absolute() and candidate.exists():
            return candidate
        if not candidate.is_absolute() and (PROJECT_ROOT / candidate).exists():
            return candidate
    return candidates[0]


def latest_run_weights(project_dir: Path, run_prefix: str) -> Path | None:
    """Return the newest ``best.pt`` from runs whose folder starts with a prefix."""

    if not project_dir.exists():
        return None
    candidates = [
        path
        for path in project_dir.glob(f"{run_prefix}*/weights/best.pt")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def configured_or_latest_weights(
    env_var: str,
    default_path: Path,
    project_dir: Path,
    run_prefix: str,
    *fallbacks: Path,
) -> Path:
    """Prefer an env override, then the latest matching run, then fallbacks."""

    override = os.getenv(env_var)
    if override:
        return preferred_existing_weights(Path(override), *fallbacks)
    latest = latest_run_weights(project_dir, run_prefix)
    if latest is not None:
        return latest
    return preferred_existing_weights(default_path, *fallbacks)


def fill_detection_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Fill missing detection options for compact commands such as ``demo``."""

    pose_weights = configured_or_latest_weights(
        "IRONQUEST_POSE_WEIGHTS",
        DEFAULT_POSE_WEIGHTS,
        DEFAULT_POSE_PROJECT,
        "body_pose_yolo26n_improved",
        BASE_POSE_WEIGHTS,
        Path("yolo26n-pose.pt"),
    )
    dumbbell_weights = configured_or_latest_weights(
        "IRONQUEST_DUMBBELL_WEIGHTS",
        DEFAULT_DUMBBELL_WEIGHTS,
        DEFAULT_DETECT_PROJECT,
        "dumbbell_combined_yolo26n_improved",
        BASE_DUMBBELL_WEIGHTS,
    )

    mode_presets = {
        "vision": {
            "model": pose_weights,
            "object_model": None,
            "pose_track": False,
            "auto_object_model": False,
        },
        "dumbbells": {
            "model": pose_weights,
            "object_model": dumbbell_weights,
            "pose_track": False,
            "auto_object_model": False,
        },
        "full": {
            "model": pose_weights,
            "object_model": dumbbell_weights,
            "pose_track": False,
            "mirror": True,
            "auto_object_model": False,
        },
    }

    for key, value in DETECT_DEFAULTS.items():
        if not hasattr(args, key):
            setattr(args, key, value)

    selected_mode = getattr(args, "mode", None)
    explicit_args = set(getattr(args, "_explicit_detection_args", set()))
    if selected_mode:
        for key, value in mode_presets[selected_mode].items():
            if key not in explicit_args:
                setattr(args, key, value)

    if getattr(args, "auto_object_model", False) and args.object_model is None:
        args.object_model = find_latest_best_weights(RUNS_ROOT)
        if args.object_model:
            print(f"Using object model: {args.object_model}")
        else:
            print("No trained object model found. Running pose/motion detection only.")
    return args


def env_flag(name: str, default: bool = False) -> bool:
    """Read a yes/no environment flag with Windows-friendly values."""

    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def apply_live_command_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Apply the one-command live runtime defaults.

    ``python -m ironquest run`` is the project-facing command for daily use. It
    keeps the advanced flags available, but defaults to the real demo stack:
    camera + pose + dumbbells + auto ESP32/IMU transport + visible telemetry UI.
    ``full``/``demo`` are aliases of the same command and get the same defaults.
    """

    if getattr(args, "mode", None) is None:
        args.mode = "full"
    args.auto_object_model = True

    if getattr(args, "command", None) not in LIVE_COMMAND_ALIASES:
        return args

    explicit_args = set(getattr(args, "_explicit_detection_args", set()))
    if "esp32_transport" not in explicit_args:
        args.esp32_transport = "auto"
    if "ui_detail" not in explicit_args:
        args.ui_detail = "debug"
    if "wearable_stale_seconds" not in explicit_args:
        args.wearable_stale_seconds = 5.0
    if "wearable_json" not in explicit_args and getattr(args, "wearable_json", None) is None:
        configured_wearable = os.getenv("IRONQUEST_WEARABLE_JSON")
        if configured_wearable:
            args.wearable_json = Path(configured_wearable)
        else:
            args.wearable_json = DEFAULT_WEARABLE_LIVE_JSON
    if "fitquest_worker_url" not in explicit_args:
        args.fitquest_worker_url = os.getenv("FITQUEST_WORKER_URL")
    if "garmin_connectiq_bridge" not in explicit_args:
        args.garmin_connectiq_bridge = env_flag(
            "IRONQUEST_GARMIN_CONNECTIQ_BRIDGE",
            default=not bool(args.fitquest_worker_url),
        )
    if "garmin_bridge" not in explicit_args:
        # Connect IQ already carries the watch motion/HR payload. BLE remains
        # available as an explicit fallback, but must not race the shared file.
        args.garmin_bridge = env_flag(
            "IRONQUEST_GARMIN_BRIDGE",
            default=not args.garmin_connectiq_bridge and not bool(args.fitquest_worker_url),
        )
    if "garmin_connectiq_host" not in explicit_args:
        args.garmin_connectiq_host = os.getenv(
            "IRONQUEST_GARMIN_CONNECTIQ_HOST",
            DETECT_DEFAULTS["garmin_connectiq_host"],
        )
    if "garmin_connectiq_port" not in explicit_args:
        args.garmin_connectiq_port = int(
            os.getenv("IRONQUEST_GARMIN_CONNECTIQ_PORT", str(DETECT_DEFAULTS["garmin_connectiq_port"]))
        )

    return args


def resolve_project_path(project: str | Path) -> str:
    """Return an absolute Ultralytics project path rooted at this repository.

    Ultralytics treats relative ``project`` paths as relative to the current
    process directory. If a command is launched from inside ``runs/detect`` or
    from a notebook with a different working directory, relative projects can
    become nested as ``runs/detect/runs/detect``. Resolving here keeps all
    training and validation outputs under the repository's top-level
    ``runs/`` directory.
    """

    project_path = Path(project)
    if not project_path.is_absolute():
        project_path = PROJECT_ROOT / project_path
    return str(project_path)


def resolve_model_reference(model: str | Path) -> str:
    """Resolve local model files while preserving Ultralytics model names.

    Base models may live in the project root during early experiments and in
    ``weights/`` after the workspace is organized. If neither local file exists,
    the original value is returned so Ultralytics can handle official model
    names such as ``yolo26n.pt``.
    """

    model_path = Path(model)
    local_candidates = []
    if model_path.is_absolute():
        local_candidates.append(model_path)
    else:
        local_candidates.extend(
            [
                Path.cwd() / model_path,
                PROJECT_ROOT / model_path,
                WEIGHTS_ROOT / model_path.name,
            ]
        )
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return str(model)


def resolve_dataset_reference(data: str | Path) -> str:
    """Resolve local dataset YAMLs while preserving official Ultralytics dataset names."""

    text = str(data)
    data_path = Path(text)
    if data_path.is_absolute():
        return data_path.as_posix()
    local_path = PROJECT_ROOT / data_path
    if len(data_path.parts) > 1 or local_path.exists():
        return local_path.resolve().as_posix()
    return text


def resolve_inference_device(requested: str | None = "auto") -> str:
    """Pick the fastest available inference backend for Ultralytics.

    The detector defaults to ``auto``: NVIDIA CUDA first, Apple MPS second, CPU
    last.  Users can still force a backend with ``--device cpu``, ``--device
    cuda:0``, ``--device 0``, or ``--device mps``.
    """

    if requested and requested != "auto":
        return "cuda:0" if str(requested).isdigit() else str(requested)
    try:
        import torch
    except ImportError:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda:0"
    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return "mps"
    return "cpu"


def prepare_yolo_model(model: YOLO | None, device: str) -> None:
    """Move a YOLO model to the selected device when the backend supports it."""

    if model is None or device == "cpu":
        return
    try:
        model.to(device)
    except Exception as exc:
        print(f"Warning: could not pre-load YOLO model on {device}; Ultralytics will fall back as needed. {exc}")


def detect_screen_size() -> tuple[int, int] | None:
    """Return the primary monitor size for fullscreen letterboxing."""

    env_width = os.getenv("IRONQUEST_SCREEN_WIDTH")
    env_height = os.getenv("IRONQUEST_SCREEN_HEIGHT")
    if env_width and env_height:
        try:
            return int(env_width), int(env_height)
        except ValueError:
            pass

    if os.name == "nt":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        size = (int(root.winfo_screenwidth()), int(root.winfo_screenheight()))
        root.destroy()
        if size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        return None
    return None


def load_training_profile(profile_name: str, config_path: Path = DEFAULT_TRAINING_CONFIG) -> dict[str, object]:
    """Load one profile from the project training configuration."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles))
        raise KeyError(f"Unknown training profile {profile_name!r}. Available: {available}")
    profile = dict(profiles[profile_name])
    profile.pop("mode", None)
    for key in list(profile):
        if key.startswith("ironquest_"):
            profile.pop(key)
    return profile


def build_profile_train_kwargs(
    profile_name: str,
    args: argparse.Namespace,
    override_keys: tuple[str, ...] = ("data", "project", "name", "device", "epochs", "imgsz", "batch"),
) -> tuple[str, dict[str, object]]:
    """Return the resolved model reference and kwargs for a configured profile."""

    profile = load_training_profile(profile_name)
    model_ref = getattr(args, "model", None) or profile.pop("model")
    for key in override_keys:
        value = getattr(args, key, None)
        if value is not None:
            profile[key] = value

    if "data" in profile:
        profile["data"] = resolve_dataset_reference(profile["data"])
    if "project" in profile:
        profile["project"] = resolve_project_path(profile["project"])
    return resolve_model_reference(model_ref), profile


def find_latest_best_weights(root: Path) -> Path | None:
    """Return the newest Ultralytics ``best.pt`` file under a root folder."""

    if not root.exists():
        return None
    candidates = [path for path in root.rglob("best.pt") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_weights_path(model_path: str | Path) -> Path:
    """Return an existing weights path or find the matching run checkpoint."""

    model_path = Path(model_path)
    if model_path.exists():
        return model_path

    organized_model = WEIGHTS_ROOT / model_path.name
    if not model_path.is_absolute() and organized_model.exists():
        return organized_model

    run_name = model_path.parent.parent.name if model_path.parent.name == "weights" else model_path.stem
    weight_name = model_path.name
    candidates = [
        path
        for path in RUNS_ROOT.rglob(weight_name)
        if path.is_file() and path.parent.name == "weights" and path.parent.parent.name == run_name
    ]
    if candidates:
        selected = max(candidates, key=lambda path: path.stat().st_mtime)
        print(f"Model path not found: {model_path}")
        print(f"Using matching checkpoint: {selected}")
        return selected

    latest = find_latest_best_weights(RUNS_ROOT)
    hint = f"\nNewest available best.pt: {latest}" if latest else "\nNo best.pt checkpoint was found under runs/."
    raise FileNotFoundError(f"Model weights not found: {model_path}{hint}")


def parse_source(source: str):
    """Return an OpenCV-friendly source.

    OpenCV expects integer ``0`` for the default webcam, but video files and
    stream URLs must stay as strings.
    """

    if source.isdigit():
        return int(source)
    return source


def should_run_object_frame(args: argparse.Namespace, frame_index: int) -> bool:
    """Return whether this frame should pay for dumbbell/weight YOLO inference."""

    stride = max(1, int(getattr(args, "object_frame_stride", 1) or 1))
    return frame_index % stride == 0 or not hasattr(args, "_cached_object_result")


def build_tracker(args: argparse.Namespace):
    """Create the lightweight middleware tracker."""

    return MovementClassifier()


def build_esp32_bridge(args: argparse.Namespace):
    """Create the configured ESP32 telemetry transport."""

    transport = str(getattr(args, "esp32_transport", "auto") or "auto").lower()
    if transport == "none":
        return None
    if transport == "auto":
        return ESP32AutoBridge(
            serial_port=getattr(args, "esp32_port", None) or "auto",
            baud=getattr(args, "esp32_baud", 115200),
            udp_host=getattr(args, "esp32_udp_host", DETECT_DEFAULTS["esp32_udp_host"]),
            udp_port=getattr(args, "esp32_udp_port", DETECT_DEFAULTS["esp32_udp_port"]),
        )
    if transport == "udp":
        return ESP32UdpBridge(
            host=getattr(args, "esp32_udp_host", DETECT_DEFAULTS["esp32_udp_host"]),
            udp_port=getattr(args, "esp32_udp_port", DETECT_DEFAULTS["esp32_udp_port"]),
        )
    return ESP32SerialBridge(getattr(args, "esp32_port", None), getattr(args, "esp32_baud", 115200))


def start_garmin_bridge_process(args: argparse.Namespace):
    """Start the Garmin BLE writer as a background helper for the one-command run path."""

    if not getattr(args, "garmin_bridge", False):
        return None, None
    if not DEFAULT_GARMIN_BRIDGE_SCRIPT.exists():
        print(f"Garmin BLE bridge script not found: {DEFAULT_GARMIN_BRIDGE_SCRIPT}")
        return None, None

    wearable_path = Path(getattr(args, "wearable_json", None) or DEFAULT_WEARABLE_LIVE_JSON)
    if not wearable_path.is_absolute():
        wearable_path = PROJECT_ROOT / wearable_path

    DEFAULT_VALIDATE_PROJECT.mkdir(parents=True, exist_ok=True)
    log_handle = DEFAULT_GARMIN_BRIDGE_LOG.open("a", encoding="utf-8")
    command = [
        sys.executable,
        str(DEFAULT_GARMIN_BRIDGE_SCRIPT),
        "--out",
        str(wearable_path),
        "--name",
        os.getenv("IRONQUEST_GARMIN_NAME", "Venu"),
        "--scan-seconds",
        os.getenv("IRONQUEST_GARMIN_SCAN_SECONDS", "10"),
    ]
    if os.getenv("IRONQUEST_GARMIN_RESTING_BPM"):
        command.extend(["--resting-bpm", os.environ["IRONQUEST_GARMIN_RESTING_BPM"]])
    if os.getenv("IRONQUEST_GARMIN_MAX_BPM"):
        command.extend(["--max-bpm", os.environ["IRONQUEST_GARMIN_MAX_BPM"]])

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    except OSError as exc:
        log_handle.close()
        print(f"Could not start Garmin BLE bridge: {exc}")
        return None, None

    print(f"Garmin BLE bridge started. Log: {DEFAULT_GARMIN_BRIDGE_LOG}")
    return process, log_handle


def tcp_port_is_listening(host: str, port: int) -> bool:
    """Return True when a local helper is already listening on the requested port."""

    connect_host = "127.0.0.1" if host in {"", "0.0.0.0", "::"} else host
    try:
        with socket.create_connection((connect_host, port), timeout=0.25):
            return True
    except OSError:
        return False


def start_garmin_connectiq_bridge_process(args: argparse.Namespace):
    """Start the Connect IQ HTTP receiver used by the richer Garmin watch app."""

    if not getattr(args, "garmin_connectiq_bridge", False):
        return None, None
    if not DEFAULT_GARMIN_CONNECTIQ_BRIDGE_SCRIPT.exists():
        print(f"Garmin Connect IQ bridge script not found: {DEFAULT_GARMIN_CONNECTIQ_BRIDGE_SCRIPT}")
        return None, None

    host = str(getattr(args, "garmin_connectiq_host", DETECT_DEFAULTS["garmin_connectiq_host"]) or "0.0.0.0")
    port = int(getattr(args, "garmin_connectiq_port", DETECT_DEFAULTS["garmin_connectiq_port"]) or 8765)
    if tcp_port_is_listening(host, port):
        print(f"Garmin Connect IQ bridge already listening on http://{host}:{port}/garmin")
        return None, None

    wearable_path = Path(getattr(args, "wearable_json", None) or DEFAULT_WEARABLE_LIVE_JSON)
    if not wearable_path.is_absolute():
        wearable_path = PROJECT_ROOT / wearable_path

    DEFAULT_VALIDATE_PROJECT.mkdir(parents=True, exist_ok=True)
    log_handle = DEFAULT_GARMIN_CONNECTIQ_BRIDGE_LOG.open("a", encoding="utf-8")
    command = [
        sys.executable,
        str(DEFAULT_GARMIN_CONNECTIQ_BRIDGE_SCRIPT),
        "--host",
        host,
        "--port",
        str(port),
        "--out",
        str(wearable_path),
        "--print-samples",
    ]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    except OSError as exc:
        log_handle.close()
        print(f"Could not start Garmin Connect IQ bridge: {exc}")
        return None, None

    print(f"Garmin Connect IQ bridge started. Log: {DEFAULT_GARMIN_CONNECTIQ_BRIDGE_LOG}")
    return process, log_handle


def start_fitquest_worker_pull_process(args: argparse.Namespace):
    """Start the free FitQuest Worker puller when a Worker URL is configured."""

    worker_url = str(getattr(args, "fitquest_worker_url", "") or "").strip()
    if not worker_url or not DEFAULT_FITQUEST_WORKER_PULL_SCRIPT.exists():
        return None, None

    wearable_path = Path(getattr(args, "wearable_json", None) or DEFAULT_WEARABLE_LIVE_JSON)
    if not wearable_path.is_absolute():
        wearable_path = PROJECT_ROOT / wearable_path

    DEFAULT_VALIDATE_PROJECT.mkdir(parents=True, exist_ok=True)
    log_handle = DEFAULT_FITQUEST_WORKER_PULL_LOG.open("a", encoding="utf-8")
    command = [
        sys.executable,
        str(DEFAULT_FITQUEST_WORKER_PULL_SCRIPT),
        "--url",
        worker_url,
        "--out",
        str(wearable_path),
        "--interval",
        os.getenv("FITQUEST_WORKER_POLL_SECONDS", "2.0"),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    except OSError as exc:
        log_handle.close()
        print(f"Could not start FitQuest Worker puller: {exc}")
        return None, None

    print(f"FitQuest Worker puller started: {worker_url}")
    return process, log_handle


def stop_background_process(process: subprocess.Popen | None, name: str) -> None:
    """Terminate a background helper without blocking shutdown."""

    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
    except OSError as exc:
        print(f"Could not stop {name}: {exc}")


class LiveInstanceLock:
    """Keep one live camera/telemetry runtime per workspace."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        """Acquire a process-released lock without relying on stale PID files."""

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open("a+b")
            self.handle.seek(0)
            self.handle.write(b"0")
            self.handle.flush()
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - exercised on non-Windows deployments
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError):
            if self.handle is not None:
                try:
                    self.handle.close()
                except OSError:
                    pass
            self.handle = None
            return False
        return True

    def release(self) -> None:
        """Release the lock and close its file handle."""

        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised on non-Windows deployments
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except (OSError, ImportError):
            pass
        finally:
            self.handle.close()
            self.handle = None


def build_signal_log_record(payload: dict) -> dict:
    """Return a flat, Pandas-friendly universal signal record for one frame."""

    motion = payload.get("motion_analysis", {})
    signal_metrics = motion.get("signal_metrics", {}) if isinstance(motion, dict) else {}
    sides = signal_metrics.get("sides", {}) if isinstance(signal_metrics, dict) else {}
    bilateral = signal_metrics.get("bilateral", {}) if isinstance(signal_metrics, dict) else {}
    calibration = signal_metrics.get("calibration", {}) if isinstance(signal_metrics, dict) else {}
    game_control = payload.get("game_control", {})
    user_state = game_control.get("user_state", {}) if isinstance(game_control, dict) else {}
    esp32 = game_control.get("esp32_glove", {}) if isinstance(game_control, dict) else {}
    wearable = game_control.get("wearable_watch", {}) if isinstance(game_control, dict) else {}
    orientation = esp32.get("orientation_euler_deg") if isinstance(esp32.get("orientation_euler_deg"), dict) else {}
    events = game_control.get("events", []) if isinstance(game_control, dict) else []
    left = sides.get("left", {}) if isinstance(sides, dict) else {}
    right = sides.get("right", {}) if isinstance(sides, dict) else {}

    return {
        "schema_version": "sensor-fusion-signal-frame-v1",
        "logged_at_unix": round(time.time(), 3),
        "motion_status": motion.get("status"),
        "calibration_state": calibration.get("state"),
        "calibration_elapsed_seconds": calibration.get("elapsed_seconds"),
        "symmetry_score": bilateral.get("symmetry_score"),
        "range_symmetry_score": bilateral.get("range_symmetry_score"),
        "speed_symmetry_score": bilateral.get("speed_symmetry_score"),
        "left_visible": left.get("visible"),
        "left_elbow_angle_deg": left.get("elbow_angle_deg"),
        "left_angle_range_deg": left.get("angle_range_deg"),
        "left_arm_extension": left.get("arm_extension"),
        "left_height_signal": left.get("height_signal"),
        "left_reach_signal": left.get("reach_signal"),
        "left_range_utilization": left.get("range_utilization"),
        "left_movement_speed": left.get("movement_speed"),
        "left_loaded": left.get("loaded"),
        "right_visible": right.get("visible"),
        "right_elbow_angle_deg": right.get("elbow_angle_deg"),
        "right_angle_range_deg": right.get("angle_range_deg"),
        "right_arm_extension": right.get("arm_extension"),
        "right_height_signal": right.get("height_signal"),
        "right_reach_signal": right.get("reach_signal"),
        "right_range_utilization": right.get("range_utilization"),
        "right_movement_speed": right.get("movement_speed"),
        "right_loaded": right.get("loaded"),
        "heart_rate_bpm": user_state.get("heart_rate_bpm"),
        "exertion_level": user_state.get("exertion_level"),
        "intensity_zone": user_state.get("intensity_zone"),
        "wearable_status": wearable.get("status"),
        "wearable_device": wearable.get("device"),
        "wearable_side": wearable.get("mounted_side"),
        "wearable_contact": wearable.get("heart_rate_contact"),
        "wearable_battery_percent": wearable.get("battery"),
        "wearable_motion_state": wearable.get("watch_motion_state"),
        "wearable_motion_delta_mg": wearable.get("watch_motion_delta_mg"),
        "wearable_acceleration_magnitude_mg": wearable.get("acceleration_magnitude_mg"),
        "wearable_acceleration_unit": wearable.get("acceleration_unit"),
        "wearable_sequence": wearable.get("sequence"),
        "wearable_sent_count": wearable.get("sent_count"),
        "wearable_sample_interval_ms": wearable.get("sample_interval_ms"),
        "wearable_last_http_code": wearable.get("last_http_code"),
        "event_tokens": "|".join(str(event) for event in events),
        "esp32_status": esp32.get("status"),
        "esp32_transport": esp32.get("transport"),
        "esp32_transport_summary": esp32.get("transport_summary"),
        "esp32_connected_transports": "|".join(str(item) for item in esp32.get("connected_transports", [])),
        "esp32_remote": esp32.get("remote"),
        "esp32_side": esp32.get("mounted_side"),
        "imu_pitch_deg": orientation.get("pitch"),
        "imu_roll_deg": orientation.get("roll"),
        "imu_yaw_deg": orientation.get("yaw"),
        "imu_sample_interval_ms": esp32.get("sample_interval_ms"),
        "imu_sample_rate_hz": esp32.get("sample_rate_hz"),
        "imu_motion_delta_mps2": esp32.get("motion_delta_mps2"),
        "imu_angular_delta_dps": esp32.get("angular_delta_dps"),
        "imu_orientation_delta_deg": esp32.get("orientation_delta_deg"),
        "imu_motion_intensity": esp32.get("motion_intensity"),
        "imu_rotation_intensity": esp32.get("rotation_intensity"),
        "imu_motion_state": esp32.get("motion_state"),
        "stability_index": esp32.get("stability_index"),
    }


def analyze_frame(
    frame,
    pose_model,
    object_model,
    tracker,
    motion_analyzer: MotionAnalyzer,
    pose_smoother: PoseSmoother | None,
    object_tracker: ObjectTemporalTracker | None,
    esp32_bridge: ESP32AutoBridge | ESP32SerialBridge | ESP32UdpBridge | None,
    wearable_bridge: WearableFileBridge | None,
    args: argparse.Namespace,
    frame_index: int = 0,
    exercise_debouncer: EventDebouncer | None = None,
) -> tuple[dict, object, object | None]:
    """Run all analysis layers for one frame.

    This is the central data path:
    camera frame -> YOLO pose -> optional dumbbell detector -> middleware pose state
    -> open-ended motion primitives -> optional smartwatch JSON -> optional
    ESP32 serial data -> game-control payload.
    """

    device = getattr(args, "inference_device", "cpu")
    use_half_precision = str(device).lower().startswith("cuda")
    if getattr(args, "pose_track", False):
        results = pose_model.track(
            frame,
            imgsz=args.imgsz,
            conf=args.conf,
            persist=True,
            device=device,
            half=use_half_precision,
            verbose=False,
        )
    else:
        results = pose_model(
            frame,
            imgsz=args.imgsz,
            conf=args.conf,
            device=device,
            half=use_half_precision,
            verbose=False,
        )
    result = results[0]
    object_result = None
    if object_model is not None:
        if should_run_object_frame(args, frame_index):
            object_results = object_model(
                frame,
                imgsz=args.object_imgsz,
                conf=args.object_conf,
                device=device,
                half=use_half_precision,
                verbose=False,
            )
            object_result = object_results[0]
            args._cached_object_result = object_result
        else:
            object_result = getattr(args, "_cached_object_result", None)

    raw_pose = extract_primary_pose(result)
    pose = pose_smoother.update(raw_pose) if pose_smoother is not None else raw_pose
    payload = tracker.update_from_pose(pose)

    body_payload = build_body_context(
        pose,
        object_result=object_result,
        min_confidence=args.pose_joint_conf,
        max_wrist_distance=args.max_wrist_distance,
        max_forearm_distance=args.max_forearm_distance,
        image_shape=frame.shape,
        min_object_area_ratio=args.min_object_area_ratio,
        max_object_area_ratio=args.max_object_area_ratio,
        label_confidences={"dumbbell": args.dumbbell_conf, "weight": args.weight_conf},
        require_body_match=args.require_object_body_match,
        object_tracker=object_tracker,
    )
    payload.update(body_payload)

    motion_payload = motion_analyzer.update(pose, body_payload)
    wearable_payload = wearable_bridge.poll() if wearable_bridge is not None else build_empty_wearable_payload()
    esp32_payload = esp32_bridge.poll() if esp32_bridge is not None else build_empty_esp32_payload()
    payload["motion_analysis"] = motion_payload
    payload["wearable"] = wearable_payload
    payload["esp32"] = esp32_payload
    payload["pose_filter"] = {
        "status": "enabled" if pose_smoother is not None else "disabled",
        "smoothing": getattr(args, "pose_smoothing", 0.0),
        "hold_frames": getattr(args, "pose_hold_frames", 0),
    }
    payload["game_control"] = build_game_control_payload(
        motion_payload,
        payload,
        esp32_payload,
        wearable_payload,
        esp32_side=getattr(args, "esp32_side", DETECT_DEFAULTS["esp32_side"]),
        wearable_side=getattr(args, "wearable_side", DETECT_DEFAULTS["wearable_side"]),
        debouncer=exercise_debouncer,
    )
    payload["signal_log"] = build_signal_log_record(payload)
    return payload, pose, object_result


@dataclass(frozen=True)
class PipelineFrame:
    """One analyzed frame emitted by the live CV pipeline."""

    index: int
    frame: object
    payload: dict
    pose: object
    object_result: object | None


class PipelineRunner:
    """Own the live detector pipeline lifecycle for preview and capture modes."""

    def __init__(self, args: argparse.Namespace, jsonl_path: Path | None = None):
        """Store command arguments and optional JSONL output path."""

        self.args = fill_detection_defaults(args)
        self.jsonl_path = jsonl_path
        self.pose_model = None
        self.object_model = None
        self.cap = None
        self.tracker = None
        self.motion_analyzer: MotionAnalyzer | None = None
        self.pose_smoother: PoseSmoother | None = None
        self.object_tracker: ObjectTemporalTracker | None = None
        self.exercise_debouncer: EventDebouncer | None = None
        self.esp32_bridge: ESP32AutoBridge | ESP32SerialBridge | ESP32UdpBridge | None = None
        self.wearable_bridge: WearableFileBridge | None = None
        self.garmin_connectiq_bridge_process: subprocess.Popen | None = None
        self.garmin_connectiq_bridge_log = None
        self.fitquest_worker_pull_process: subprocess.Popen | None = None
        self.fitquest_worker_pull_log = None
        self.garmin_bridge_process: subprocess.Popen | None = None
        self.garmin_bridge_log = None
        self.jsonl_handle = None
        self.live_instance_lock: LiveInstanceLock | None = None
        self.frame_count = 0
        self.fps = 0.0
        self.last_frame_time = time.perf_counter()
        self.ui_debug_enabled = self.args.ui_detail == "debug"
        self.display_size: tuple[int, int] | None = None
        self.web_gateway: WebGateway | None = None

    def __enter__(self) -> "PipelineRunner":
        """Open models, camera/video, sensor bridges, optional JSONL, and window."""

        if getattr(self.args, "command", None) in LIVE_COMMAND_ALIASES:
            self.live_instance_lock = LiveInstanceLock(LIVE_INSTANCE_LOCK_PATH)
            if not self.live_instance_lock.acquire():
                raise RuntimeError(
                    "Another IronQuest live session is already running. "
                    "Close the existing run before starting a new one."
                )

        self.args.inference_device = resolve_inference_device(getattr(self.args, "device", "auto"))
        print(f"Using inference device: {self.args.inference_device}")

        self.pose_model = YOLO(resolve_model_reference(self.args.model))
        self.object_model = YOLO(resolve_weights_path(self.args.object_model)) if self.args.object_model else None
        prepare_yolo_model(self.pose_model, self.args.inference_device)
        prepare_yolo_model(self.object_model, self.args.inference_device)
        self.cap = cv2.VideoCapture(parse_source(self.args.source))
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open source: {self.args.source}")

        self.tracker = build_tracker(self.args)
        self.motion_analyzer = MotionAnalyzer(
            window=self.args.analysis_window,
            min_confidence=self.args.pose_joint_conf,
            calibration_seconds=self.args.calibration_seconds,
        )
        self.exercise_debouncer = EventDebouncer()
        self.pose_smoother = PoseSmoother(
            alpha=self.args.pose_smoothing,
            hold_frames=self.args.pose_hold_frames,
            min_confidence=min(self.args.pose_joint_conf, self.args.conf),
        )
        self.object_tracker = (
            ObjectTemporalTracker(
                max_stale_frames=self.args.object_track_hold_frames,
                smoothing=self.args.object_track_smoothing,
                max_center_distance=self.args.object_track_max_center_distance,
            )
            if self.object_model is not None and self.args.object_track_hold_frames > 0
            else None
        )
        self.esp32_bridge = build_esp32_bridge(self.args)
        self.wearable_bridge = WearableFileBridge(self.args.wearable_json, self.args.wearable_stale_seconds)

        if self.jsonl_path:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            self.jsonl_handle = self.jsonl_path.open("w", encoding="utf-8")

        if not self.args.no_show:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            if getattr(self.args, "fullscreen", True):
                self.display_size = detect_screen_size()
                if self.display_size is None:
                    fallback_width = max(1, int(self.args.display_width or 1100))
                    self.display_size = (fallback_width, max(1, int(fallback_width * 0.75)))
                cv2.resizeWindow(WINDOW_NAME, self.display_size[0], self.display_size[1])
                cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            elif self.args.display_width and self.args.display_width > 0:
                cv2.resizeWindow(
                    WINDOW_NAME,
                    self.args.display_width,
                    max(1, int(self.args.display_width * 0.75)),
                )
        self.garmin_connectiq_bridge_process, self.garmin_connectiq_bridge_log = start_garmin_connectiq_bridge_process(
            self.args
        )
        self.fitquest_worker_pull_process, self.fitquest_worker_pull_log = start_fitquest_worker_pull_process(self.args)
        self.garmin_bridge_process, self.garmin_bridge_log = start_garmin_bridge_process(self.args)
        if getattr(self.args, "web", False):
            self.web_gateway = WebGateway(
                host=str(getattr(self.args, "web_host", "127.0.0.1")),
                port=int(getattr(self.args, "web_port", 8787)),
            )
            self.web_gateway.start()
            print(f"FitQuest web client: {self.web_gateway.url}")
            try:
                webbrowser.open(self.web_gateway.url, new=2)
            except Exception as exc:  # pragma: no cover - browser availability is environment-specific
                print(f"Could not open the FitQuest web client automatically: {exc}")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        """Release all resources held by the runner."""

        if self.cap is not None:
            self.cap.release()
        if self.esp32_bridge is not None:
            self.esp32_bridge.close()
        stop_background_process(self.garmin_connectiq_bridge_process, "Garmin Connect IQ bridge")
        if self.garmin_connectiq_bridge_log:
            self.garmin_connectiq_bridge_log.close()
        stop_background_process(self.fitquest_worker_pull_process, "FitQuest Worker puller")
        if self.fitquest_worker_pull_log:
            self.fitquest_worker_pull_log.close()
        stop_background_process(self.garmin_bridge_process, "Garmin BLE bridge")
        if self.garmin_bridge_log:
            self.garmin_bridge_log.close()
        if self.web_gateway is not None:
            self.web_gateway.close()
        if self.jsonl_handle:
            self.jsonl_handle.close()
        if not self.args.no_show:
            cv2.destroyAllWindows()
        if self.live_instance_lock is not None:
            self.live_instance_lock.release()

    def frames(self):
        """Yield analyzed frames until the source ends or ``--max-frames`` is reached."""

        assert self.cap is not None
        while self.cap.isOpened():
            success, frame = self.cap.read()
            if not success:
                break
            payload, pose, object_result = self.process_frame(frame)
            yield PipelineFrame(
                index=self.frame_count,
                frame=frame,
                payload=payload,
                pose=pose,
                object_result=object_result,
            )
            self.frame_count += 1
            if self.args.max_frames is not None and self.frame_count >= self.args.max_frames:
                break

    def process_frame(self, frame) -> tuple[dict, object, object | None]:
        """Run analysis and attach runtime FPS for one frame."""

        assert self.pose_model is not None
        assert self.tracker is not None
        assert self.motion_analyzer is not None
        self._apply_pending_controls()
        payload, pose, object_result = analyze_frame(
            frame,
            self.pose_model,
            self.object_model,
            self.tracker,
            self.motion_analyzer,
            self.pose_smoother,
            self.object_tracker,
            self.esp32_bridge,
            self.wearable_bridge,
            self.args,
            frame_index=self.frame_count,
            exercise_debouncer=self.exercise_debouncer,
        )
        now = time.perf_counter()
        instant_fps = 1.0 / max(now - self.last_frame_time, 1e-6)
        self.fps = instant_fps if self.frame_count == 0 else (0.9 * self.fps + 0.1 * instant_fps)
        self.last_frame_time = now
        payload["runtime"] = {"fps": round(self.fps, 1)}
        if isinstance(payload.get("signal_log"), dict):
            payload["signal_log"]["frame_index"] = self.frame_count
            payload["signal_log"]["fps"] = round(self.fps, 1)
        if self.web_gateway is not None:
            web_preview = compose_camera_detection_preview(
                frame,
                payload,
                pose,
                object_result,
                display_width=min(960, max(640, int(getattr(self.args, "display_width", 960) or 960))),
                mirror=self.args.mirror,
                min_pose_confidence=self.args.pose_joint_conf,
                min_object_area_ratio=self.args.min_object_area_ratio,
                display_size=None,
            )
            self.web_gateway.publish(payload, web_preview)
        return payload, pose, object_result

    def _apply_pending_controls(self) -> None:
        """Apply browser lifecycle requests at a safe point in the CV loop."""

        if self.web_gateway is None:
            return
        for action in self.web_gateway.poll_controls():
            if action in {"calibrate", "reset_session"}:
                self._reset_runtime_state()

    def _reset_runtime_state(self) -> None:
        """Reset temporal inference state without restarting camera or sensors."""

        if self.motion_analyzer is not None:
            self.motion_analyzer.reset()
        if self.exercise_debouncer is not None:
            self.exercise_debouncer.reset()
        if self.pose_smoother is not None:
            self.pose_smoother.reset()
        if self.object_tracker is not None:
            self.object_tracker.reset()
        if self.tracker is not None and hasattr(self.tracker, "reset"):
            self.tracker.reset()
        if hasattr(self.args, "_cached_object_result"):
            delattr(self.args, "_cached_object_result")
        self.last_frame_time = time.perf_counter()

    def write_json(self, payload: dict) -> None:
        """Write one JSON payload to the configured JSONL handle."""

        if self.jsonl_handle:
            self.jsonl_handle.write(json.dumps(payload) + "\n")

    def maybe_print_json(self, payload: dict) -> None:
        """Print a payload when the command requested terminal JSON."""

        if self.args.print_json:
            print(json.dumps(payload))

    def show_preview(self, frame, payload: dict, pose: object, object_result: object | None) -> bool:
        """Render the OpenCV preview and return ``True`` when the user quits."""

        if self.args.no_show:
            return False

        display_frame = compose_detector_preview(
            frame,
            payload,
            pose,
            object_result,
            self.args.display_width,
            self.args.panel_width,
            ui_detail="debug" if self.ui_debug_enabled else "clean",
            mirror=self.args.mirror,
            min_pose_confidence=self.args.pose_joint_conf,
            min_object_area_ratio=self.args.min_object_area_ratio,
            display_size=self.display_size,
        )
        cv2.imshow(WINDOW_NAME, display_frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("d"), ord("D")):
            self.ui_debug_enabled = not self.ui_debug_enabled
            return False
        return bool(key in (ord("q"), ord("Q")))


def command_detect(args: argparse.Namespace) -> int:
    """Run the camera/video movement detector."""

    args = fill_detection_defaults(args)
    with PipelineRunner(args, jsonl_path=getattr(args, "jsonl", None)) as runner:
        for result in runner.frames():
            runner.write_json(result.payload)
            runner.maybe_print_json(result.payload)
            if runner.show_preview(result.frame, result.payload, result.pose, result.object_result):
                break

    return 0


def command_demo(args: argparse.Namespace) -> int:
    """Run the recommended low-clutter detector setup with short command options."""

    args = apply_live_command_defaults(args)
    return command_detect(args)


def command_export_pose(args: argparse.Namespace) -> int:
    """Export the YOLO26 pose model for browser/edge experiments."""

    model = YOLO(resolve_model_reference(args.model))
    output = model.export(
        format=args.format,
        imgsz=args.imgsz,
        dynamic=args.dynamic,
        half=args.half,
        int8=args.int8,
        simplify=True,
    )
    print(output)
    return 0


def _read_yolo_names(data_yaml: Path) -> list[str]:
    """Read class names from a YOLO ``data.yaml`` file."""

    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    names = data.get("names", [])
    if isinstance(names, dict):
        return [str(names[index]) for index in sorted(names, key=lambda value: int(value))]
    return [str(name) for name in names]


def _extract_zip_dataset(zip_path: Path, out_dir: Path) -> Path:
    """Extract one YOLO zip dataset and return its dataset root directory."""

    if not zip_path.exists():
        raise FileNotFoundError(f"Dataset zip not found: {zip_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    data_yaml = out_dir / "data.yaml"
    if not data_yaml.exists():
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(out_dir)
    if data_yaml.exists():
        return out_dir
    matches = list(out_dir.rglob("data.yaml"))
    if not matches:
        raise FileNotFoundError(f"No data.yaml found after extracting {zip_path}")
    return matches[0].parent


def _safe_rebuild_dir(path: Path) -> None:
    """Remove a generated directory only when it is inside this workspace."""

    if not path.exists():
        return
    workspace = Path.cwd().resolve()
    target = path.resolve()
    if workspace not in (target, *target.parents):
        raise ValueError(f"Refusing to rebuild outside workspace: {target}")
    shutil.rmtree(target)


def prepare_combined_dumbbell_dataset(zip_paths: list[Path], out_dir: Path, rebuild: bool = False) -> Path:
    """Merge multiple YOLO dumbbell datasets into one Ultralytics dataset.

    The two current Roboflow datasets use compatible box format but different
    second class names: the first has ``weight`` and the second has ``other``.
    The combined dataset keeps all three names: ``dumbbell``, ``weight``, and
    ``other``. The live detector still uses only ``dumbbell`` and ``weight`` as
    load-bearing objects.
    """

    if rebuild:
        _safe_rebuild_dir(out_dir)
    data_yaml = out_dir / "data.local.yaml"
    if data_yaml.exists() and not rebuild:
        return data_yaml

    extracted_root = out_dir / "_sources"
    combined_names = ["dumbbell", "weight", "other"]
    for split in ("train", "valid", "test"):
        (out_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (out_dir / split / "labels").mkdir(parents=True, exist_ok=True)

    for dataset_index, zip_path in enumerate(zip_paths, start=1):
        source_root = _extract_zip_dataset(zip_path, extracted_root / f"dataset_{dataset_index}")
        source_names = _read_yolo_names(source_root / "data.yaml")
        class_map = {old_index: combined_names.index(name) for old_index, name in enumerate(source_names) if name in combined_names}
        missing = [name for name in source_names if name not in combined_names]
        if missing:
            raise ValueError(f"Unsupported class names in {zip_path}: {missing}")

        prefix = f"d{dataset_index}_"
        for split in ("train", "valid", "test"):
            source_images = source_root / split / "images"
            source_labels = source_root / split / "labels"
            if not source_images.exists():
                continue
            for image_path in source_images.iterdir():
                if not image_path.is_file():
                    continue
                target_image = out_dir / split / "images" / f"{prefix}{image_path.name}"
                shutil.copy2(image_path, target_image)
                label_path = source_labels / f"{image_path.stem}.txt"
                target_label = out_dir / split / "labels" / f"{prefix}{image_path.stem}.txt"
                if not label_path.exists():
                    target_label.write_text("", encoding="utf-8")
                    continue
                converted_lines: list[str] = []
                for raw_line in label_path.read_text(encoding="utf-8").splitlines():
                    parts = raw_line.strip().split()
                    if len(parts) < 5:
                        continue
                    old_class = int(float(parts[0]))
                    if old_class not in class_map:
                        continue
                    converted_lines.append(" ".join([str(class_map[old_class]), *parts[1:5]]))
                target_label.write_text("\n".join(converted_lines) + ("\n" if converted_lines else ""), encoding="utf-8")

    data_yaml.write_text(
        "\n".join(
            [
                f"path: {out_dir.resolve().as_posix()}",
                "train: train/images",
                "val: valid/images",
                "test: test/images",
                "",
                "names:",
                "  0: dumbbell",
                "  1: weight",
                "  2: other",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return data_yaml


def command_prepare_combined_dumbbell_data(args: argparse.Namespace) -> int:
    """Prepare the merged dumbbell detector dataset without training."""

    data_yaml = prepare_combined_dumbbell_dataset(args.zip, args.out, rebuild=args.rebuild)
    print(f"Combined dataset ready: {data_yaml}")
    return 0


def count_dataset_split(dataset_dir: Path, split: str) -> tuple[int, int]:
    """Count images and labels in one YOLO dataset split."""

    image_dir = dataset_dir / split / "images"
    label_dir = dataset_dir / split / "labels"
    image_count = len([path for path in image_dir.glob("*") if path.is_file()]) if image_dir.exists() else 0
    label_count = len([path for path in label_dir.glob("*.txt") if path.is_file()]) if label_dir.exists() else 0
    return image_count, label_count


def find_latest_training_run(runs_root: Path) -> Path | None:
    """Find the newest Ultralytics run that contains a results.csv file."""

    candidates = [path.parent for path in runs_root.rglob("results.csv")]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_last_metrics(run_dir: Path) -> dict[str, str] | None:
    """Read the last row from an Ultralytics results.csv file."""

    results_csv = run_dir / "results.csv"
    if not results_csv.exists():
        return None

    with results_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    return {key.strip(): value.strip() for key, value in rows[-1].items()}


def command_dataset_report(args: argparse.Namespace) -> int:
    """Print dataset counts and the latest training metrics."""

    dataset_dir = args.dataset.resolve()
    print(f"Dataset: {dataset_dir}")
    for split in ("train", "valid", "test"):
        images, labels = count_dataset_split(dataset_dir, split)
        print(f"  {split}: {images} images, {labels} labels")

    run_dir = args.run_dir.resolve() if args.run_dir else find_latest_training_run(args.runs_root)
    if run_dir is None:
        print("No training run with results.csv was found.")
        return 0

    print(f"\nLatest/selected run: {run_dir}")
    metrics = read_last_metrics(run_dir)
    if metrics is None:
        print("No metrics found yet.")
    else:
        interesting_keys = [
            "epoch",
            "metrics/precision(B)",
            "metrics/recall(B)",
            "metrics/mAP50(B)",
            "metrics/mAP50-95(B)",
            "val/box_loss",
            "val/cls_loss",
            "lr/pg0",
        ]
        for key in interesting_keys:
            if key in metrics:
                print(f"  {key}: {metrics[key]}")

    weights_dir = run_dir / "weights"
    if weights_dir.exists():
        for weight_name in ("best.pt", "last.pt"):
            weight_path = weights_dir / weight_name
            if weight_path.exists():
                print(f"  {weight_name}: {weight_path}")
    return 0


def command_train_combined_dumbbell_detector(args: argparse.Namespace) -> int:
    """Train a detector from the merged dumbbell/weight/other dataset."""

    data_yaml = prepare_combined_dumbbell_dataset(args.zip, args.out, rebuild=args.rebuild)
    if args.resume:
        if args.model is None:
            raise ValueError("Pass --model runs/.../weights/last.pt when using --resume.")
        model_ref = resolve_weights_path(args.model)
        train_kwargs: dict[str, object] = {"resume": True}
        if args.device:
            train_kwargs["device"] = args.device
    else:
        model_ref, train_kwargs = build_profile_train_kwargs("dumbbell_detection", args)
        train_kwargs["data"] = str(data_yaml)
    model = YOLO(model_ref)
    if args.resume:
        train_kwargs["resume"] = True
    model.train(**train_kwargs)
    return 0


def command_train_object_detector(args: argparse.Namespace) -> int:
    """Train any YOLO object detector from a prepared data.yaml file."""

    model_path = resolve_weights_path(args.model) if args.resume else resolve_model_reference(args.model)
    model = YOLO(model_path)
    train_kwargs = {
        "data": str(args.data),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "project": resolve_project_path(args.project),
        "name": args.name,
    }
    if args.device:
        train_kwargs["device"] = args.device
    if args.resume:
        train_kwargs["resume"] = True
    model.train(**train_kwargs)
    return 0


def command_validate_object_detector(args: argparse.Namespace) -> int:
    """Validate any YOLO object detector against a prepared data.yaml file."""

    model = YOLO(resolve_weights_path(args.model))
    metrics = model.val(
        data=str(args.data),
        split=args.split,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        project=resolve_project_path(args.project),
        name=args.name,
    )
    if hasattr(metrics, "results_dict"):
        print("\nSummary:")
        for key, value in metrics.results_dict.items():
            print(f"  {key}: {value:.5f}" if isinstance(value, float) else f"  {key}: {value}")
    return 0


def command_train_body_pose(args: argparse.Namespace) -> int:
    """Train or re-fit a YOLO body-pose model using a 17-keypoint pose dataset."""

    model_path = resolve_weights_path(args.model) if args.resume else resolve_model_reference(args.model)
    model = YOLO(model_path)
    train_kwargs = {
        "task": "pose",
        "data": str(args.data),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "project": resolve_project_path(args.project),
        "name": args.name,
    }
    if args.device:
        train_kwargs["device"] = args.device
    if args.resume:
        train_kwargs["resume"] = True
    model.train(**train_kwargs)
    return 0


def sanitize_label(value: str) -> str:
    """Create a safe folder/file label from a human label."""

    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower())
    return cleaned.strip("_") or "unlabeled"


def command_capture_motion_data(args: argparse.Namespace) -> int:
    """Capture images, optional video, and JSONL motion payloads from a camera."""

    args = fill_detection_defaults(args)
    safe_label = sanitize_label(args.label)
    session_name = args.session or f"{time.strftime('%Y%m%d_%H%M%S')}_{safe_label}"
    session_dir = args.out / session_name
    image_dir = session_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = session_dir / "motion_payloads.jsonl"
    metadata_path = session_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "session": session_name,
                "label": args.label,
                "source": args.source,
                "pose_model": str(args.model),
                "object_model": None if args.object_model is None else str(args.object_model),
                "object_filters": {
                    "object_conf": args.object_conf,
                    "object_track_hold_frames": args.object_track_hold_frames,
                    "object_track_smoothing": args.object_track_smoothing,
                    "object_track_max_center_distance": args.object_track_max_center_distance,
                    "dumbbell_conf": args.dumbbell_conf,
                    "weight_conf": args.weight_conf,
                    "min_object_area_ratio": args.min_object_area_ratio,
                    "max_object_area_ratio": args.max_object_area_ratio,
                    "require_object_body_match": args.require_object_body_match,
                },
                "wearable_json": None if args.wearable_json is None else str(args.wearable_json),
                "esp32_port": args.esp32_port,
                "esp32_transport": args.esp32_transport,
                "esp32_udp_host": args.esp32_udp_host,
                "esp32_udp_port": args.esp32_udp_port,
                "signal_calibration": {
                    "calibration_seconds": args.calibration_seconds,
                    "esp32_side": args.esp32_side,
                    "wearable_side": args.wearable_side,
                },
                "notes": args.notes,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "purpose": "Raw sensor-fusion middleware data for motion signals, YOLO object labeling, and future interaction mapping.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    video_writer = None
    processed_count = 0
    saved_count = 0
    started = time.perf_counter()
    try:
        with PipelineRunner(args, jsonl_path=jsonl_path) as runner:
            for result in runner.frames():
                frame = result.frame
                payload = result.payload
                if args.video and video_writer is None:
                    height, width = frame.shape[:2]
                    fps = runner.cap.get(cv2.CAP_PROP_FPS) if runner.cap is not None else 0.0
                    fps = fps if fps and fps > 0 else 30.0
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    video_writer = cv2.VideoWriter(str(session_dir / "raw_video.mp4"), fourcc, fps, (width, height))
                if video_writer is not None:
                    video_writer.write(frame)

                payload["capture"] = {
                    "session": session_name,
                    "label": args.label,
                    "frame_index": result.index,
                    "saved_image": None,
                }

                if result.index % max(args.save_every, 1) == 0:
                    image_path = image_dir / f"frame_{result.index:06d}.jpg"
                    cv2.imwrite(str(image_path), frame)
                    payload["capture"]["saved_image"] = str(image_path)
                    saved_count += 1

                runner.write_json(payload)
                runner.maybe_print_json(payload)
                processed_count = result.index + 1

                if runner.show_preview(frame, payload, result.pose, result.object_result):
                    break
                if args.duration and (time.perf_counter() - started) >= args.duration:
                    break
    finally:
        if video_writer is not None:
            video_writer.release()

    print(f"Capture session: {session_dir}")
    print(f"Frames processed: {processed_count}")
    print(f"Images saved: {saved_count}")
    print(f"JSONL: {jsonl_path}")
    return 0


def command_analyze_capture(args: argparse.Namespace) -> int:
    """Summarize a recorded motion capture without opening the UI."""

    jsonl_path = resolve_capture_jsonl(args.path, captures_root=args.captures_root)
    summary = analyze_capture(jsonl_path)
    report_path = args.out or (jsonl_path.parent / "capture_analysis.md")
    write_capture_report(summary, report_path)
    print_capture_summary(summary)
    print(f"Report: {report_path}")
    if args.json:
        print(json.dumps(summary, indent=2))
    return 0


def command_extract_video_frames(args: argparse.Namespace) -> int:
    """Extract still images from a video for later YOLO labeling."""

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {args.video}")
    args.out.mkdir(parents=True, exist_ok=True)

    frame_index = 0
    saved_count = 0
    every = max(args.every, 1)
    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break
            if args.mirror:
                frame = cv2.flip(frame, 1)
            if frame_index % every == 0:
                image_path = args.out / f"{args.prefix}_{frame_index:06d}.jpg"
                cv2.imwrite(str(image_path), frame)
                saved_count += 1
                if args.max_images and saved_count >= args.max_images:
                    break
            frame_index += 1
    finally:
        cap.release()

    print(f"Saved {saved_count} images to {args.out}")
    return 0


def command_check_esp32(args: argparse.Namespace) -> int:
    """Read ESP32 JSON lines for a short hardware smoke test."""

    if args.transport == "none":
        print(json.dumps(build_empty_esp32_payload()))
        return 0
    if args.list_ports and args.transport in {"serial", "auto"}:
        print(json.dumps({"available_ports": list_serial_ports()}))
    if args.transport == "auto":
        bridge = ESP32AutoBridge(args.port or "auto", args.baud, args.udp_host, args.udp_port)
    elif args.transport == "udp":
        bridge = ESP32UdpBridge(args.udp_host, args.udp_port)
    else:
        bridge = ESP32SerialBridge(args.port, args.baud)
    started = time.perf_counter()
    try:
        while True:
            print(json.dumps(bridge.poll()))
            if args.seconds and (time.perf_counter() - started) >= args.seconds:
                break
            time.sleep(args.interval)
    finally:
        bridge.close()
    return 0


def command_check_wearable(args: argparse.Namespace) -> int:
    """Read smartwatch/wristband context from a JSON file for a smoke test."""

    bridge = WearableFileBridge(args.path, args.stale_seconds)
    started = time.perf_counter()
    while True:
        print(json.dumps(bridge.poll()))
        if args.seconds and (time.perf_counter() - started) >= args.seconds:
            break
        time.sleep(args.interval)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Define every command available through ``python -m ironquest``."""

    mode_choices = ("vision", "dumbbells", "full")

    class TrackExplicitAction(argparse.Action):
        """Store a value and remember that the user provided this option."""

        def __call__(self, parser, namespace, values, option_string=None):
            explicit = set(getattr(namespace, "_explicit_detection_args", set()))
            explicit.add(self.dest)
            setattr(namespace, "_explicit_detection_args", explicit)
            setattr(namespace, self.dest, values)

    class TrackExplicitBooleanOptionalAction(argparse.BooleanOptionalAction):
        """Store a boolean optional value and remember the user provided it."""

        def __call__(self, parser, namespace, values, option_string=None):
            explicit = set(getattr(namespace, "_explicit_detection_args", set()))
            explicit.add(self.dest)
            setattr(namespace, "_explicit_detection_args", explicit)
            super().__call__(parser, namespace, values, option_string=option_string)

    def add_mode_argument(command_parser: argparse.ArgumentParser) -> None:
        """Add the project-wide execution preset argument to a command parser."""

        command_parser.add_argument(
            "--mode",
            choices=mode_choices,
            help=(
                "Execution preset: vision=body pose only, dumbbells=body+dumbbell model, "
                "full=body+dumbbells+sensors with tracking and mirror."
            ),
        )

    parser = argparse.ArgumentParser(
        prog="python -m ironquest",
        description="Unified Iron Quest 3D camera, pose, sensor-fusion, and dataset prototype.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("full", aliases=["demo", "run"], help="Run the unified live detector with body, dumbbells, and sensors.")
    demo.add_argument("--pose-weights", dest="model", default=DETECT_DEFAULTS["model"], action=TrackExplicitAction, help="Pose model path/name.")
    demo.add_argument("--source", default="0", action=TrackExplicitAction, help="Camera index, video path, image path, or stream URL.")
    demo.add_argument("--object-model", "--object-weights", dest="object_model", type=Path, action=TrackExplicitAction, help="Optional trained object detector. Demo defaults to the combined dumbbell weights in full mode.")
    demo.add_argument("--object-conf", type=float, default=0.20, help="Raw object detector confidence threshold.")
    demo.add_argument("--object-frame-stride", type=int, default=2, help="Run dumbbell/weight YOLO every N frames; cached boxes are reused between runs.")
    demo.add_argument("--object-track-hold-frames", type=int, default=4, help="Keep a tracked dumbbell prediction for this many missed frames.")
    demo.add_argument("--object-track-smoothing", type=float, default=0.55, help="Blend tracked object boxes across frames.")
    demo.add_argument("--object-track-max-center-distance", type=float, default=160.0, help="Maximum center distance for matching a detection to an active object track.")
    demo.add_argument("--dumbbell-conf", type=float, default=0.30, help="Minimum confidence for the dumbbell class.")
    demo.add_argument("--weight-conf", type=float, default=0.50, help="Minimum confidence for the weight class.")
    demo.add_argument("--min-object-area-ratio", type=float, default=0.0015)
    demo.add_argument("--max-object-area-ratio", type=float, default=0.12)
    demo.add_argument("--wearable-json", type=Path, action=TrackExplicitAction, help="Optional JSON file with smartwatch/wristband data.")
    demo.add_argument(
        "--fitquest-worker-url",
        action=TrackExplicitAction,
        help="Stable FitQuest Worker URL used to pull Garmin data into the local wearable JSON file.",
    )
    demo.add_argument(
        "--garmin-bridge",
        action=TrackExplicitBooleanOptionalAction,
        default=DETECT_DEFAULTS["garmin_bridge"],
        help="Start the Garmin Venu 3 BLE heart-rate bridge in the background for the one-command run path.",
    )
    demo.add_argument(
        "--garmin-connectiq-bridge",
        action=TrackExplicitBooleanOptionalAction,
        default=DETECT_DEFAULTS["garmin_connectiq_bridge"],
        help="Start the Garmin Connect IQ HTTP telemetry receiver in the background.",
    )
    demo.add_argument(
        "--garmin-connectiq-host",
        default=DETECT_DEFAULTS["garmin_connectiq_host"],
        action=TrackExplicitAction,
        help="Host/interface for the Garmin Connect IQ HTTP receiver.",
    )
    demo.add_argument(
        "--garmin-connectiq-port",
        type=int,
        default=DETECT_DEFAULTS["garmin_connectiq_port"],
        action=TrackExplicitAction,
        help="TCP port for Garmin Connect IQ telemetry from the phone/watch app.",
    )
    demo.add_argument(
        "--wearable-stale-seconds",
        type=float,
        default=10.0,
        action=TrackExplicitAction,
        help="Mark --wearable-json data stale when the file has not changed for this many seconds.",
    )
    demo.add_argument(
        "--calibration-seconds",
        type=float,
        default=DETECT_DEFAULTS["calibration_seconds"],
        help="Seconds used to auto-calibrate each user's comfortable signal range.",
    )
    demo.add_argument(
        "--esp32-side",
        choices=["left", "right"],
        default=DETECT_DEFAULTS["esp32_side"],
        help="Hand wearing the ESP32+IMU gym glove.",
    )
    demo.add_argument(
        "--esp32-transport",
        choices=ESP32_TRANSPORT_CHOICES,
        default=DETECT_DEFAULTS["esp32_transport"],
        action=TrackExplicitAction,
        help="ESP32 telemetry transport. auto listens to USB serial and Wi-Fi UDP together.",
    )
    demo.add_argument(
        "--wearable-side",
        choices=["left", "right"],
        default=DETECT_DEFAULTS["wearable_side"],
        help="Hand wearing the Garmin smartwatch.",
    )
    demo.add_argument("--esp32-port", default="auto", help="Optional ESP32 serial port, for example COM4 or auto.")
    demo.add_argument("--esp32-baud", type=int, default=115200, help="ESP32 serial baud rate.")
    demo.add_argument("--esp32-udp-host", default=DETECT_DEFAULTS["esp32_udp_host"], help="Local host/IP for the UDP listener.")
    demo.add_argument("--esp32-udp-port", type=int, default=DETECT_DEFAULTS["esp32_udp_port"], help="Local UDP port for ESP32 Wi-Fi telemetry.")
    demo.add_argument("--display-width", type=int, default=1100)
    demo.add_argument("--panel-width", type=int, default=520)
    demo.add_argument("--ui-detail", choices=["simple", "standard", "debug"], default="simple", action=TrackExplicitAction)
    demo.add_argument("--device", default="auto", help="Inference device: auto, cpu, cuda:0, 0, or mps.")
    demo.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Launch the OpenCV monitor fullscreen with aspect-ratio letterboxing.",
    )
    demo.add_argument(
        "--pose-track",
        action=TrackExplicitBooleanOptionalAction,
        default=False,
        help="Use Ultralytics tracking for smoother person continuity. Disabled by default for speed.",
    )
    demo.add_argument("--mirror", action=TrackExplicitBooleanOptionalAction, default=True)
    demo.add_argument("--jsonl", type=Path, help="Save one JSON payload per frame.")
    demo.add_argument("--print-json", action="store_true", help="Print payloads to the terminal.")
    demo.add_argument("--no-show", action="store_true")
    demo.add_argument(
        "--web",
        action="store_true",
        help="Publish the live sensor-fusion stream to the FitQuest browser client.",
    )
    demo.add_argument("--web-host", default="127.0.0.1", help="Local host for the FitQuest browser gateway.")
    demo.add_argument("--web-port", type=int, default=8787, help="Local port for the FitQuest browser gateway.")
    demo.add_argument("--max-frames", type=int)
    demo.set_defaults(func=command_demo)

    detect = subparsers.add_parser("detect", help="Run camera/video movement detection.")
    add_mode_argument(detect)
    detect.add_argument("--model", "--pose-weights", dest="model", default="yolo26n-pose.pt", action=TrackExplicitAction, help="YOLO pose model path/name.")
    detect.add_argument("--source", default="0", action=TrackExplicitAction, help="Camera index, video path, image path, or stream URL.")
    detect.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    detect.add_argument("--conf", type=float, default=0.20, help="YOLO confidence threshold.")
    detect.add_argument(
        "--pose-track",
        action=TrackExplicitBooleanOptionalAction,
        default=False,
        help="Use Ultralytics tracking for smoother person continuity. Disabled by default for speed.",
    )
    detect.add_argument(
        "--pose-smoothing",
        type=float,
        default=0.55,
        help="Blend visible joints across frames. Use 1.0 for raw YOLO keypoints.",
    )
    detect.add_argument(
        "--pose-hold-frames",
        type=int,
        default=2,
        help="Keep a recently visible joint for this many frames during brief occlusion.",
    )
    detect.add_argument(
        "--object-model",
        "--object-weights",
        dest="object_model",
        type=Path,
        action=TrackExplicitAction,
        help="Optional dumbbell/weight detector, for example runs/.../weights/best.pt.",
    )
    detect.add_argument("--object-imgsz", type=int, default=960, help="Object detector image size.")
    detect.add_argument("--object-conf", type=float, default=0.20, help="Object detector confidence threshold.")
    detect.add_argument("--object-frame-stride", type=int, default=2, help="Run dumbbell/weight YOLO every N frames; cached boxes are reused between runs.")
    detect.add_argument("--object-track-hold-frames", type=int, default=4, help="Keep a tracked dumbbell prediction for this many missed frames.")
    detect.add_argument("--object-track-smoothing", type=float, default=0.55, help="Blend tracked object boxes across frames.")
    detect.add_argument("--object-track-max-center-distance", type=float, default=160.0, help="Maximum center distance for matching a detection to an active object track.")
    detect.add_argument("--dumbbell-conf", type=float, default=0.30, help="Minimum confidence for the dumbbell class.")
    detect.add_argument("--weight-conf", type=float, default=0.50, help="Minimum confidence for the weight class.")
    detect.add_argument(
        "--min-object-area-ratio",
        type=float,
        default=0.0015,
        help="Ignore object boxes smaller than this frame-area ratio to reduce tiny false positives.",
    )
    detect.add_argument(
        "--max-object-area-ratio",
        type=float,
        default=0.12,
        help="Ignore object boxes larger than this frame-area ratio to reject body-region false positives.",
    )
    detect.add_argument(
        "--require-object-body-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only accept dumbbell candidates that are near a visible wrist or forearm.",
    )
    detect.add_argument("--pose-joint-conf", type=float, default=0.25, help="Minimum keypoint confidence for limb context.")
    detect.add_argument(
        "--max-wrist-distance",
        type=float,
        default=90.0,
        help="Maximum pixel distance for a dumbbell to count as near a wrist.",
    )
    detect.add_argument(
        "--max-forearm-distance",
        type=float,
        default=70.0,
        help="Maximum pixel distance for a dumbbell to count as near a forearm segment.",
    )
    detect.add_argument(
        "--analysis-window",
        type=int,
        default=12,
        help="Recent frame window used for open-ended motion primitives.",
    )
    detect.add_argument(
        "--calibration-seconds",
        type=float,
        default=DETECT_DEFAULTS["calibration_seconds"],
        help="Seconds used to auto-calibrate each user's comfortable signal range.",
    )
    detect.add_argument(
        "--esp32-side",
        choices=["left", "right"],
        default=DETECT_DEFAULTS["esp32_side"],
        help="Hand wearing the ESP32+IMU gym glove.",
    )
    detect.add_argument(
        "--esp32-transport",
        choices=ESP32_TRANSPORT_CHOICES,
        default=DETECT_DEFAULTS["esp32_transport"],
        help="ESP32 telemetry transport. auto listens to USB serial and Wi-Fi UDP together.",
    )
    detect.add_argument(
        "--wearable-side",
        choices=["left", "right"],
        default=DETECT_DEFAULTS["wearable_side"],
        help="Hand wearing the Garmin smartwatch.",
    )
    detect.add_argument("--esp32-port", help="Optional ESP32 serial port, for example COM4 or auto.")
    detect.add_argument("--esp32-baud", type=int, default=115200, help="ESP32 serial baud rate.")
    detect.add_argument("--esp32-udp-host", default=DETECT_DEFAULTS["esp32_udp_host"], help="Local host/IP for the UDP listener.")
    detect.add_argument("--esp32-udp-port", type=int, default=DETECT_DEFAULTS["esp32_udp_port"], help="Local UDP port for ESP32 Wi-Fi telemetry.")
    detect.add_argument(
        "--wearable-json",
        type=Path,
        help="Optional JSON file with the latest smartwatch/wristband sample.",
    )
    detect.add_argument(
        "--fitquest-worker-url",
        help="Stable FitQuest Worker URL used to pull Garmin data into the local wearable JSON file.",
    )
    detect.add_argument(
        "--wearable-stale-seconds",
        type=float,
        default=10.0,
        help="Mark --wearable-json data stale when the file has not changed for this many seconds.",
    )
    detect.add_argument("--jsonl", type=Path, help="Save one JSON payload per frame.")
    detect.add_argument("--print-json", action="store_true", help="Print payloads to the terminal.")
    detect.add_argument("--no-show", action="store_true", help="Do not open the OpenCV preview window.")
    detect.add_argument("--display-width", type=int, default=960, help="Preview window frame width in pixels.")
    detect.add_argument("--panel-width", type=int, default=520, help="Right dashboard panel width in pixels.")
    detect.add_argument("--device", default="auto", help="Inference device: auto, cpu, cuda:0, 0, or mps.")
    detect.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Launch the OpenCV monitor fullscreen with aspect-ratio letterboxing.",
    )
    detect.add_argument(
        "--ui-detail",
        choices=["simple", "standard", "debug"],
        default="simple",
        help="Initial HUD mode: simple/standard start clean; debug starts with the raw overlay. Press d to toggle.",
    )
    detect.add_argument(
        "--mirror",
        action=TrackExplicitBooleanOptionalAction,
        default=False,
        help="Mirror only the preview; analysis keeps real anatomical left/right.",
    )
    detect.add_argument("--max-frames", type=int, help="Stop after N frames.")
    detect.set_defaults(func=command_detect)

    export_pose = subparsers.add_parser("export-pose", help="Export YOLO26 pose for deployment experiments.")
    export_pose.add_argument("--model", default="yolo26n-pose.pt", help="Pose model path/name.")
    export_pose.add_argument("--format", default="onnx", help="Export format: onnx, openvino, engine, tflite, etc.")
    export_pose.add_argument("--imgsz", type=int, default=640, help="Export image size.")
    export_pose.add_argument("--dynamic", action="store_true", help="Allow dynamic input sizes where supported.")
    export_pose.add_argument("--half", action="store_true", help="Use FP16 export where supported.")
    export_pose.add_argument("--int8", action="store_true", help="Use INT8 export where supported.")
    export_pose.set_defaults(func=command_export_pose)

    prepare_combined = subparsers.add_parser("prepare-combined-dumbbell-data", help="Merge the two dumbbell datasets.")
    prepare_combined.add_argument(
        "--zip",
        type=Path,
        nargs="+",
        default=[DEFAULT_DUMBBELL_ZIP, DEFAULT_DUMBBELL_ZIP_2],
        help="YOLO zip datasets to merge.",
    )
    prepare_combined.add_argument("--out", type=Path, default=DEFAULT_COMBINED_DUMBBELL_OUT)
    prepare_combined.add_argument("--rebuild", action="store_true", help="Delete and rebuild the generated combined dataset.")
    prepare_combined.set_defaults(func=command_prepare_combined_dumbbell_data)

    report = subparsers.add_parser("dataset-report", help="Show dataset counts and latest training metrics.")
    report.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_COMBINED_DUMBBELL_OUT,
        help="Prepared YOLO dataset directory. Defaults to the combined dumbbell dataset.",
    )
    report.add_argument("--runs-root", type=Path, default=DEFAULT_DETECT_PROJECT, help="Directory where object-detection training runs are saved.")
    report.add_argument("--run-dir", type=Path, help="Specific training run directory to inspect.")
    report.set_defaults(func=command_dataset_report)

    train_combined = subparsers.add_parser("train-combined-dumbbell-detector", help="Train with both dumbbell datasets.")
    train_combined.add_argument(
        "--zip",
        type=Path,
        nargs="+",
        default=[DEFAULT_DUMBBELL_ZIP, DEFAULT_DUMBBELL_ZIP_2],
        help="YOLO zip datasets to merge before training.",
    )
    train_combined.add_argument("--out", type=Path, default=DEFAULT_COMBINED_DUMBBELL_OUT)
    train_combined.add_argument("--rebuild", action="store_true", help="Delete and rebuild the generated combined dataset before training.")
    train_combined.add_argument("--model", help="Detection model or checkpoint. Defaults to the configured dumbbell profile.")
    train_combined.add_argument("--epochs", type=int)
    train_combined.add_argument("--imgsz", type=int)
    train_combined.add_argument("--batch", type=int)
    train_combined.add_argument("--device", default=None, help="Training device, for example 0, cpu, or cuda:0.")
    train_combined.add_argument("--project")
    train_combined.add_argument("--name")
    train_combined.add_argument("--resume", action="store_true")
    train_combined.set_defaults(func=command_train_combined_dumbbell_detector)

    train_object = subparsers.add_parser("train-object-detector", help="Train any YOLO detector from a data.yaml file.")
    train_object.add_argument("--data", type=Path, required=True, help="Ultralytics data.yaml file.")
    train_object.add_argument("--model", default="yolo26n.pt", help="Base model or last.pt checkpoint.")
    train_object.add_argument("--epochs", type=int, default=50)
    train_object.add_argument("--imgsz", type=int, default=640)
    train_object.add_argument("--batch", type=int, default=-1, help="Batch size. Use -1 for Ultralytics auto-batch.")
    train_object.add_argument("--device", default=None, help="Training device, for example 0, cpu, or cuda:0.")
    train_object.add_argument("--project", default=DEFAULT_DETECT_PROJECT)
    train_object.add_argument("--name", default="custom_object_yolo26n")
    train_object.add_argument("--resume", action="store_true", help="Resume training from a last.pt checkpoint.")
    train_object.set_defaults(func=command_train_object_detector)

    train_body = subparsers.add_parser("train-body-pose", help="Train or re-fit a 17-keypoint YOLO body-pose model.")
    train_body.add_argument(
        "--data",
        default="coco-pose.yaml",
        help="Body-pose dataset YAML. Use a local 17-keypoint data.yaml when you label IronQuest body pose.",
    )
    train_body.add_argument("--model", default=BASE_POSE_WEIGHTS, help="Base body-pose model or last.pt checkpoint.")
    train_body.add_argument("--epochs", type=int, default=100)
    train_body.add_argument("--imgsz", type=int, default=640)
    train_body.add_argument("--batch", type=int, default=-1, help="Batch size. Use -1 for Ultralytics auto-batch.")
    train_body.add_argument("--device", default=None, help="Training device, for example 0, cpu, or cuda:0.")
    train_body.add_argument("--project", default=DEFAULT_POSE_PROJECT)
    train_body.add_argument("--name", default="body_pose_yolo26n_improved")
    train_body.add_argument("--resume", action="store_true", help="Resume training from a last.pt checkpoint.")
    train_body.set_defaults(func=command_train_body_pose)

    validate_object = subparsers.add_parser("validate-object-detector", help="Validate any YOLO detector from a data.yaml file.")
    validate_object.add_argument("--data", type=Path, required=True, help="Ultralytics data.yaml file.")
    validate_object.add_argument("--model", type=Path, required=True, help="Trained detector weights.")
    validate_object.add_argument("--split", choices=["val", "test"], default="test")
    validate_object.add_argument("--imgsz", type=int, default=640)
    validate_object.add_argument("--conf", type=float, default=0.25)
    validate_object.add_argument("--iou", type=float, default=0.7)
    validate_object.add_argument("--project", default=DEFAULT_VALIDATE_PROJECT)
    validate_object.add_argument("--name", default="custom_object_eval")
    validate_object.set_defaults(func=command_validate_object_detector)

    capture = subparsers.add_parser("capture-motion-data", help="Record images/video/JSONL for project-specific training data.")
    add_mode_argument(capture)
    capture.add_argument("--label", required=True, help="Human label for this session, for example right_overhead_left_front.")
    capture.add_argument("--session", help="Optional folder name. Defaults to timestamp plus label.")
    capture.add_argument("--out", type=Path, default=Path("data/captures"), help="Root folder for captured sessions.")
    capture.add_argument("--notes", default="", help="Free-text notes saved in metadata.json.")
    capture.add_argument("--model", "--pose-weights", dest="model", default="yolo26n-pose.pt", action=TrackExplicitAction, help="YOLO pose model path/name.")
    capture.add_argument("--source", default="0", action=TrackExplicitAction, help="Camera index, video path, image path, or stream URL.")
    capture.add_argument("--imgsz", type=int, default=640, help="Pose inference image size.")
    capture.add_argument("--conf", type=float, default=0.20, help="Pose confidence threshold.")
    capture.add_argument(
        "--pose-track",
        action=TrackExplicitBooleanOptionalAction,
        default=False,
        help="Use Ultralytics tracking for smoother person continuity. Disabled by default for speed.",
    )
    capture.add_argument("--pose-smoothing", type=float, default=0.55, help="Blend visible joints across frames. Use 1.0 for raw YOLO keypoints.")
    capture.add_argument("--pose-hold-frames", type=int, default=2, help="Keep recently visible joints during brief occlusion.")
    capture.add_argument("--object-model", "--object-weights", dest="object_model", type=Path, action=TrackExplicitAction, help="Optional dumbbell/weight detector.")
    capture.add_argument("--object-imgsz", type=int, default=960, help="Object detector image size.")
    capture.add_argument("--object-conf", type=float, default=0.20, help="Object detector confidence threshold.")
    capture.add_argument("--object-frame-stride", type=int, default=2, help="Run dumbbell/weight YOLO every N frames; cached boxes are reused between runs.")
    capture.add_argument("--object-track-hold-frames", type=int, default=4, help="Keep a tracked dumbbell prediction for this many missed frames.")
    capture.add_argument("--object-track-smoothing", type=float, default=0.55, help="Blend tracked object boxes across frames.")
    capture.add_argument("--object-track-max-center-distance", type=float, default=160.0, help="Maximum center distance for matching a detection to an active object track.")
    capture.add_argument("--dumbbell-conf", type=float, default=0.30, help="Minimum confidence for the dumbbell class.")
    capture.add_argument("--weight-conf", type=float, default=0.50, help="Minimum confidence for the weight class.")
    capture.add_argument("--min-object-area-ratio", type=float, default=0.0015)
    capture.add_argument("--max-object-area-ratio", type=float, default=0.12)
    capture.add_argument(
        "--require-object-body-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only accept dumbbell candidates that are near a visible wrist or forearm.",
    )
    capture.add_argument("--pose-joint-conf", type=float, default=0.25, help="Minimum keypoint confidence.")
    capture.add_argument("--max-wrist-distance", type=float, default=90.0)
    capture.add_argument("--max-forearm-distance", type=float, default=70.0)
    capture.add_argument("--analysis-window", type=int, default=12)
    capture.add_argument(
        "--calibration-seconds",
        type=float,
        default=DETECT_DEFAULTS["calibration_seconds"],
        help="Seconds used to auto-calibrate each user's comfortable signal range.",
    )
    capture.add_argument(
        "--esp32-side",
        choices=["left", "right"],
        default=DETECT_DEFAULTS["esp32_side"],
        help="Hand wearing the ESP32+IMU gym glove.",
    )
    capture.add_argument(
        "--esp32-transport",
        choices=ESP32_TRANSPORT_CHOICES,
        default=DETECT_DEFAULTS["esp32_transport"],
        help="ESP32 telemetry transport. auto listens to USB serial and Wi-Fi UDP together.",
    )
    capture.add_argument(
        "--wearable-side",
        choices=["left", "right"],
        default=DETECT_DEFAULTS["wearable_side"],
        help="Hand wearing the Garmin smartwatch.",
    )
    capture.add_argument("--esp32-port", help="Optional ESP32 serial port, for example COM4 or auto.")
    capture.add_argument("--esp32-baud", type=int, default=115200)
    capture.add_argument("--esp32-udp-host", default=DETECT_DEFAULTS["esp32_udp_host"], help="Local host/IP for the UDP listener.")
    capture.add_argument("--esp32-udp-port", type=int, default=DETECT_DEFAULTS["esp32_udp_port"], help="Local UDP port for ESP32 Wi-Fi telemetry.")
    capture.add_argument("--wearable-json", type=Path, help="Optional JSON file with smartwatch/wristband data.")
    capture.add_argument("--wearable-stale-seconds", type=float, default=10.0)
    capture.add_argument("--save-every", type=int, default=5, help="Save one image every N frames.")
    capture.add_argument("--duration", type=float, help="Stop after N seconds.")
    capture.add_argument("--max-frames", type=int, help="Stop after N frames.")
    capture.add_argument("--video", action="store_true", help="Also save raw_video.mp4.")
    capture.add_argument("--print-json", action="store_true", help="Print payloads to the terminal.")
    capture.add_argument("--no-show", action="store_true", help="Do not open the OpenCV preview window.")
    capture.add_argument("--display-width", type=int, default=960)
    capture.add_argument("--panel-width", type=int, default=520)
    capture.add_argument("--device", default="auto", help="Inference device: auto, cpu, cuda:0, 0, or mps.")
    capture.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Launch the OpenCV monitor fullscreen with aspect-ratio letterboxing.",
    )
    capture.add_argument(
        "--ui-detail",
        choices=["simple", "standard", "debug"],
        default="simple",
        help="Initial HUD mode: simple/standard start clean; debug starts with the raw overlay. Press d to toggle.",
    )
    capture.add_argument(
        "--mirror",
        action=TrackExplicitBooleanOptionalAction,
        default=False,
        help="Mirror only the preview; saved images/video and analysis stay unmirrored.",
    )
    capture.set_defaults(func=command_capture_motion_data)

    analyze_capture_parser = subparsers.add_parser("analyze-capture", help="Summarize the latest or selected capture JSONL.")
    analyze_capture_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Capture folder or motion_payloads.jsonl. Defaults to the newest folder under data/captures.",
    )
    analyze_capture_parser.add_argument(
        "--captures-root",
        type=Path,
        default=Path("data/captures"),
        help="Root folder used when no capture path is provided.",
    )
    analyze_capture_parser.add_argument("--out", type=Path, help="Optional markdown report path.")
    analyze_capture_parser.add_argument("--json", action="store_true", help="Also print the full JSON summary.")
    analyze_capture_parser.set_defaults(func=command_analyze_capture)

    extract_frames = subparsers.add_parser("extract-video-frames", help="Extract images from a recorded video for YOLO labeling.")
    extract_frames.add_argument("--video", type=Path, required=True, help="Input video path.")
    extract_frames.add_argument("--out", type=Path, required=True, help="Output image folder.")
    extract_frames.add_argument("--every", type=int, default=10, help="Save one image every N frames.")
    extract_frames.add_argument("--max-images", type=int, help="Optional limit.")
    extract_frames.add_argument("--prefix", default="frame", help="Output filename prefix.")
    extract_frames.add_argument("--mirror", action="store_true", help="Mirror frames before saving.")
    extract_frames.set_defaults(func=command_extract_video_frames)

    check_esp32 = subparsers.add_parser("check-esp32", aliases=["esp32"], help="Read ESP32 newline JSON from serial or UDP.")
    check_esp32.add_argument("--transport", choices=ESP32_TRANSPORT_CHOICES, default="auto", help="Read ESP32 over USB serial, Wi-Fi UDP, or both with auto.")
    check_esp32.add_argument("--port", default="auto", help="Serial port, for example COM4, or auto for hardware detection.")
    check_esp32.add_argument("--baud", type=int, default=115200)
    check_esp32.add_argument("--udp-host", default=DETECT_DEFAULTS["esp32_udp_host"], help="Local host/IP for the UDP listener.")
    check_esp32.add_argument("--udp-port", type=int, default=DETECT_DEFAULTS["esp32_udp_port"], help="Local UDP port for ESP32 Wi-Fi telemetry.")
    check_esp32.add_argument("--seconds", type=float, default=5.0)
    check_esp32.add_argument("--interval", type=float, default=0.25)
    check_esp32.add_argument("--list-ports", action="store_true", help="Print visible serial ports before polling.")
    check_esp32.set_defaults(func=command_check_esp32)

    check_wearable = subparsers.add_parser("check-wearable", help="Read smartwatch/wristband data from a JSON file.")
    check_wearable.add_argument("--path", type=Path, help="Path to the wearable JSON sample file.")
    check_wearable.add_argument("--seconds", type=float, default=5.0)
    check_wearable.add_argument("--interval", type=float, default=0.5)
    check_wearable.add_argument("--stale-seconds", type=float, default=10.0)
    check_wearable.set_defaults(func=command_check_wearable)

    return parser


def main() -> int:
    """Parse command-line arguments and run the selected command handler."""

    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)
