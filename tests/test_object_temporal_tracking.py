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
    # Isolates pure frame-count expiry by disabling the wall-clock floor.
    tracker = ObjectTemporalTracker(max_stale_frames=1, max_stale_seconds=0)

    tracker.update([_detection(100.0, 100.0, 140.0, 140.0)])
    assert tracker.update([])[0].tracking_state == "tracked"
    assert tracker.update([]) == []


def test_tracker_time_floor_extends_hold_beyond_frame_count() -> None:
    # A real webcam frame misses a held dumbbell for more than a couple of
    # frames fairly often (hands crossing, brief occlusion). The wall-clock
    # floor keeps a track alive for at least max_stale_seconds regardless of
    # how tight max_stale_frames is, so a fast camera doesn't collapse the
    # grace period down to a few milliseconds.
    tracker = ObjectTemporalTracker(max_stale_frames=1, max_stale_seconds=1.0)
    start = 1000.0

    tracker.update([_detection(100.0, 100.0, 140.0, 140.0)], now=start)
    # Well past the frame budget (missed_frames reaches 5), but still inside
    # the 1.0s time floor -- must not expire yet.
    for step in range(1, 6):
        result = tracker.update([], now=start + step * 0.1)
        assert result[0].tracking_state == "tracked", f"expired too early at step {step}"

    # Once the time floor is also exceeded, the track expires.
    assert tracker.update([], now=start + 1.5) == []


def test_tracker_frame_budget_still_bounds_a_stalled_slow_camera() -> None:
    # On a very slow camera, "a couple of frames" can span far longer than
    # the time floor; the frame budget still caps how long a track survives
    # so a genuinely gone object does not linger forever.
    tracker = ObjectTemporalTracker(max_stale_frames=2, max_stale_seconds=0.5)
    start = 2000.0

    tracker.update([_detection(100.0, 100.0, 140.0, 140.0)], now=start)
    assert tracker.update([], now=start + 5.0)[0].tracking_state == "tracked"
    assert tracker.update([], now=start + 10.0)[0].tracking_state == "tracked"
    assert tracker.update([], now=start + 15.0) == []


if __name__ == "__main__":
    test_tracker_holds_short_detector_dropouts()
    test_tracker_expires_after_hold_window()
    test_tracker_time_floor_extends_hold_beyond_frame_count()
    test_tracker_frame_budget_still_bounds_a_stalled_slow_camera()
    print("object temporal tracking tests passed")
