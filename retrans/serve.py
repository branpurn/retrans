"""Loopback-only HTTP control API for the live restream path.

Bind is locked to 127.0.0.1:8788. HOST=0.0.0.0 (and any non-loopback /
LAN / hotspot address) is refused with a non-zero exit. Responses never
echo rtmp_url or rtmp_key. There is no /api/clip route.

Sign in: PUT /api/live/credentials (or env). Drop link: source_url.
Preview: GET /api/live/preview?source_url= (yt-dlp -J title + is_live; no ffmpeg).
Retrans: POST /api/live/start (fills RTMP from store when body omits it).
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
from urllib.parse import parse_qs, urlparse, urlsplit

from retrans.config import DEFAULT_PORT, HOST_ENV, LOOPBACK_HOST, PORT_ENV, redact
from retrans.credentials import (
    delete_credentials,
    is_configured,
    load_credentials,
    save_credentials,
)
from retrans.ingest import NotLiveError, ResolveError, StreamResolver
from retrans.outputs.x import RestreamError, XLiveRestream, join_rtmp_destination
from retrans.sources.youtube import is_youtube_url

MAX_BODY = 64 * 1024
VALID_STATES = ("idle", "starting", "live", "error", "stopped")
CORS_METHODS = "GET, PUT, POST, DELETE, OPTIONS"
NOT_CONFIGURED = (
    "RTMP credentials are not configured. "
    "PUT /api/live/credentials or set RETRANS_X_RTMP_URL and RETRANS_X_RTMP_KEY."
)


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
        self._generation = 0

    @property
    def busy(self) -> bool:
        return self._state in {"starting", "live"}

    def _owns_session_locked(self, job: XLiveRestream, generation: int) -> bool:
        """True only for the controller's current restream job/generation."""
        return self._job is job and self._generation == generation

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
            # error / stopped / idle may start again on this same serve process.
            # Bump generation so a leftover wait() thread cannot clobber us.
            self._generation += 1
            generation = self._generation
            self._state = "starting"
            self._source_url = source_url
            self._error = None
            job = self._factory()
            self._job = job
            thread = threading.Thread(
                target=self._run,
                args=(job, generation, source_url, rtmp_url, rtmp_key),
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
        generation: int,
        source_url: str,
        rtmp_url: str,
        rtmp_key: str,
    ) -> None:
        dest = ""
        try:
            dest = join_rtmp_destination(rtmp_url, rtmp_key)
            job.start(source_url, rtmp_url, rtmp_key)
            stop_self = False
            with self._lock:
                if not self._owns_session_locked(job, generation):
                    # Superseded by a newer start(); do not touch controller state.
                    stop_self = True
                elif self._state == "stopped":
                    stop_self = True
                else:
                    self._state = "live"
            if stop_self:
                job.stop()
                return
            job.wait()
            with self._lock:
                if not self._owns_session_locked(job, generation):
                    return
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
                if not self._owns_session_locked(job, generation):
                    return
                if self._state == "stopped":
                    return
                self._state = "error"
                self._error = redact(str(exc), rtmp_url, rtmp_key, dest)


def _nonempty_str(payload: dict[str, Any], key: str) -> str | None:
    raw = payload.get(key)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def validate_credentials_payload(payload: Any) -> tuple[str, str] | str:
    """Return (rtmp_url, rtmp_key) or an error string. Same RTMP rules as start."""
    if not isinstance(payload, dict):
        return "invalid fields"
    missing = [key for key in ("rtmp_url", "rtmp_key") if key not in payload]
    if missing:
        return f"missing fields: {', '.join(missing)}"
    url = _nonempty_str(payload, "rtmp_url")
    key = _nonempty_str(payload, "rtmp_key")
    if url is None:
        return "invalid fields: rtmp_url"
    if key is None:
        return "invalid fields: rtmp_key"
    try:
        join_rtmp_destination(url, key)
    except RestreamError:
        return "invalid fields: rtmp_url"
    return url, key


