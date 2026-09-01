"""Loopback-only HTTP control API for the live restream path.

Bind is locked to 127.0.0.1:8788. HOST=0.0.0.0 (and any non-loopback /
LAN / hotspot address) is refused with a non-zero exit. Responses never
echo rtmp_url or rtmp_key. There is no /api/clip route.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import socketserver
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from retrans.config import DEFAULT_PORT, HOST_ENV, LOOPBACK_HOST, PORT_ENV, redact
from retrans.ingest import NotLiveError, ResolveError, StreamResolver
from retrans.outputs.x import RestreamError, XLiveRestream, join_rtmp_destination

MAX_BODY = 64 * 1024
VALID_STATES = ("idle", "starting", "live", "error", "stopped")


class BindRefused(RuntimeError):
    """Serve would bind off-loopback. Exit non-zero; do not listen."""


class AlreadyRunning(RuntimeError):
    """A live restream is already starting or live."""


def normalize_bind_host(host: str | None) -> str:
    """Accept only 127.0.0.1 / localhost. Refuse 0.0.0.0 and LAN/hotspot."""
    if host is None:
        raw = os.environ.get(HOST_ENV, LOOPBACK_HOST)
    else:
        raw = host
    raw = (raw or "").strip()
    if not raw:
        raw = LOOPBACK_HOST
    lowered = raw.lower().strip("[]")
    refused = {
        "0.0.0.0",
        "::",
        "*",
        "0",
        "::0",
        "0:0:0:0:0:0:0:0",
    }
    if lowered in refused:
        raise BindRefused(
            f"refusing to bind HOST={raw}; retrans serve is loopback-only "
            f"({LOOPBACK_HOST}:{DEFAULT_PORT})"
        )
    if lowered in {LOOPBACK_HOST, "localhost"}:
        return LOOPBACK_HOST
    raise BindRefused(
        f"refusing to bind HOST={raw}; retrans serve is loopback-only "
        f"({LOOPBACK_HOST}:{DEFAULT_PORT})"
    )


def resolve_bind_port(port: int | None) -> int:
    if port is not None:
        return int(port)
    env = os.environ.get(PORT_ENV)
    if env:
        return int(env)
    return DEFAULT_PORT


def ensure_loopback_bind(host: str, port: int) -> None:
    """Fail closed if getaddrinfo would yield a non-loopback address."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BindRefused(f"cannot resolve bind address {host!r}: {exc}") from exc
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_loopback:
            raise BindRefused(
                f"refusing to bind {host} ({ip}); retrans serve is loopback-only "
                f"({LOOPBACK_HOST}:{DEFAULT_PORT})"
            )


