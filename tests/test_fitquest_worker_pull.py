import json
import time

from tools import fitquest_worker_pull


class _Response:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


def test_fetch_latest_uses_a_named_client_identity(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({"status": "waiting", "project": "FitQuest"})

    monkeypatch.setattr(fitquest_worker_pull, "urlopen", fake_urlopen)

    assert fitquest_worker_pull.fetch_latest("https://example.workers.dev", 3.0) is None
    assert captured["request"].get_header("User-agent") == "FitQuest-Puller/1.0"
    assert captured["request"].full_url.endswith("/latest")
    assert captured["timeout"] == 3.0


def test_sample_identity_does_not_change_while_worker_repeats_one_sample():
    sample = {"sequence": 7, "bridge_received_epoch_ms": 1234567890}

    assert fitquest_worker_pull.sample_identity(sample) == fitquest_worker_pull.sample_identity(dict(sample))
    assert fitquest_worker_pull.sample_identity(sample) != fitquest_worker_pull.sample_identity(
        {**sample, "bridge_received_epoch_ms": 1234567891}
    )


def test_write_json_atomic_preserves_remote_receive_time(tmp_path):
    path = tmp_path / "wearable.json"
    received_epoch_ms = int((time.time() - 30) * 1000)

    fitquest_worker_pull.write_json_atomic(
        path,
        {"status": "connected", "bridge_received_epoch_ms": received_epoch_ms},
    )

    assert time.time() - path.stat().st_mtime >= 29
