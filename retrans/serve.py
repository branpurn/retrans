"""Loopback-only HTTP control API for the live restream path.

Bind is locked to 127.0.0.1:8788. HOST=0.0.0.0 (and any non-loopback /
LAN / hotspot address) is refused with a non-zero exit. When Vite dist/
is present, GET / and assets are served from that directory (same origin
as /api). Responses never echo rtmp_url or rtmp_key. There is no /api/clip route.

Named keys: GET/PUT /api/live/keys, DELETE /api/live/keys/<id> (0600 local file).
Retrans: POST /api/live/start {source_url, key_id} — concurrent workers; 409 per key_id.
Stop: POST /api/live/stop {session_id} or {key_id}. Status: GET /api/live/status {sessions:[]}.
Legacy GET/PUT/DELETE /api/live/credentials and body RTMP override remain.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import socket
import socketserver
import threading
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

from retrans.config import DEFAULT_PORT, HOST_ENV, LOOPBACK_HOST, PORT_ENV, redact
from retrans.credentials import (
    delete_credentials,
    is_configured,
    load_credentials,
    save_credentials,
)
from retrans.keys import (
    delete_key,
    get_key,
    list_keys_public,
    upsert_key,
    validate_key_payload,
)
from retrans.ingest import NotLiveError, ResolveError, StreamResolver
from retrans.outputs.x import RestreamError, XLiveRestream, join_rtmp_destination
from retrans.sources.youtube import is_youtube_url

MAX_BODY = 64 * 1024
VALID_STATES = ("idle", "starting", "live", "error", "stopped")
CORS_METHODS = "GET, PUT, POST, DELETE, OPTIONS"
DIST_ENV = "RETRANS_DIST"
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


def resolve_dist_dir(explicit: str | None = None) -> Path | None:
    """Locate Vite dist/ (index.html + assets) for same-origin operator UI.

    RETRANS_DIST (or explicit) is exclusive when set: a miss does not fall
    through to cwd / package-adjacent dist/.
    """
    raw = explicit if explicit is not None else os.environ.get(DIST_ENV, "")
    if isinstance(raw, str) and raw.strip():
        try:
            resolved = Path(raw.strip()).resolve()
        except OSError:
            return None
        if resolved.is_dir() and (resolved / "index.html").is_file():
            return resolved
        return None
    for cand in (Path.cwd() / "dist", Path(__file__).resolve().parent.parent / "dist"):
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved.is_dir() and (resolved / "index.html").is_file():
            return resolved
    return None


def safe_dist_file(dist: Path, url_path: str) -> Path | None:
    """Map a URL path onto a file under dist/. Reject traversal."""
    rel = unquote(url_path or "")
    if rel.startswith("/"):
        rel = rel[1:]
    if not rel or rel.endswith("/"):
        rel = f"{rel}index.html" if rel else "index.html"
    parts = Path(rel).parts
    if ".." in parts:
        return None
    try:
        root = dist.resolve()
        target = (root / rel).resolve()
        target.relative_to(root)
    except (OSError, ValueError):
        return None
    if target.is_file():
        return target
    return None


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


class SessionHub:
    """Concurrent live sessions keyed by named key_id. 409 only when that key is busy."""

    def __init__(self, restream_factory: Callable[[], XLiveRestream] | None = None) -> None:
        self._factory = restream_factory or XLiveRestream
        self._lock = threading.Lock()
        self._by_key: dict[str, dict[str, Any]] = {}
        self._by_session: dict[str, dict[str, Any]] = {}

    def _entry_public(self, entry: dict[str, Any]) -> dict[str, Any]:
        status = entry["controller"].public_status()
        return {
            "session_id": entry["session_id"],
            "key_id": entry["key_id"],
            "name": entry["name"],
            "source_url": status.get("source_url"),
            "state": status.get("state"),
            "error": status.get("error"),
        }

    def sessions_public(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._entry_public(entry) for entry in self._by_key.values()]

    def start(self, source_url: str, key_id: str, name: str, rtmp_url: str, rtmp_key: str) -> dict[str, Any]:
        with self._lock:
            entry = self._by_key.get(key_id)
            if entry is not None:
                if entry["controller"].busy:
                    raise AlreadyRunning("already running")
                entry["name"] = name
                state = entry["controller"].start(source_url, rtmp_url, rtmp_key)
                return {
                    "session_id": entry["session_id"],
                    "key_id": key_id,
                    "state": state,
                }
            controller = LiveController(self._factory)
            session_id = uuid.uuid4().hex[:12]
            entry = {
                "session_id": session_id,
                "key_id": key_id,
                "name": name,
                "controller": controller,
            }
            self._by_key[key_id] = entry
            self._by_session[session_id] = entry
            state = controller.start(source_url, rtmp_url, rtmp_key)
            return {"session_id": session_id, "key_id": key_id, "state": state}

    def stop(self, session_id: str | None = None, key_id: str | None = None) -> str:
        with self._lock:
            entry = None
            if session_id:
                entry = self._by_session.get(session_id)
            elif key_id:
                entry = self._by_key.get(key_id)
            if entry is None:
                return "stopped"
            controller = entry["controller"]
        controller.stop()
        return "stopped"

    def busy_for(self, key_id: str) -> bool:
        with self._lock:
            entry = self._by_key.get(key_id)
            return bool(entry is not None and entry["controller"].busy)


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


def _keys_id_from_path(path: str) -> str | None:
    prefix = "/api/live/keys/"
    if not path.startswith(prefix):
        return None
    key_id = path[len(prefix) :]
    if not key_id or "/" in key_id:
        return None
    return key_id


def make_handler(
    controller: LiveController,
    resolver: StreamResolver | None = None,
) -> type[BaseHTTPRequestHandler]:
    stream_resolver = resolver or StreamResolver()
    hub = SessionHub(getattr(controller, "_factory", None))

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

        def _send_static(self, url_path: str) -> bool:
            dist = resolve_dist_dir()
            if dist is None:
                return False
            file_path = safe_dist_file(dist, url_path)
            if file_path is None:
                return False
            data = file_path.read_bytes()
            ctype, _enc = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", ctype or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            origin = _cors_origin(self)
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)
            return True

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
            if path == "/api/live/keys":
                self._send(200, {"ok": True, "keys": list_keys_public()})
                return
            if path == "/api/live/preview":
                self._preview()
                return
            if path == "/api/live/status":
                status = controller.public_status()
                status["sessions"] = hub.sessions_public()
                self._send(200, status)
                return
            if path.startswith("/api/"):
                self._send(404, {"ok": False, "error": "not found"})
                return
            if self._send_static(path):
                return
            self._send(404, {"ok": False, "error": "not found"})

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
            if path == "/api/live/keys":
                self._put_key()
                return
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

        def _put_key(self) -> None:
            payload, err = self._read_json()
            if err:
                self._send(400, {"ok": False, "error": err})
                return
            parsed = validate_key_payload(payload)
            if isinstance(parsed, str):
                self._send(400, {"ok": False, "error": parsed})
                return
            public = upsert_key(
                name=parsed["name"],
                rtmp_key=parsed["rtmp_key"],
                key_id=parsed.get("id"),
                rtmp_url=parsed.get("rtmp_url"),
            )
            self._send(200, {"ok": True, **public})

        def do_DELETE(self) -> None:
            path = self.path.split("?", 1)[0]
            key_id = _keys_id_from_path(path)
            if key_id is not None:
                if not delete_key(key_id):
                    self._send(404, {"ok": False, "error": "not found"})
                    return
                self._send(200, {"ok": True})
                return
            if path != "/api/live/credentials":
                self._send(404, {"ok": False, "error": "not found"})
                return
            delete_credentials()
            self._send(200, {"ok": True, "configured": is_configured()})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/api/live/stop":
                self._stop()
                return
            if path != "/api/live/start":
                self._send(404, {"ok": False, "error": "not found"})
                return
            payload, err = self._read_json()
            if err:
                self._send(400, {"ok": False, "error": err})
                return
            if isinstance(payload, dict) and _nonempty_str(payload, "key_id"):
                self._start_named(payload)
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

        def _start_named(self, payload: dict[str, Any]) -> None:
            key_id = _nonempty_str(payload, "key_id")
            if key_id is None:
                self._send(400, {"ok": False, "error": "invalid fields: key_id"})
                return
            if "source_url" not in payload:
                self._send(400, {"ok": False, "error": "missing fields: source_url"})
                return
            source_url = validate_source_url(payload)
            if source_url is None:
                self._send(400, {"ok": False, "error": "invalid fields: source_url"})
                return
            record = get_key(key_id)
            if record is None:
                self._send(400, {"ok": False, "error": "unknown key_id"})
                return
            try:
                stream_resolver.require_live(source_url)
            except (NotLiveError, ResolveError) as exc:
                self._send(400, {"ok": False, "error": str(exc)})
                return
            try:
                started = hub.start(
                    source_url,
                    record["id"],
                    record["name"],
                    record["rtmp_url"],
                    record["rtmp_key"],
                )
            except AlreadyRunning:
                self._send(
                    409,
                    {
                        "ok": False,
                        "error": "already running",
                        "key_id": record["id"],
                    },
                )
                return
            self._send(
                200,
                {
                    "ok": True,
                    "state": started["state"],
                    "session_id": started["session_id"],
                    "key_id": started["key_id"],
                },
            )

        def _stop(self) -> None:
            payload, err = self._read_json()
            if err:
                self._send(400, {"ok": False, "error": err})
                return
            session_id = None
            key_id = None
            if isinstance(payload, dict):
                session_id = _nonempty_str(payload, "session_id")
                key_id = _nonempty_str(payload, "key_id")
            if session_id or key_id:
                state = hub.stop(session_id=session_id, key_id=key_id)
                self._send(200, {"ok": True, "state": state})
                return
            state = controller.stop()
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