class LiveController:
    """In-process live session. Status never includes RTMP credentials."""

    def __init__(self, restream_factory: Callable[[], XLiveRestream] | None = None) -> None:
        self._factory = restream_factory or XLiveRestream
        self._lock = threading.Lock()
        self._state = "idle"
        self._source_url: str | None = None
        self._error: str | None = None
        self._job: XLiveRestream | None = None
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._state in {"starting", "live"}

    def public_status(self) -> dict[str, Any]:
        with self._lock:
            self._reconcile_dead_process_locked()
            return {
                "ok": True,
                "state": self._state,
                "source_url": self._source_url,
                "error": self._error,
            }

    def _reconcile_dead_process_locked(self) -> None:
        """If status claims live/starting but ffmpeg already exited, flip to error.

        Covers a late wait() thread: GET /api/live/status must not stay live.
        Operator stop() sets state=stopped first, so it is not treated as error.
        """
        if self._state not in {"starting", "live"}:
            return
        job = self._job
        if job is None:
            return
        poll = getattr(job, "poll", None)
        if not callable(poll):
            return
        if poll() is None:
            return
        self._state = "error"
        error_fn = getattr(job, "ffmpeg_exit_error", None)
        message = error_fn() if callable(error_fn) else "ffmpeg restream exited"
        self._error = message or "ffmpeg restream exited"

    def start(self, source_url: str, rtmp_url: str, rtmp_key: str) -> str:
        with self._lock:
            self._reconcile_dead_process_locked()
            if self.busy:
                raise AlreadyRunning("already running")
            self._state = "starting"
            self._source_url = source_url
            self._error = None
            job = self._factory()
            self._job = job
            thread = threading.Thread(
                target=self._run,
                args=(job, source_url, rtmp_url, rtmp_key),
                name="retrans-live",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return "starting"

    def stop(self) -> str:
        with self._lock:
            job = self._job
            self._state = "stopped"
            self._error = None
        if job is not None:
            job.stop()
        return "stopped"

    def _run(
        self,
        job: XLiveRestream,
        source_url: str,
        rtmp_url: str,
        rtmp_key: str,
    ) -> None:
        dest = ""
        try:
            dest = join_rtmp_destination(rtmp_url, rtmp_key)
            job.start(source_url, rtmp_url, rtmp_key)
            with self._lock:
                if self._state == "stopped":
                    job.stop()
                    return
                self._state = "live"
            job.wait()
            with self._lock:
                if self._state == "stopped":
                    return
                # Unexpected exit — including zero — is an error. A dead
                # restream must not look like a clean operator stop.
                if self._state != "error" or not self._error:
                    self._state = "error"
                    error_fn = getattr(job, "ffmpeg_exit_error", None)
                    if callable(error_fn):
                        self._error = error_fn() or "ffmpeg restream exited"
                    else:
                        self._error = "ffmpeg restream exited"
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                if self._state == "stopped":
                    return
                self._state = "error"
                self._error = redact(str(exc), rtmp_url, rtmp_key, dest)


def validate_start_payload(payload: Any) -> tuple[str, str, str] | str:
    """Return (source_url, rtmp_url, rtmp_key) or an error string."""
    if not isinstance(payload, dict):
        return "invalid fields"
    required = ("source_url", "rtmp_url", "rtmp_key")
    missing = [key for key in required if key not in payload]
    if missing:
        return f"missing fields: {', '.join(missing)}"
    values: dict[str, str] = {}
    for key in required:
        raw = payload[key]
        if not isinstance(raw, str) or not raw.strip():
            return f"invalid fields: {key}"
        values[key] = raw.strip()
    source = values["source_url"]
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid fields: source_url"
    try:
        join_rtmp_destination(values["rtmp_url"], values["rtmp_key"])
    except RestreamError:
        return "invalid fields: rtmp_url"
    return values["source_url"], values["rtmp_url"], values["rtmp_key"]


def _cors_origin(handler: BaseHTTPRequestHandler) -> str | None:
    """Allow only http://127.0.0.1 or http://localhost (optional port)."""
    origin = handler.headers.get("Origin", "")
    if not origin:
        return None
    parsed = urlparse(origin)
    if parsed.scheme != "http":
        return None
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return None
    return origin


def make_handler(
    controller: LiveController,
    resolver: StreamResolver | None = None,
) -> type[BaseHTTPRequestHandler]:
    stream_resolver = resolver or StreamResolver()

    class LiveAPIHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            origin = _cors_origin(self)
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            origin = _cors_origin(self)
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/api/live/status":
                self._send(404, {"ok": False, "error": "not found"})
                return
            self._send(200, controller.public_status())

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/api/live/stop":
                state = controller.stop()
                self._send(200, {"ok": True, "state": state})
                return
            if path != "/api/live/start":
                self._send(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(400, {"ok": False, "error": "invalid fields"})
                return
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8") or "null")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"ok": False, "error": "invalid fields"})
                return
            parsed = validate_start_payload(payload)
            if isinstance(parsed, str):
                self._send(400, {"ok": False, "error": parsed})
                return
            source_url, rtmp_url, rtmp_key = parsed
            # Reject VOD / non-live before LiveController.start — no ffmpeg/RTMP.
            try:
                stream_resolver.require_live(source_url)
            except (NotLiveError, ResolveError) as exc:
                self._send(400, {"ok": False, "error": str(exc)})
                return
            try:
                state = controller.start(source_url, rtmp_url, rtmp_key)
            except AlreadyRunning:
                status = controller.public_status()
                self._send(
                    409,
                    {
                        "ok": False,
                        "error": "already running",
                        "state": status["state"],
                    },
                )
                return
            self._send(200, {"ok": True, "state": state})

    return LiveAPIHandler


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_forever(
    host: str | None = None,
    port: int | None = None,
    controller: LiveController | None = None,
    resolver: StreamResolver | None = None,
) -> None:
    bind_host = normalize_bind_host(host)
    bind_port = resolve_bind_port(port)
    ensure_loopback_bind(bind_host, bind_port)
    httpd = ThreadingHTTPServer(
        (bind_host, bind_port),
        make_handler(controller or LiveController(), resolver=resolver),
    )
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
