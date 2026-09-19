"""Optional HTTP health/readiness surface for the LiveKit worker process (F-M25).

Disabled unless ``UVA_WORKER_HEALTH_PORT`` is a positive integer. Default bind is
``127.0.0.1`` (``UVA_WORKER_HEALTH_BIND``); use ``0.0.0.0`` for container probes.

Endpoints (stdlib ``http.server``, daemon thread — no FastAPI dependency):

- ``GET /healthz`` — liveness (process up)
- ``GET /healthz/ready`` — LiveKit env present, VAD prewarmed, DB ``SELECT 1``
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("worker.health_http")

_SERVICE = "uva-worker"
_vad_ready = False
_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None


def set_vad_ready(ready: bool = True) -> None:
    """Called from ``prewarm()`` after Silero loads (or fails → leave False)."""
    global _vad_ready
    _vad_ready = bool(ready)


def vad_is_ready() -> bool:
    return _vad_ready


def health_port() -> int | None:
    """Return configured port, or None when health HTTP is disabled."""
    raw = (os.getenv("UVA_WORKER_HEALTH_PORT") or "").strip()
    if not raw or raw in {"0", "false", "no", "off"}:
        return None
    try:
        port = int(raw)
    except ValueError:
        logger.warning("stage=health_port invalid UVA_WORKER_HEALTH_PORT=%r", raw)
        return None
    if port <= 0 or port > 65535:
        logger.warning("stage=health_port out of range port=%s", port)
        return None
    return port


def health_bind() -> str:
    return (os.getenv("UVA_WORKER_HEALTH_BIND") or "127.0.0.1").strip() or "127.0.0.1"


def livekit_credentials_configured() -> bool:
    return bool(
        (os.getenv("LIVEKIT_URL") or "").strip()
        and (os.getenv("LIVEKIT_API_KEY") or "").strip()
        and (os.getenv("LIVEKIT_API_SECRET") or "").strip()
    )


def check_database() -> tuple[str, bool]:
    """Return ``(status_label, ok)`` for readiness.

    Label is intentionally coarse (F-M5) — never return raw driver/host text to the probe.
    """
    try:
        from worker.db_pool import worker_db_connection

        with worker_db_connection(connect_timeout=3) as conn:
            conn.execute("select 1").fetchone()
        return "connected", True
    except Exception as exc:
        logger.warning("stage=health_db_check failed err=%s", exc)
        return "failed", False


def liveness_payload() -> dict[str, Any]:
    return {"status": "ok", "service": _SERVICE}


def readiness_payload() -> tuple[dict[str, Any], int]:
    """Build readiness body + HTTP status (200 healthy, 503 unhealthy)."""
    lk_ok = livekit_credentials_configured()
    vad_ok = vad_is_ready()
    db_label, db_ok = check_database()

    healthy = lk_ok and vad_ok and db_ok
    body: dict[str, Any] = {
        "status": "healthy" if healthy else "unhealthy",
        "service": _SERVICE,
        "livekit": "configured" if lk_ok else "missing_credentials",
        "vad": "loaded" if vad_ok else "not_loaded",
        "database": db_label,
    }
    return body, (200 if healthy else 503)


class _HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        logger.debug("health_http %s", fmt % args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/healthz":
            self._send_json(200, liveness_payload())
            return
        if path in ("/healthz/ready", "/healthz/ready/"):
            body, code = readiness_payload()
            self._send_json(code, body)
            return
        self._send_json(404, {"status": "not_found", "service": _SERVICE})


def start_health_server_if_configured() -> threading.Thread | None:
    """Start daemon health server when port is set. Idempotent."""
    global _server, _server_thread
    if _server_thread is not None and _server_thread.is_alive():
        return _server_thread

    port = health_port()
    if port is None:
        return None

    bind = health_bind()
    try:
        server = ThreadingHTTPServer((bind, port), _HealthHandler)
    except OSError as exc:
        logger.error(
            "stage=health_http_bind failed bind=%s port=%s err=%s",
            bind,
            port,
            exc,
        )
        return None

    _server = server
    thread = threading.Thread(
        target=server.serve_forever,
        name="uva-worker-health",
        daemon=True,
    )
    thread.start()
    _server_thread = thread
    logger.info(
        "worker health HTTP listening bind=%s port=%s paths=/healthz,/healthz/ready",
        bind,
        port,
    )
    return thread


def stop_health_server() -> None:
    """Test helper — shut down the daemon server if running."""
    global _server, _server_thread
    if _server is not None:
        try:
            _server.shutdown()
        except Exception as exc:
            logger.warning("stage=health_http_shutdown failed err=%s", exc)
        _server = None
    _server_thread = None
