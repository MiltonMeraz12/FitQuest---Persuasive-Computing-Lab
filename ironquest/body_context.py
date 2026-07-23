"""Body-side and dumbbell-use context for camera frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

import numpy as np

from .keypoints import PoseCandidate, get_point


@dataclass
class ObjectDetection:
    """One YOLO object box converted into project-friendly coordinates."""

    label: str
    confidence: float
    xyxy: tuple[float, float, float, float]
    z_distance: float | None = None
    rejection_reason: str | None = None
    rejection_detail: Any | None = None
    track_id: int | None = None
    tracking_state: str = "detected"
    stale_frames: int = 0

    @property
    def width(self) -> float:
        """Return the detection width in pixels."""

        x1, _, x2, _ = self.xyxy
        return max(0.0, x2 - x1)

    @property
    def height(self) -> float:
        """Return the detection height in pixels."""

        _, y1, _, y2 = self.xyxy
        return max(0.0, y2 - y1)

    @property
    def area(self) -> float:
        """Return the detection area in pixels."""

        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        """Return the center of the detection box in image pixels."""

        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def as_payload(self) -> dict[str, Any]:
        """Convert the detection into values that can be saved as JSON."""

        payload = {
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "xyxy": [round(value, 2) for value in self.xyxy],
            "center": [round(value, 2) for value in self.center],
            "z_distance": None if self.z_distance is None else round(self.z_distance, 3),
            "area": round(self.area, 2),
        }
        if self.z_distance is not None:
            payload["center_3d"] = [
                round(self.center[0], 2),
                round(self.center[1], 2),
                round(self.z_distance, 3),
            ]
        if self.rejection_reason:
            payload["rejection_reason"] = self.rejection_reason
        if self.rejection_detail:
            if hasattr(self.rejection_detail, "as_payload"):
                payload["rejection_detail"] = self.rejection_detail.as_payload()
            else:
                payload["rejection_detail"] = self.rejection_detail
        if self.track_id is not None:
            payload["track_id"] = self.track_id
        if self.tracking_state != "detected" or self.stale_frames:
            payload["tracking_state"] = self.tracking_state
            payload["stale_frames"] = self.stale_frames
        return payload


@dataclass
class ObjectTrackState:
    """Temporal state for one dumbbell-like object across frames."""

    track_id: int
    label: str
    confidence: float
    xyxy: tuple[float, float, float, float]
    z_distance: float | None = None
    velocity: tuple[float, float] = (0.0, 0.0)
    missed_frames: int = 0


@dataclass(frozen=True)
class BodyContextConfig:
    """Thresholds used by body/object context filters."""

    wearable_area_ratio: float = 0.005
    wearable_overlap_scale: float = 0.55
    wearable_overlap_min_px: float = 12.0
    wearable_overlap_max_px: float = 28.0
    shoulder_width_to_torso_scale: float = 1.25
    fallback_torso_scale_px: float = 100.0
    depth_epsilon: float = 1e-6
    z_distance_min: float = 0.0
    z_distance_max: float = 3.0


BODY_CONTEXT_CONFIG = BodyContextConfig()


@dataclass(frozen=True)
class WearableRejectionDetail:
    """Why a tiny object candidate was treated as wrist-wearable noise."""

    matched_wrist_side: str
    wrist_distance: float
    overlap_threshold: float
    area_ratio: float
    max_area_ratio: float

    def as_payload(self) -> dict[str, Any]:
        """Return JSON-friendly rejection details."""

        return {
            "matched_wrist_side": self.matched_wrist_side,
            "wrist_distance": round(self.wrist_distance, 2),
            "overlap_threshold": round(self.overlap_threshold, 2),
            "area_ratio": round(self.area_ratio, 5),
            "max_area_ratio": self.max_area_ratio,
        }


@dataclass(frozen=True)
class ObjectDetectionFilters:
    """Object detector filters applied before a dumbbell is accepted."""

    min_area_ratio: float
    max_area_ratio: float
    label_confidences: dict[str, float] = field(default_factory=dict)
    require_body_match: bool = True
    wearable_area_ratio: float = BODY_CONTEXT_CONFIG.wearable_area_ratio

    def as_payload(self) -> dict[str, Any]:
        """Return filter settings for logs and debugging."""

        return {
            "min_area_ratio": self.min_area_ratio,
            "max_area_ratio": self.max_area_ratio,
            "label_confidences": self.label_confidences,
            "require_body_match": self.require_body_match,
            "wearable_area_ratio": self.wearable_area_ratio,
        }


class ObjectTemporalTracker:
    """Keep accepted dumbbell boxes stable through brief detector dropouts.

    This is deliberately post-detector tracking: it never creates a new object
    unless YOLO has already produced a valid dumbbell/weight candidate. During
    short misses it publishes a decayed, predicted box marked as ``tracked`` so
    downstream code can distinguish continuity from a fresh model detection.
    """

    def __init__(
        self,
        max_stale_frames: int = 6,
        smoothing: float = 0.65,
        max_center_distance: float = 160.0,
        min_iou: float = 0.05,
        confidence_decay: float = 0.82,
    ):
        self.max_stale_frames = max(0, int(max_stale_frames))
        self.smoothing = float(np.clip(smoothing, 0.0, 1.0))
        self.max_center_distance = max(1.0, float(max_center_distance))
        self.min_iou = float(np.clip(min_iou, 0.0, 1.0))
        self.confidence_decay = float(np.clip(confidence_decay, 0.0, 1.0))
        self._tracks: dict[int, ObjectTrackState] = {}
        self._next_track_id = 1

    def reset(self) -> None:
        """Drop all temporal object tracks for a new camera acquisition."""

        self._tracks.clear()
        self._next_track_id = 1

    def update(self, detections: list[ObjectDetection]) -> list[ObjectDetection]:
        """Return current detections plus short-lived tracked predictions."""

        if self.max_stale_frames <= 0:
            return [
                _with_tracking(detection, track_id=None, tracking_state="detected", stale_frames=0)
                for detection in detections
            ]

        matches, unmatched_detection_indices, unmatched_track_ids = self._match_detections(detections)
        output: list[ObjectDetection] = []

        for detection_index, track_id in matches:
            detection = detections[detection_index]
            track = self._tracks[track_id]
            predicted_box = _translate_box(track.xyxy, track.velocity)
            smoothed_box = _smooth_xyxy(predicted_box, detection.xyxy, self.smoothing)
            previous_center = _box_center(track.xyxy)
            current_center = _box_center(smoothed_box)
            track.velocity = (
                current_center[0] - previous_center[0],
                current_center[1] - previous_center[1],
            )
            track.xyxy = smoothed_box
            track.label = detection.label
            track.confidence = max(float(detection.confidence), track.confidence * self.confidence_decay)
            track.z_distance = detection.z_distance
            track.missed_frames = 0
            output.append(
                _with_tracking(
                    detection,
                    track_id=track_id,
                    tracking_state="detected",
                    stale_frames=0,
                    xyxy=smoothed_box,
                    confidence=track.confidence,
                )
            )

        for detection_index in unmatched_detection_indices:
            detection = detections[detection_index]
            track_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[track_id] = ObjectTrackState(
                track_id=track_id,
                label=detection.label,
                confidence=float(detection.confidence),
                xyxy=detection.xyxy,
                z_distance=detection.z_distance,
            )
            output.append(
                _with_tracking(
                    detection,
                    track_id=track_id,
                    tracking_state="detected",
                    stale_frames=0,
                )
            )

        expired: list[int] = []
        for track_id in unmatched_track_ids:
            track = self._tracks.get(track_id)
            if track is None:
                continue
            track.missed_frames += 1
            if track.missed_frames > self.max_stale_frames:
                expired.append(track_id)
                continue
            track.xyxy = _translate_box(track.xyxy, track.velocity)
            track.confidence *= self.confidence_decay
            output.append(
                ObjectDetection(
                    label=track.label,
                    confidence=track.confidence,
                    xyxy=track.xyxy,
                    z_distance=track.z_distance,
                    track_id=track.track_id,
                    tracking_state="tracked",
                    stale_frames=track.missed_frames,
                )
            )

        for track_id in expired:
            self._tracks.pop(track_id, None)

        return sorted(output, key=lambda detection: (detection.track_id or 0, detection.stale_frames))

    def _match_detections(
        self,
        detections: list[ObjectDetection],
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        """Greedily match current YOLO boxes to active tracks."""

        candidate_pairs: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(detections):
            for track_id, track in self._tracks.items():
                if detection.label != track.label:
                    continue
                predicted_box = _translate_box(track.xyxy, track.velocity)
                iou = _box_iou(predicted_box, detection.xyxy)
                center_distance = point_distance(_box_center(predicted_box), detection.center)
                dynamic_center_limit = max(
                    self.max_center_distance,
                    _box_diagonal(predicted_box) * 2.25,
                    _box_diagonal(detection.xyxy) * 2.25,
                )
                if iou < self.min_iou and center_distance > dynamic_center_limit:
                    continue
                cost = center_distance - (iou * 80.0)
                candidate_pairs.append((cost, detection_index, track_id))

        matches: list[tuple[int, int]] = []
        used_detections: set[int] = set()
        used_tracks: set[int] = set()
        for _, detection_index, track_id in sorted(candidate_pairs, key=lambda item: item[0]):
            if detection_index in used_detections or track_id in used_tracks:
                continue
            used_detections.add(detection_index)
            used_tracks.add(track_id)
            matches.append((detection_index, track_id))

        unmatched_detection_indices = [
            index for index in range(len(detections)) if index not in used_detections
        ]
        unmatched_track_ids = [
            track_id for track_id in self._tracks if track_id not in used_tracks
        ]
        return matches, unmatched_detection_indices, unmatched_track_ids


@dataclass(frozen=True)
class NearestWeight:
    """Closest accepted object candidate to one body side."""

    candidate_index: int
    label: str
    confidence: float
    distance: float
    wrist_distance: float | None
    forearm_distance: float | None
    z_distance: float | None = None

    def as_payload(self) -> dict[str, Any]:
        """Return JSON-friendly nearest-object data."""

        return {
            "candidate_index": self.candidate_index,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "distance": round(self.distance, 2),
            "wrist_distance": None if self.wrist_distance is None else round(self.wrist_distance, 2),
            "forearm_distance": None if self.forearm_distance is None else round(self.forearm_distance, 2),
            "z_distance": None if self.z_distance is None else round(self.z_distance, 3),
        }


@dataclass(frozen=True)
class LimbVisibility:
    """Visible joints for one anatomical side."""

    shoulder: bool
    elbow: bool
    wrist: bool
    forearm: bool
    full_arm: bool

    def as_payload(self) -> dict[str, bool]:
        """Return the legacy joint-visibility payload."""

        return {
            "shoulder": self.shoulder,
            "elbow": self.elbow,
            "wrist": self.wrist,
            "forearm": self.forearm,
            "full_arm": self.full_arm,
        }


@dataclass(frozen=True)
class LimbSideContext:
    """Dumbbell association for one anatomical side."""

    joints_visible: LimbVisibility
    nearest_weight: NearestWeight | None
    dumbbell_near_wrist_or_forearm: bool

    def as_payload(self) -> dict[str, Any]:
        """Return the side context payload used by motion analysis."""

        return {
            "joints_visible": self.joints_visible.as_payload(),
            "nearest_weight": None if self.nearest_weight is None else self.nearest_weight.as_payload(),
            "dumbbell_near_wrist_or_forearm": self.dumbbell_near_wrist_or_forearm,
        }


@dataclass(frozen=True)
class ObjectContextPayload:
    """Typed object-detection section for one frame."""

    status: str
    detections: list[ObjectDetection]
    candidates: list[ObjectDetection]
    rejected: list[ObjectDetection]
    wearable_rejected: list[ObjectDetection]
    filters: ObjectDetectionFilters

    def as_payload(self) -> dict[str, Any]:
        """Return the legacy ``object_detection`` dictionary."""

        return {
            "status": self.status,
            "detections": [detection.as_payload() for detection in self.detections],
            "candidates": [detection.as_payload() for detection in self.candidates],
            "rejected": [detection.as_payload() for detection in self.rejected],
            "wearable_rejected": [detection.as_payload() for detection in self.wearable_rejected],
            "candidate_count": len(self.candidates),
            "accepted_count": len(self.detections),
            "rejected_count": len(self.rejected),
            "filters": self.filters.as_payload(),
        }


@dataclass(frozen=True)
class LimbsContextPayload:
    """Typed limb/object-use section for one frame."""

    usage: str
    engaged_sides: list[str]
    sides: dict[str, LimbSideContext]
    torso_scale: float | None = None
    note: str = "Forearm means the elbow-to-wrist segment because COCO pose has no separate forearm keypoint."

    def as_payload(self) -> dict[str, Any]:
        """Return the legacy ``limbs`` dictionary."""

        return {
            "usage": self.usage,
            "engaged_sides": self.engaged_sides,
            "sides": {side: context.as_payload() for side, context in self.sides.items()},
            "torso_scale": None if self.torso_scale is None else round(self.torso_scale, 3),
            "note": self.note,
        }


@dataclass(frozen=True)
class BodyContextPayload:
    """Complete typed body/object context for one frame."""

    object_detection: ObjectContextPayload
    limbs: LimbsContextPayload

    def as_payload(self) -> dict[str, Any]:
        """Return the existing top-level dictionary shape."""

        return {
            "object_detection": self.object_detection.as_payload(),
            "limbs": self.limbs.as_payload(),
        }


def point_distance(a: np.ndarray | tuple[float, float], b: np.ndarray | tuple[float, float]) -> float:
    """Return the straight-line distance between two 2D image points."""

    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    return sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def estimate_torso_scale(
    pose: PoseCandidate | None,
    min_confidence: float,
    config: BodyContextConfig = BODY_CONTEXT_CONFIG,
) -> float | None:
    """Estimate the per-frame body scale used by 2D-to-pseudo-3D normalization."""

    if pose is None:
        return None

    distances: list[float] = []
    for side in ("left", "right"):
        shoulder = get_point(pose, "shoulder", side, min_confidence)
        hip = get_point(pose, "hip", side, min_confidence)
        if shoulder is not None and hip is not None:
            distances.append(point_distance(shoulder, hip))

    if distances:
        return max(float(np.mean(distances)), 1.0)

    left_shoulder = get_point(pose, "shoulder", "left", min_confidence)
    right_shoulder = get_point(pose, "shoulder", "right", min_confidence)
    if left_shoulder is not None and right_shoulder is not None:
        return max(
            point_distance(left_shoulder, right_shoulder) * config.shoulder_width_to_torso_scale,
            1.0,
        )

    return config.fallback_torso_scale_px


def estimate_z_distance_from_area(
    area: float,
    reference_scale: float | None,
    config: BodyContextConfig = BODY_CONTEXT_CONFIG,
) -> float | None:
    """Return a normalized pseudo-depth proxy from bounding-box area.

    A monocular webcam cannot recover true metric Z. For game control, the
    useful signal is monotonic depth: larger projected object boxes are closer
    to the camera. The square root converts area back to an edge-length scale,
    then torso normalization makes the value less sensitive to user distance.
    """

    if reference_scale is None or reference_scale <= config.depth_epsilon or area <= 0.0:
        return None
    raw_depth = sqrt(area) / reference_scale
    return float(np.clip(raw_depth, config.z_distance_min, config.z_distance_max))


def point_to_segment_distance(
    point: np.ndarray | tuple[float, float],
    start: np.ndarray,
    end: np.ndarray,
) -> float:
    """Distance from a point to a forearm segment such as elbow-wrist."""

    point_arr = np.asarray(point, dtype=float)
    start_arr = np.asarray(start, dtype=float)
    end_arr = np.asarray(end, dtype=float)
    segment = end_arr - start_arr
    length_squared = float(np.dot(segment, segment))
    if length_squared == 0:
        return point_distance(point_arr, start_arr)
    t = float(np.clip(np.dot(point_arr - start_arr, segment) / length_squared, 0.0, 1.0))
    projection = start_arr + t * segment
    return point_distance(point_arr, projection)


def _box_center(xyxy: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _box_diagonal(xyxy: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = xyxy
    return float(np.hypot(max(0.0, x2 - x1), max(0.0, y2 - y1)))


def _box_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if intersection <= 0:
        return 0.0
    first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = first_area + second_area - intersection
    if union <= 0:
        return 0.0
    return float(intersection / union)


def _smooth_xyxy(
    previous: tuple[float, float, float, float],
    current: tuple[float, float, float, float],
    alpha: float,
) -> tuple[float, float, float, float]:
    return tuple(
        float(alpha * current_value + (1.0 - alpha) * previous_value)
        for previous_value, current_value in zip(previous, current, strict=True)
    )


def _translate_box(
    xyxy: tuple[float, float, float, float],
    velocity: tuple[float, float],
) -> tuple[float, float, float, float]:
    dx, dy = velocity
    x1, y1, x2, y2 = xyxy
    return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


def _with_tracking(
    detection: ObjectDetection,
    track_id: int | None,
    tracking_state: str,
    stale_frames: int,
    xyxy: tuple[float, float, float, float] | None = None,
    confidence: float | None = None,
) -> ObjectDetection:
    return ObjectDetection(
        label=detection.label,
        confidence=detection.confidence if confidence is None else confidence,
        xyxy=detection.xyxy if xyxy is None else xyxy,
        z_distance=detection.z_distance,
        rejection_reason=detection.rejection_reason,
        rejection_detail=detection.rejection_detail,
        track_id=track_id,
        tracking_state=tracking_state,
        stale_frames=stale_frames,
    )


def _filter_detection_list(
    detections: list[ObjectDetection],
    allowed_labels: set[str] | None,
    min_area: float | None,
    max_area: float | None,
) -> list[ObjectDetection]:
    filtered: list[ObjectDetection] = []
    for detection in detections:
        if allowed_labels and detection.label not in allowed_labels:
            continue
        if min_area is not None and detection.area < min_area:
            continue
        if max_area is not None and detection.area > max_area:
            continue
        filtered.append(detection)
    return filtered


def extract_object_detections(
    result,
    allowed_labels: set[str] | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    label_confidences: dict[str, float] | None = None,
    wrist_points: dict[str, np.ndarray] | None = None,
    image_shape: tuple[int, int, int] | None = None,
    wearable_area_ratio: float = BODY_CONTEXT_CONFIG.wearable_area_ratio,
    depth_reference_scale: float | None = None,
    return_rejected: bool = False,
) -> list[ObjectDetection] | tuple[list[ObjectDetection], list[ObjectDetection]]:
    """Extract boxes from an Ultralytics detection result.

    ``min_area`` filters very small boxes. This is useful in the lab scene
    because cabinet handles, watches, and other small dark objects can look
    similar to the current dumbbell/weight dataset.

    ``max_area`` filters boxes that are too large to be a small dumbbell in the
    current camera setup. This prevents shirts, furniture, or large body regions
    from being accepted as a dumbbell-like object.

    ``label_confidences`` allows stricter thresholds for classes that are more
    prone to false positives. In practice, the `weight` class should usually be
    stricter than the `dumbbell` class when small real dumbbells are used.

    ``wrist_points`` enables an extra wearable filter. A very small dumbbell or
    weight detection whose center nearly overlaps a visible wrist is treated as
    a smartwatch/wristband false positive instead of a usable carried weight.
    """

    if isinstance(result, list) and all(isinstance(item, ObjectDetection) for item in result):
        detections = _filter_detection_list(result, allowed_labels, min_area, max_area)
        return (detections, []) if return_rejected else detections

    if result is None or getattr(result, "boxes", None) is None:
        return ([], []) if return_rejected else []

    names = getattr(result, "names", {}) or {}
    detections: list[ObjectDetection] = []
    rejected: list[ObjectDetection] = []
    boxes = result.boxes
    if boxes.xyxy is None:
        return (detections, rejected) if return_rejected else detections

    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy() if boxes.conf is not None else np.ones(len(xyxy))
    cls = boxes.cls.cpu().numpy() if boxes.cls is not None else np.zeros(len(xyxy))

    for box, score, class_id in zip(xyxy, conf, cls):
        label = str(names.get(int(class_id), int(class_id)))
        if allowed_labels and label not in allowed_labels:
            continue
        if label_confidences and float(score) < label_confidences.get(label, 0.0):
            continue
        x1, y1, x2, y2 = [float(value) for value in box]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        z_distance = estimate_z_distance_from_area(area, depth_reference_scale)
        detection = ObjectDetection(
            label=label,
            confidence=float(score),
            xyxy=(x1, y1, x2, y2),
            z_distance=z_distance,
        )
        wearable_detail = classify_wearable_false_positive(
            detection,
            wrist_points=wrist_points,
            image_shape=image_shape,
            max_area_ratio=wearable_area_ratio,
        )
        if wearable_detail is not None:
            rejected.append(
                ObjectDetection(
                    label=label,
                    confidence=float(score),
                    xyxy=(x1, y1, x2, y2),
                    z_distance=z_distance,
                    rejection_reason="wearable_wrist_overlap",
                    rejection_detail=wearable_detail,
                )
            )
            continue
        if min_area is not None and area < min_area:
            continue
        if max_area is not None and area > max_area:
            continue
        detections.append(detection)
    return (detections, rejected) if return_rejected else detections


def classify_wearable_false_positive(
    detection: ObjectDetection,
    wrist_points: dict[str, np.ndarray] | None,
    image_shape: tuple[int, int, int] | None,
    max_area_ratio: float = BODY_CONTEXT_CONFIG.wearable_area_ratio,
) -> WearableRejectionDetail | None:
    """Return rejection details when a small object overlaps a wrist.

    A smartwatch can look like a tiny dark dumbbell/weight box. This filter is
    intentionally strict: it only rejects boxes that are both very small and
    centered almost directly on a visible wrist.
    """

    if detection.label not in {"dumbbell", "weight"}:
        return None
    if not wrist_points or image_shape is None:
        return None

    frame_height, frame_width = image_shape[:2]
    frame_area = float(max(frame_width * frame_height, 1))
    area_ratio = detection.area / frame_area
    if area_ratio >= max_area_ratio:
        return None

    box_scale = sqrt(max(detection.area, 1.0))
    overlap_threshold = float(
        np.clip(
            box_scale * BODY_CONTEXT_CONFIG.wearable_overlap_scale,
            BODY_CONTEXT_CONFIG.wearable_overlap_min_px,
            BODY_CONTEXT_CONFIG.wearable_overlap_max_px,
        )
    )
    nearest_side = None
    nearest_distance = None
    for side, wrist in wrist_points.items():
        distance = point_distance(detection.center, wrist)
        if nearest_distance is None or distance < nearest_distance:
            nearest_side = side
            nearest_distance = distance

    if nearest_side is None or nearest_distance is None or nearest_distance > overlap_threshold:
        return None

    return WearableRejectionDetail(
        matched_wrist_side=nearest_side,
        wrist_distance=nearest_distance,
        overlap_threshold=overlap_threshold,
        area_ratio=area_ratio,
        max_area_ratio=max_area_ratio,
    )


def build_body_context(
    pose: PoseCandidate | None,
    object_result=None,
    min_confidence: float = 0.25,
    max_wrist_distance: float = 90.0,
    max_forearm_distance: float = 70.0,
    image_shape: tuple[int, int, int] | None = None,
    min_object_area_ratio: float = 0.0,
    max_object_area_ratio: float = 0.12,
    label_confidences: dict[str, float] | None = None,
    require_body_match: bool = True,
    object_tracker: ObjectTemporalTracker | None = None,
) -> dict[str, Any]:
    """Describe visible limbs and whether dumbbells are near each side.

    COCO pose does not provide a forearm keypoint. In this project, "forearm"
    means the segment between elbow and wrist.
    """

    min_area = None
    max_area = None
    if image_shape is not None and min_object_area_ratio > 0:
        height, width = image_shape[:2]
        min_area = float(height * width * min_object_area_ratio)
    if image_shape is not None and max_object_area_ratio > 0:
        height, width = image_shape[:2]
        max_area = float(height * width * max_object_area_ratio)

    wrist_points: dict[str, np.ndarray] = {}
    if pose is not None:
        for side in ("left", "right"):
            wrist = get_point(pose, "wrist", side, min_confidence)
            if wrist is not None:
                wrist_points[side] = wrist

    torso_scale = estimate_torso_scale(pose, min_confidence)

    object_candidates, wearable_rejections = extract_object_detections(
        object_result,
        {"dumbbell", "weight"},
        min_area=min_area,
        max_area=max_area,
        label_confidences=label_confidences,
        wrist_points=wrist_points,
        image_shape=image_shape,
        depth_reference_scale=torso_scale,
        return_rejected=True,
    )
    if object_tracker is not None:
        object_candidates = object_tracker.update(object_candidates)

    sides: dict[str, LimbSideContext] = {}
    engaged_sides: list[str] = []
    accepted_indices: set[int] = set()

    for side in ("left", "right"):
        shoulder = get_point(pose, "shoulder", side, min_confidence) if pose is not None else None
        elbow = get_point(pose, "elbow", side, min_confidence) if pose is not None else None
        wrist = get_point(pose, "wrist", side, min_confidence) if pose is not None else None

        joints = LimbVisibility(
            shoulder=shoulder is not None,
            elbow=elbow is not None,
            wrist=wrist is not None,
            forearm=elbow is not None and wrist is not None,
            full_arm=shoulder is not None and elbow is not None and wrist is not None,
        )

        nearest: NearestWeight | None = None
        for index, detection in enumerate(object_candidates):
            center = detection.center
            wrist_distance = (
                point_distance(center, wrist)
                if wrist is not None
                else None
            )
            forearm_distance = (
                point_to_segment_distance(center, elbow, wrist)
                if elbow is not None and wrist is not None
                else None
            )

            distances = [value for value in (wrist_distance, forearm_distance) if value is not None]
            if not distances:
                continue
            best_distance = min(distances)
            if nearest is None or best_distance < nearest.distance:
                nearest = NearestWeight(
                    candidate_index=index,
                    label=detection.label,
                    confidence=detection.confidence,
                    distance=best_distance,
                    wrist_distance=wrist_distance,
                    forearm_distance=forearm_distance,
                    z_distance=detection.z_distance,
                )

        dumbbell_near = False
        if nearest is not None:
            wrist_ok = nearest.wrist_distance is not None and nearest.wrist_distance <= max_wrist_distance
            forearm_ok = nearest.forearm_distance is not None and nearest.forearm_distance <= max_forearm_distance
            dumbbell_near = wrist_ok or forearm_ok

        if dumbbell_near:
            engaged_sides.append(side)
            accepted_indices.add(nearest.candidate_index)

        sides[side] = LimbSideContext(
            joints_visible=joints,
            nearest_weight=nearest,
            dumbbell_near_wrist_or_forearm=dumbbell_near,
        )

    accepted_detections = [
        detection for index, detection in enumerate(object_candidates) if not require_body_match or index in accepted_indices
    ]
    unmatched_rejections = [
        detection for index, detection in enumerate(object_candidates) if require_body_match and index not in accepted_indices
    ]
    rejected_detections = [*wearable_rejections, *unmatched_rejections]

    if object_result is None:
        usage = "unknown"
    elif len(engaged_sides) == 2:
        usage = "both"
    elif len(engaged_sides) == 1:
        usage = engaged_sides[0]
    else:
        usage = "none"

    if object_result is None:
        object_status = "not_run"
    elif accepted_detections:
        object_status = (
            "tracked"
            if all(detection.tracking_state == "tracked" for detection in accepted_detections)
            else "detected"
        )
    elif object_candidates:
        object_status = "candidates_only"
    else:
        object_status = "none_detected"

    return BodyContextPayload(
        object_detection=ObjectContextPayload(
            status=object_status,
            detections=accepted_detections,
            candidates=object_candidates,
            rejected=rejected_detections,
            wearable_rejected=wearable_rejections,
            filters=ObjectDetectionFilters(
                min_area_ratio=min_object_area_ratio,
                max_area_ratio=max_object_area_ratio,
                label_confidences=label_confidences or {},
                require_body_match=require_body_match,
            ),
        ),
        limbs=LimbsContextPayload(
            usage=usage,
            engaged_sides=engaged_sides,
            sides=sides,
            torso_scale=torso_scale,
        ),
    ).as_payload()
