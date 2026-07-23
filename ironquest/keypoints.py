"""COCO keypoint utilities used by YOLO pose models.

Ultralytics YOLO pose models return 17 COCO keypoints per detected person.
This module keeps that mapping in one place so movement code does not need
hard-coded numeric indexes scattered throughout the project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


COCO_KEYPOINTS = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}

SIDE_AWARE_JOINTS = {
    "eye",
    "ear",
    "shoulder",
    "elbow",
    "wrist",
    "hip",
    "knee",
    "ankle",
}


@dataclass(frozen=True)
class PoseCandidate:
    """One detected person from a YOLO pose result."""

    xy: np.ndarray
    conf: np.ndarray | None
    box_confidence: float | None = None


class PoseSmoother:
    """Reduce frame-to-frame keypoint noise while keeping recent joints alive.

    YOLO pose estimates each frame independently. Small changes in lighting,
    motion blur, or partial occlusion can make a wrist/elbow jump for one
    frame. This smoother blends visible joints with their recent position and
    can hold a missing joint briefly before it disappears from analysis.
    """

    def __init__(self, alpha: float = 0.55, hold_frames: int = 2, min_confidence: float = 0.05):
        """Store smoothing strength and how long to keep recently visible joints."""

        self.alpha = float(np.clip(alpha, 0.0, 1.0))
        self.hold_frames = max(int(hold_frames), 0)
        self.min_confidence = float(min_confidence)
        self._xy: np.ndarray | None = None
        self._conf: np.ndarray | None = None
        self._missing: np.ndarray | None = None

    def reset(self) -> None:
        """Clear all remembered keypoints."""

        self._xy = None
        self._conf = None
        self._missing = None

    def update(self, pose: PoseCandidate | None) -> PoseCandidate | None:
        """Return a smoothed pose candidate for the current frame."""

        if pose is None:
            if self._xy is None or self._missing is None:
                return None
            self._missing += 1
            if np.all(self._missing > self.hold_frames):
                self.reset()
                return None
            return PoseCandidate(xy=self._xy.copy(), conf=None if self._conf is None else self._conf.copy())

        xy = pose.xy.astype(float, copy=True)
        conf = None if pose.conf is None else pose.conf.astype(float, copy=True)
        visible = np.any(xy != 0, axis=1)
        if conf is not None:
            visible = visible & (conf >= self.min_confidence)

        if self._xy is None:
            self._xy = xy.copy()
            self._conf = None if conf is None else conf.copy()
            self._missing = np.where(visible, 0, self.hold_frames + 1).astype(int)
            return pose

        assert self._missing is not None
        smoothed_xy = xy.copy()
        previous_available = self._missing <= self.hold_frames
        blend_mask = visible & previous_available
        smoothed_xy[blend_mask] = self.alpha * xy[blend_mask] + (1.0 - self.alpha) * self._xy[blend_mask]

        hold_mask = (~visible) & previous_available & (self._missing < self.hold_frames)
        smoothed_xy[hold_mask] = self._xy[hold_mask]

        missing = self._missing.copy()
        missing[visible] = 0
        missing[~visible] += 1
        drop_mask = (~visible) & (missing > self.hold_frames)
        smoothed_xy[drop_mask] = 0.0

        if conf is None and self._conf is not None:
            smoothed_conf = self._conf.copy()
            smoothed_conf[drop_mask] = 0.0
        elif conf is not None:
            smoothed_conf = conf.copy()
            if self._conf is not None:
                smoothed_conf[blend_mask] = self.alpha * conf[blend_mask] + (1.0 - self.alpha) * self._conf[blend_mask]
                smoothed_conf[hold_mask] = self._conf[hold_mask] * 0.75
            smoothed_conf[drop_mask] = 0.0
        else:
            smoothed_conf = None

        self._xy = smoothed_xy
        self._conf = None if smoothed_conf is None else smoothed_conf.copy()
        self._missing = missing
        return PoseCandidate(
            xy=smoothed_xy,
            conf=smoothed_conf,
            box_confidence=pose.box_confidence,
        )


def resolve_joint_name(joint: str, side: str | None = None) -> str:
    """Convert a generic joint name like ``elbow`` into ``left_elbow``.

    Center-only joints like ``nose`` do not need a side. COCO does not include
    ``foot_index`` keypoints, so ankle is the lowest reliable lower-body point
    available from the standard YOLO26 pose model.
    """

    joint = joint.strip().lower()
    if joint in COCO_KEYPOINTS:
        return joint
    if joint in SIDE_AWARE_JOINTS:
        if side not in {"left", "right"}:
            raise ValueError(f"Joint '{joint}' needs side='left' or side='right'.")
        return f"{side}_{joint}"
    raise KeyError(f"Unknown COCO joint '{joint}'.")


def calculate_angle(a: Iterable[float], b: Iterable[float], c: Iterable[float]) -> float:
    """Return the smaller angle ABC in degrees.

    Example: shoulder-elbow-wrist gives the elbow angle.
    """

    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    c_arr = np.asarray(c, dtype=float)

    radians = np.arctan2(c_arr[1] - b_arr[1], c_arr[0] - b_arr[0]) - np.arctan2(
        a_arr[1] - b_arr[1], a_arr[0] - b_arr[0]
    )
    angle = abs(radians * 180.0 / np.pi)
    return float(360.0 - angle if angle > 180.0 else angle)


def is_visible(
    pose: PoseCandidate,
    joint_name: str,
    min_confidence: float = 0.25,
) -> bool:
    """Check whether a joint has usable coordinates and confidence."""

    idx = COCO_KEYPOINTS[joint_name]
    point = pose.xy[idx]
    if point.shape[0] < 2:
        return False

    # Ultralytics often stores missing joints as (0, 0). A real keypoint could
    # be near an image border, but for this camera-monitor setup the user should not
    # be exactly at the top-left pixel, so (0, 0) is treated as missing.
    if point[0] == 0 and point[1] == 0:
        return False
    if pose.conf is not None:
        return bool(pose.conf[idx] >= min_confidence)
    return bool(point[0] != 0 or point[1] != 0)


def get_point(
    pose: PoseCandidate,
    joint: str,
    side: str | None = None,
    min_confidence: float = 0.25,
) -> np.ndarray | None:
    """Return a keypoint coordinate or ``None`` if it is not reliable."""

    joint_name = resolve_joint_name(joint, side)
    if not is_visible(pose, joint_name, min_confidence=min_confidence):
        return None
    return pose.xy[COCO_KEYPOINTS[joint_name]]


def average_confidence(
    pose: PoseCandidate,
    joints: Iterable[str],
    side: str,
    min_confidence: float = 0.25,
) -> float:
    """Average confidence for a set of joints on one body side."""

    scores: list[float] = []
    for joint in joints:
        joint_name = resolve_joint_name(joint, side)
        if not is_visible(pose, joint_name, min_confidence=min_confidence):
            return 0.0
        if pose.conf is not None:
            scores.append(float(pose.conf[COCO_KEYPOINTS[joint_name]]))
        else:
            scores.append(1.0)
    return float(np.mean(scores)) if scores else 0.0


def extract_primary_pose(result) -> PoseCandidate | None:
    """Pick the most confident person from one Ultralytics result object."""

    if result.keypoints is None:
        return None

    xy = result.keypoints.xy
    if xy is None or len(xy) == 0:
        return None

    xy_np = xy.cpu().numpy()
    conf_np = None
    if getattr(result.keypoints, "conf", None) is not None:
        conf_np = result.keypoints.conf.cpu().numpy()

    best_idx = 0
    box_confidence = None
    if getattr(result, "boxes", None) is not None and getattr(result.boxes, "conf", None) is not None:
        box_scores = result.boxes.conf.cpu().numpy()
        if len(box_scores) > 0:
            best_idx = int(np.argmax(box_scores))
            box_confidence = float(box_scores[best_idx])
    elif conf_np is not None:
        best_idx = int(np.argmax(np.nanmean(conf_np, axis=1)))

    return PoseCandidate(
        xy=xy_np[best_idx],
        conf=conf_np[best_idx] if conf_np is not None else None,
        box_confidence=box_confidence,
    )
