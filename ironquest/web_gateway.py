"""Small local HTTP/SSE gateway for the FitQuest browser client.

The detector owns the camera and sensors. This module only publishes the
already-normalised frame payload and an annotated JPEG preview to a browser.
It intentionally uses the Python standard library so the web demo does not
need a second application framework or a database.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB_ROOT = PROJECT_ROOT / "web"


def _json_default(value: Any) -> Any:
    """Convert common scientific Python scalar values to JSON values."""

    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, Path):
        return str(value)
    return str(value)


class WebStream:
    """Thread-safe latest-value stream used by SSE and MJPEG clients."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._sequence = 0
        self._latest_event: dict[str, Any] | None = None
        self._latest_jpeg: bytes | None = None
        self._closed = False
        self._controls: queue.Queue[str] = queue.Queue()

    @property
    def sequence(self) -> int:
        with self._condition:
            return self._sequence

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def publish(self, payload: dict[str, Any], frame: Any | None = None) -> None:
        """Publish one sensor-fusion payload and optional BGR preview frame."""

        encoded_frame: bytes | None = None
        if frame is not None:
            try:
                preview = frame
                height, width = preview.shape[:2]
                if width > 960:
                    scale = 960.0 / float(width)
                    preview = cv2.resize(preview, (960, max(1, int(height * scale))))
                ok, encoded = cv2.imencode(
                    ".jpg",
                    preview,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 82],
                )
                if ok:
                    encoded_frame = encoded.tobytes()
            except Exception:
                encoded_frame = None

        with self._condition:
            self._sequence += 1
            self._latest_event = {
                "type": "game_control",
                "sequence": self._sequence,
                "published_at_unix": round(time.time(), 3),
                "payload": payload,
            }
            if encoded_frame is not None:
                self._latest_jpeg = encoded_frame
            self._condition.notify_all()

    def wait_for_event(self, after_sequence: int, timeout: float = 15.0) -> dict[str, Any] | None:
        """Return the newest event after ``after_sequence`` or ``None`` on timeout/close."""

        with self._condition:
            if self._sequence <= after_sequence and not self._closed:
                self._condition.wait(timeout=max(0.05, timeout))
            if self._closed:
                return None
            if self._latest_event is None or self._sequence <= after_sequence:
                return None
            return self._latest_event

    def wait_for_jpeg(self, after_sequence: int, timeout: float = 15.0) -> tuple[int, bytes] | None:
        """Return the newest encoded preview after ``after_sequence``."""

        with self._condition:
            if self._sequence <= after_sequence and not self._closed:
                self._condition.wait(timeout=max(0.05, timeout))
            if self._closed or self._latest_jpeg is None or self._sequence <= after_sequence:
                return None
            return self._sequence, self._latest_jpeg

    def latest(self) -> dict[str, Any] | None:
        """Return the latest JSON-safe event for health/debug endpoints."""

        with self._condition:
            if self._latest_event is None:
                return None
            return self._latest_event

    def enqueue_control(self, action: str) -> None:
        """Queue a browser control for the owning detector thread."""

        self._controls.put(action)

    def poll_controls(self, limit: int = 8) -> list[str]:
        """Return pending browser controls without running them in HTTP threads."""

        actions: list[str] = []
        for _ in range(max(1, int(limit))):
            try:
                actions.append(self._controls.get_nowait())
            except queue.Empty:
                break
        return actions

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class _GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, publisher: WebStream, web_root: Path):
        self.publisher = publisher
        self.web_root = web_root
        super().__init__(address, handler)

    def handle_error(self, request, client_address) -> None:
        """Ignore normal browser disconnects without hiding real server errors."""

        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
            return
        if getattr(error, "winerror", None) == 10053:
            return
        super().handle_error(request, client_address)