def parse_http_source_url(raw: str | None) -> str | None:
    """Accept a non-empty http(s) URL. None if missing or not http(s)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    source = raw.strip()
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return source


def validate_source_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    return parse_http_source_url(_nonempty_str(payload, "source_url"))


def preview_query_source_url(path_with_query: str) -> str | None:
    """Return source_url from GET query, or None if the key is absent."""
    qs = parse_qs(urlsplit(path_with_query).query, keep_blank_values=True)
    if "source_url" not in qs:
        return None
    return (qs["source_url"][0] or "").strip()


def _override_rtmp(payload: dict[str, Any]) -> tuple[str, str] | str | None:
    """Body rtmp_url/rtmp_key is a one-shot override. None if neither field is present."""
    has_url = "rtmp_url" in payload
    has_key = "rtmp_key" in payload
    if not has_url and not has_key:
        return None
    return validate_credentials_payload(payload)


def validate_start_payload(
    payload: Any,
    stored: tuple[str, str] | None = None,
) -> tuple[str, str, str] | str:
    """Return (source_url, rtmp_url, rtmp_key) or an error string.

    source_url is always required. rtmp_url/rtmp_key in the body are an
    optional one-shot override. Otherwise fill from stored/env.
    """
    if not isinstance(payload, dict):
        return "invalid fields"
    if "source_url" not in payload:
        return "missing fields: source_url"
    source = validate_source_url(payload)
    if source is None:
        return "invalid fields: source_url"
    override = _override_rtmp(payload)
    if isinstance(override, str):
        return override
    if override is not None:
        return source, override[0], override[1]
    if stored is not None:
        try:
            join_rtmp_destination(stored[0], stored[1])
        except RestreamError:
            return "invalid fields: rtmp_url"
        return source, stored[0], stored[1]
    return NOT_CONFIGURED


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
                self.send_header("Access-Control-Allow-Methods", CORS_METHODS)
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> tuple[Any, str | None]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return None, "invalid fields"
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw.decode("utf-8") or "null"), None
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None, "invalid fields"

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            origin = _cors_origin(self)
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", CORS_METHODS)
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/live/credentials":
                self._send(200, {"ok": True, "configured": is_configured()})
                return
            if path == "/api/live/preview":
                self._preview()
                return
            if path != "/api/live/status":
                self._send(404, {"ok": False, "error": "not found"})
                return
            self._send(200, controller.public_status())

        def _preview(self) -> None:
            """Drop-link preview: yt-dlp -J title + is_live. No ffmpeg / restream."""
            raw = preview_query_source_url(self.path)
            if raw is None or raw == "":
                self._send(400, {"ok": False, "error": "missing source_url"})
                return
            source = parse_http_source_url(raw)
            if source is None:
                self._send(400, {"ok": False, "error": "invalid source_url"})
                return
            if not is_youtube_url(source):
                self._send(400, {"ok": False, "error": "YouTube first"})
                return
            try:
                title, is_live = stream_resolver.preview_meta(source)
            except ResolveError as exc:
                # Probe failure is not VOD. Do not return 200 title="" is_live=false.
                self._send(502, {"ok": False, "error": str(exc)})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "source_url": source,
                    "title": title,
                    "is_live": is_live,
                },
            )

        def do_PUT(self) -> None:
            path = self.path.split("?", 1)[0]
            if path != "/api/live/credentials":
                self._send(404, {"ok": False, "error": "not found"})
                return
            payload, err = self._read_json()
            if err:
                self._send(400, {"ok": False, "error": err})
                return
            parsed = validate_credentials_payload(payload)
            if isinstance(parsed, str):
                self._send(400, {"ok": False, "error": parsed})
                return
            rtmp_url, rtmp_key = parsed
            save_credentials(rtmp_url, rtmp_key)
            self._send(200, {"ok": True, "configured": True})

        def do_DELETE(self) -> None:
            path = self.path.split("?", 1)[0]
            if path != "/api/live/credentials":
                self._send(404, {"ok": False, "error": "not found"})
                return
            delete_credentials()
            self._send(200, {"ok": True, "configured": is_configured()})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/api/live/stop":
                state = controller.stop()
                self._send(200, {"ok": True, "state": state})
                return
            if path != "/api/live/start":
                self._send(404, {"ok": False, "error": "not found"})
                return
            payload, err = self._read_json()
            if err:
                self._send(400, {"ok": False, "error": err})
                return
            parsed = validate_start_payload(payload, stored=load_credentials())
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
