"""Regression checks for optional temporal dumbbell tracking."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ironquest.body_context import ObjectDetection, ObjectTemporalTracker


def _detection(x1: float, y1: float, x2: float, y2: float) -> ObjectDetection:
    return ObjectDetection(
        label="dumbbell",
        confidence=0.8,
        xyxy=(x1, y1, x2, y2),
    )


def test_tracker_holds_short_detector_dropouts() -> None:
    tracker = ObjectTemporalTracker(max_stale_frames=2, smoothing=1.0, max_center_distance=80.0)

    first = tracker.update([_detection(100.0, 100.0, 140.0, 140.0)])
    assert len(first) == 1
    assert first[0].tracking_state == "detected"
    assert first[0].track_id == 1

    held = tracker.update([])
    assert len(held) == 1
    assert held[0].tracking_state == "tracked"
    assert held[0].stale_frames == 1
    assert held[0].track_id == 1

    reacquired = tracker.update([_detection(112.0, 100.0, 152.0, 140.0)])
    assert len(reacquired) == 1
    assert reacquired[0].tracking_state == "detected"
    assert reacquired[0].stale_frames == 0
    assert reacquired[0].track_id == 1


def test_tracker_expires_after_hold_window() -> None:
    tracker = ObjectTemporalTracker(max_stale_frames=1)

    tracker.update([_detection(100.0, 100.0, 140.0, 140.0)])
    assert tracker.update([])[0].tracking_state == "tracked"
    assert tracker.update([]) == []


if __name__ == "__main__":
    test_tracker_holds_short_detector_dropouts()
    test_tracker_expires_after_hold_window()
    print("object temporal tracking tests passed")