class _GatewayRequestHandler(BaseHTTPRequestHandler):
    """Serve the static client, SSE sensor frames, and MJPEG preview."""

    server: _GatewayServer

    def log_message(self, format: str, *args: object) -> None:
        """Keep per-frame browser polling out of the detector terminal."""

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self._send_json({"error": "not_found", "path": str(path.name)}, status=404)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler API
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in {"/", "/fitquest_game.html"}:
            self._send_file(self.server.web_root / "fitquest_game.html")
            return
        if path == "/demo_game_control.jsonl":
            self._send_file(self.server.web_root / "demo_game_control.jsonl")
            return
        if path == "/api/health":
            latest = self.server.publisher.latest()
            self._send_json(
                {
                    "status": "ok",
                    "stream": "live" if latest else "waiting",
                    "sequence": self.server.publisher.sequence,
                    "endpoints": {
                        "events": "/events",
                        "preview": "/preview.mjpg",
                    },
                }
            )
            return
        if path == "/api/latest":
            latest = self.server.publisher.latest()
            if latest is None:
                self._send_json({"status": "waiting"}, status=404)
            else:
                self._send_json(latest)
            return
        if path == "/events":
            self._serve_events()
            return
        if path == "/preview.mjpg":
            self._serve_preview()
            return

        self._send_json({"error": "not_found", "path": path}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP handler API
        """Accept small lifecycle requests for the owning detector loop."""

        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path != "/api/control":
            self._send_json({"error": "not_found", "path": path}, status=404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > 4096:
            self._send_json(
                {"error": "invalid_request", "detail": "Expected a small JSON control body."},
                status=400,
            )
            return
        try:
            request = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "invalid_json"}, status=400)
            return
        action = request.get("action") if isinstance(request, dict) else None
        if action not in {"calibrate", "reset_session"}:
            self._send_json({"error": "unsupported_action"}, status=400)
            return
        self.server.publisher.enqueue_control(action)
        self._send_json({"status": "accepted", "action": action})

    def _serve_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_sequence = 0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                event = self.server.publisher.wait_for_event(last_sequence, timeout=15.0)
                if event is None:
                    if self.server.publisher.closed:
                        break
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    if self.server.publisher.sequence == 0:
                        continue
                    if self.server.publisher.latest() is None:
                        break
                    continue
                last_sequence = int(event["sequence"])
                body = json.dumps(event, default=_json_default, separators=(",", ":"))
                self.wfile.write(f"data: {body}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _serve_preview(self) -> None:
        boundary = b"--fitquest-frame\r\n"
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=fitquest-frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_sequence = 0
        try:
            while True:
                result = self.server.publisher.wait_for_jpeg(last_sequence, timeout=15.0)
                if result is None:
                    if self.server.publisher.closed:
                        break
                    if self.server.publisher.sequence == 0:
                        continue
                    if self.server.publisher.latest() is None:
                        break
                    continue
                last_sequence, jpeg = result
                self.wfile.write(boundary)
                self.wfile.write(f"Content-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


class WebGateway:
    """Run the local browser gateway beside ``PipelineRunner``."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8787, web_root: Path | None = None):
        self.host = host
        self.port = port
        self.web_root = (web_root or DEFAULT_WEB_ROOT).resolve()
        self.publisher = WebStream()
        self._server: _GatewayServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> None:
        """Start the HTTP server in a daemon thread."""

        if self._server is not None:
            return
        if not (self.web_root / "fitquest_game.html").is_file():
            raise FileNotFoundError(f"FitQuest web client not found: {self.web_root / 'fitquest_game.html'}")
        self._server = _GatewayServer(
            (self.host, self.port),
            _GatewayRequestHandler,
            self.publisher,
            self.web_root,
        )
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, name="fitquest-web", daemon=True)
        self._thread.start()

    def publish(self, payload: dict[str, Any], frame: Any | None = None) -> None:
        self.publisher.publish(payload, frame)

    def poll_controls(self, limit: int = 8) -> list[str]:
        """Return browser lifecycle requests for the detector thread."""

        return self.publisher.poll_controls(limit)

    def close(self) -> None:
        self.publisher.close()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
