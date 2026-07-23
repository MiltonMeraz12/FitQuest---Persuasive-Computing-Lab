"""Regression checks for the Garmin Connect IQ HTTP bridge normalizer."""

from __future__ import annotations

from tools.garmin_connectiq_http_bridge import normalize_connectiq_payload, sanitize_heart_rate_bpm


def test_plausible_heart_rate_passes_through() -> None:
    payload = normalize_connectiq_payload({"heart_rate_bpm": 132})

    assert payload["heart_rate_bpm"] == 132


def test_garbage_heart_rate_is_dropped_instead_of_propagated() -> None:
    payload = normalize_connectiq_payload({"heart_rate_bpm": 99999})

    assert "heart_rate_bpm" not in payload


def test_non_numeric_heart_rate_is_dropped() -> None:
    payload = normalize_connectiq_payload({"heart_rate_bpm": "not-a-number"})

    assert "heart_rate_bpm" not in payload


def test_sanitize_heart_rate_bpm_boundaries() -> None:
    assert sanitize_heart_rate_bpm(20) == 20
    assert sanitize_heart_rate_bpm(240) == 240
    assert sanitize_heart_rate_bpm(19) is None
    assert sanitize_heart_rate_bpm(241) is None
    assert sanitize_heart_rate_bpm(None) is None
