from __future__ import annotations

import json
import queue
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from types import SimpleNamespace

import pytest

from retrans.config import LOOPBACK_HOST
from retrans.ingest import StreamResolver
from retrans.outputs.x import RestreamError, XLiveRestream
from retrans.serve import (
    BindRefused,
    LiveController,
    _cors_origin,
    ensure_loopback_bind,
    make_handler,
    normalize_bind_host,
    validate_start_payload,
)

SECRET_KEY = "super-secret-stream-key-xyz"
SECRET_URL = "rtmps://va.pscp.tv:443/x"
SOURCE = "https://www.youtube.com/watch?v=press"


class ImmediateLive:
    def __init__(self):
        self.stopped = False
        self._started = threading.Event()

    def start(self, source_url, rtmp_url, rtmp_key):
        assert source_url == SOURCE
        assert rtmp_key == SECRET_KEY
        self._started.set()

    def wait(self):
        self._started.wait(timeout=2)
        while not self.stopped:
            threading.Event().wait(0.05)
        return 0

    def stop(self):
        self.stopped = True

    def running(self):
        return not self.stopped


class HangStart:
    """Stay in starting until stop()."""

    def __init__(self):
        self._release = threading.Event()

    def start(self, *_a, **_k):
        self._release.wait(timeout=5)

    def wait(self):
        return 0

    def stop(self):
        self._release.set()


class FailStart:
    def start(self, *_a, **_k):
        raise RestreamError(f"could not reach {SECRET_URL}/{SECRET_KEY}")

    def wait(self):
        return 1

    def stop(self):
        return None


def _ytdlp_print_run(status: str, calls: list | None = None):
    """Mock subprocess.run for yt-dlp --print live_status. Never hits the network."""

    def run(argv, **_kwargs):
        if calls is not None:
            calls.append(list(argv))
        if argv[0] != "yt-dlp":
            raise AssertionError(f"unexpected binary: {argv}")
        if "-g" in argv:
            raise AssertionError("live probe must not run yt-dlp -g")
        if "ffmpeg" in argv[0]:
            raise AssertionError("ffmpeg must not start")
        assert "--print" in argv
        assert "live_status" in argv
        return SimpleNamespace(stdout=f"{status}\n", stderr="", returncode=0)

    return run


def _live_resolver(status: str = "is_live", calls: list | None = None) -> StreamResolver:
    return StreamResolver(run=_ytdlp_print_run(status, calls=calls))


@pytest.fixture
def api_factory():
    servers = []

    def start(controller: LiveController, resolver: StreamResolver | None = None):
        httpd = HTTPServer(
            (LOOPBACK_HOST, 0),
            make_handler(controller, resolver=resolver or _live_resolver()),
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append(httpd)
        return httpd.server_address[1]

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def _req(port: int, method: str, path: str, body=None):
    conn = HTTPConnection(LOOPBACK_HOST, port, timeout=5)
    payload = None
    headers = {}
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode()
    conn.close()
    data = json.loads(raw) if raw else {}
    return resp.status, data, raw


def test_normalize_host_defaults_loopback(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    assert normalize_bind_host(None) == "127.0.0.1"


def test_normalize_host_refuses_wildcard():
    with pytest.raises(BindRefused, match="0.0.0.0"):
        normalize_bind_host("0.0.0.0")


def test_normalize_host_refuses_ipv6_wildcard():
    with pytest.raises(BindRefused):
        normalize_bind_host("::")


def test_normalize_host_refuses_lan():
    with pytest.raises(BindRefused):
        normalize_bind_host("192.168.1.10")
    with pytest.raises(BindRefused):
        normalize_bind_host("10.0.0.5")


def test_normalize_host_accepts_localhost():
    assert normalize_bind_host("localhost") == "127.0.0.1"
    assert normalize_bind_host("127.0.0.1") == "127.0.0.1"


def test_ensure_loopback_bind_ok():
    ensure_loopback_bind("127.0.0.1", 8788)


def test_status_idle(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(port, "GET", "/api/live/status")
    assert status == 200
    assert data == {
        "ok": True,
        "state": "idle",
        "source_url": None,
        "error": None,
    }
    assert "rtmp_key" not in data
    assert "rtmp_url" not in data
    assert SECRET_KEY not in raw


def test_start_stop_and_status_never_echo_secrets(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE, "rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY},
    )
    assert status == 200
    assert data == {"ok": True, "state": "starting"}
    assert "rtmp_key" not in data
    assert SECRET_KEY not in raw
    assert SECRET_URL not in raw

    # wait until the job marks live
    for _ in range(50):
        _, live, live_raw = _req(port, "GET", "/api/live/status")
        if live["state"] == "live":
            break
        threading.Event().wait(0.05)
    assert live["state"] == "live"
    assert live["source_url"] == SOURCE
    assert live["error"] is None
    assert "rtmp_key" not in live
    assert "rtmp_url" not in live
    assert SECRET_KEY not in live_raw
    assert SECRET_URL not in live_raw

    status, data, raw = _req(port, "POST", "/api/live/stop")
    assert status == 200
    assert data == {"ok": True, "state": "stopped"}
    assert SECRET_KEY not in raw


def test_start_missing_fields_400(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, _ = _req(port, "POST", "/api/live/start", {"source_url": SOURCE})
    assert status == 400
    assert data["ok"] is False
    assert "missing" in data["error"]


def test_start_invalid_source_400(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, _ = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": "not-a-url", "rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY},
    )
    assert status == 400
    assert "invalid" in data["error"]


def test_start_invalid_rtmp_400():
    err = validate_start_payload(
        {"source_url": SOURCE, "rtmp_url": "https://nope", "rtmp_key": "k"}
    )
    assert isinstance(err, str)
    assert "invalid" in err


def test_start_409_already_running(api_factory):
    port = api_factory(LiveController(restream_factory=HangStart))
    body = {"source_url": SOURCE, "rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY}
    status, data, _ = _req(port, "POST", "/api/live/start", body)
    assert status == 200
    assert data["state"] == "starting"
    status, data, raw = _req(port, "POST", "/api/live/start", body)
    assert status == 409
    assert data["ok"] is False
    assert data["error"] == "already running"
    assert SECRET_KEY not in raw
    _req(port, "POST", "/api/live/stop")


def test_stop_when_idle_is_ok(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, _ = _req(port, "POST", "/api/live/stop")
    assert status == 200
    assert data == {"ok": True, "state": "stopped"}


def test_error_redacts_rtmp_secrets(api_factory):
    port = api_factory(LiveController(restream_factory=FailStart))
    _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE, "rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY},
    )
    for _ in range(50):
        _, data, raw = _req(port, "GET", "/api/live/status")
        if data["state"] == "error":
            break
        threading.Event().wait(0.05)
    assert data["state"] == "error"
    assert data["error"]
    assert SECRET_KEY not in data["error"]
    assert SECRET_KEY not in raw
    assert SECRET_URL not in raw
    assert "rtmp_key" not in data
    assert "rtmp_url" not in data


def test_no_clip_route(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, _ = _req(port, "POST", "/api/clip", {"source_url": SOURCE})
    assert status == 404
    assert data["ok"] is False
    status, _, _ = _req(port, "GET", "/api/clip")
    assert status == 404


class _OriginHandler:
    def __init__(self, origin: str):
        self.headers = {"Origin": origin}


def test_cors_origin_allows_loopback_http_with_port():
    assert _cors_origin(_OriginHandler("http://127.0.0.1:8788")) == "http://127.0.0.1:8788"
    assert _cors_origin(_OriginHandler("http://localhost:5173")) == "http://localhost:5173"


def test_cors_origin_rejects_lookalike_host():
    assert _cors_origin(_OriginHandler("http://127.0.0.1.evil.com")) is None


@pytest.mark.parametrize(
    "origin",
    ["", "*", "https://127.0.0.1", "https://localhost", "file://127.0.0.1", "http://"],
)
def test_cors_origin_rejects_non_loopback_http(origin: str):
    assert _cors_origin(_OriginHandler(origin)) is None


def _acao(port: int, origin: str) -> str | None:
    conn = HTTPConnection(LOOPBACK_HOST, port, timeout=5)
    conn.request("GET", "/api/live/status", headers={"Origin": origin})
    resp = conn.getresponse()
    resp.read()
    value = resp.getheader("Access-Control-Allow-Origin")
    conn.close()
    return value


def test_status_acao_reflects_only_exact_loopback_origin(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    assert _acao(port, "http://127.0.0.1:8788") == "http://127.0.0.1:8788"
    assert _acao(port, "http://localhost:5173") == "http://localhost:5173"
    assert _acao(port, "http://127.0.0.1.evil.com") is None


START_BODY = {
    "source_url": SOURCE,
    "rtmp_url": SECRET_URL,
    "rtmp_key": SECRET_KEY,
}


class MustNotStart:
    """Restream factory that fails the test if instantiated or started."""

    def __init__(self):
        raise AssertionError("restream factory must not be called for a non-live URL")

    def start(self, *_a, **_k):
        raise AssertionError("ffmpeg/RTMP must not start for a non-live URL")

    def wait(self):
        return 1

    def stop(self):
        return None


def test_start_validates_fields_before_live_probe(api_factory):
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        raise AssertionError("must not probe yt-dlp before field validation")

    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=StreamResolver(run=run),
    )
    code, data, _ = _req(port, "POST", "/api/live/start", {"source_url": SOURCE})
    assert code == 400
    assert data["ok"] is False
    assert "missing" in data["error"]
    assert calls == []


@pytest.mark.parametrize("status", ["not_live", "was_live", "is_upcoming", "", "NA"])
def test_start_rejects_vod_before_restream(api_factory, status: str):
    probe_calls: list[list[str]] = []
    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=_live_resolver(status, calls=probe_calls),
    )
    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 400
    assert data["ok"] is False
    err = (data.get("error") or "").lower()
    assert "not a live stream" in err or "vod" in err or "not live" in err
    assert SECRET_KEY not in raw
    assert SECRET_URL not in raw
    assert "rtmp_key" not in data
    assert "rtmp_url" not in data
    assert probe_calls
    assert "-g" not in probe_calls[0]

    st, status_body, _ = _req(port, "GET", "/api/live/status")
    assert st == 200
    assert status_body["state"] == "idle"
    assert status_body["ok"] is True


def test_start_proceeds_when_youtube_is_live(api_factory):
    probe_calls: list[list[str]] = []
    port = api_factory(
        LiveController(restream_factory=ImmediateLive),
        resolver=_live_resolver("is_live", calls=probe_calls),
    )
    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data == {"ok": True, "state": "starting"}
    assert SECRET_KEY not in raw
    assert probe_calls
    assert probe_calls[0][0] == "yt-dlp"
    assert "--print" in probe_calls[0]
    assert "live_status" in probe_calls[0]

    for _ in range(50):
        _, live, _ = _req(port, "GET", "/api/live/status")
        if live["state"] == "live":
            break
        threading.Event().wait(0.05)
    assert live["state"] == "live"
    assert live["error"] is None
    _req(port, "POST", "/api/live/stop")


def test_start_rejects_true_only_via_live_status_true_print(api_factory):
    """--print is_live may emit True; treat that as live."""
    port = api_factory(
        LiveController(restream_factory=ImmediateLive),
        resolver=_live_resolver("True"),
    )
    code, data, _ = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data["state"] == "starting"
    _req(port, "POST", "/api/live/stop")


class _LinePipe:
    """Iterable stderr stand-in a drain thread can block on."""

    def __init__(self):
        self._q: queue.Queue[str | None] = queue.Queue()
        self._closed = False

    def feed(self, text: str) -> None:
        if not text.endswith("\n"):
            text = text + "\n"
        self._q.put(text)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._q.put(None)

    def __iter__(self):
        return self

    def __next__(self) -> str:
        item = self._q.get()
        if item is None:
            raise StopIteration
        return item

    def read(self) -> str:
        chunks: list[str] = []
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            chunks.append(item)
        return "".join(chunks)


class _ControllableProc:
    """Mock ffmpeg: poll/wait/stderr are independently controllable."""

    def __init__(self):
        self._code: int | None = None
        self._done = threading.Event()
        self.stderr = _LinePipe()
        self.terminated = False

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        self._done.wait(timeout=timeout)
        return 0 if self._code is None else self._code

    def terminate(self):
        self.terminated = True
        self.die(0)

    def kill(self):
        self.die(-9)

    def die(self, code: int, stderr: str = "") -> None:
        if stderr:
            self.stderr.feed(stderr)
        self.stderr.close()
        self._code = code
        self._done.set()

    def mark_dead(self, code: int, stderr: str = "") -> None:
        """Make poll() report an exit without unblocking wait()."""
        if stderr:
            self.stderr.feed(stderr)
        self.stderr.close()
        self._code = code


class _LivePageResolver:
    def resolve(self, page_url: str) -> str:
        return "https://cdn.example/live.m3u8"


def _popen_holder() -> tuple[dict, object]:
    holder: dict = {}

    def popen(cmd, **_kwargs):
        proc = _ControllableProc()
        holder["proc"] = proc
        holder["cmd"] = cmd
        return proc

    return holder, popen


def _wait_status(port: int, wanted: str, tries: int = 80):
    data: dict = {}
    raw = ""
    for _ in range(tries):
        _, data, raw = _req(port, "GET", "/api/live/status")
        if data.get("state") == wanted:
            return data, raw
        threading.Event().wait(0.05)
    return data, raw


def _assert_no_rtmp_secrets(data: dict, raw: str) -> None:
    assert "rtmp_key" not in data
    assert "rtmp_url" not in data
    assert SECRET_KEY not in raw
    assert SECRET_URL not in raw
    err = data.get("error") or ""
    assert SECRET_KEY not in err
    assert SECRET_URL not in err
    assert SECRET_KEY not in json.dumps(data)
    assert SECRET_URL not in json.dumps(data)


def test_ffmpeg_kill_mid_restream_status_error(api_factory):
    holder, popen = _popen_holder()
    port = api_factory(
        LiveController(
            restream_factory=lambda: XLiveRestream(
                resolver=_LivePageResolver(),
                popen=popen,
            )
        )
    )
    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data["state"] == "starting"
    _assert_no_rtmp_secrets(data, raw)

    live, _ = _wait_status(port, "live")
    assert live["state"] == "live"
    proc: _ControllableProc = holder["proc"]
    proc.die(
        1,
        stderr=f"Connection to {SECRET_URL}/{SECRET_KEY} failed: Broken pipe",
    )

    status, raw = _wait_status(port, "error")
    assert status["state"] == "error"
    assert status["error"]
    assert "ffmpeg restream exited" in status["error"]
    _assert_no_rtmp_secrets(status, raw)


def test_ffmpeg_zero_exit_without_stop_is_error(api_factory):
    holder, popen = _popen_holder()
    port = api_factory(
        LiveController(
            restream_factory=lambda: XLiveRestream(
                resolver=_LivePageResolver(),
                popen=popen,
            )
        )
    )
    _req(port, "POST", "/api/live/start", START_BODY)
    live, _ = _wait_status(port, "live")
    assert live["state"] == "live"
    holder["proc"].die(0, stderr="rtmp output closed")

    status, raw = _wait_status(port, "error")
    assert status["state"] == "error"
    assert status["error"]
    assert status["state"] != "stopped"
    _assert_no_rtmp_secrets(status, raw)


def test_status_flips_error_while_wait_blocked(api_factory):
    """GET /api/live/status must not stay live if poll() says ffmpeg is dead."""
    holder, popen = _popen_holder()
    port = api_factory(
        LiveController(
            restream_factory=lambda: XLiveRestream(
                resolver=_LivePageResolver(),
                popen=popen,
            )
        )
    )
    _req(port, "POST", "/api/live/start", START_BODY)
    live, _ = _wait_status(port, "live")
    assert live["state"] == "live"
    holder["proc"].mark_dead(
        1,
        stderr=f"server rejected key {SECRET_KEY} at {SECRET_URL}",
    )

    _, data, raw = _req(port, "GET", "/api/live/status")
    assert data["state"] == "error"
    assert data["error"]
    _assert_no_rtmp_secrets(data, raw)
    assert not holder["proc"]._done.is_set()


def test_operator_stop_still_stopped_not_error(api_factory):
    holder, popen = _popen_holder()
    port = api_factory(
        LiveController(
            restream_factory=lambda: XLiveRestream(
                resolver=_LivePageResolver(),
                popen=popen,
            )
        )
    )
    _req(port, "POST", "/api/live/start", START_BODY)
    live, _ = _wait_status(port, "live")
    assert live["state"] == "live"

    st, data, raw = _req(port, "POST", "/api/live/stop")
    assert st == 200
    assert data == {"ok": True, "state": "stopped"}
    _assert_no_rtmp_secrets(data, raw)
    assert holder["proc"].terminated

    _, status, status_raw = _req(port, "GET", "/api/live/status")
    assert status["state"] == "stopped"
    assert status["error"] is None
    _assert_no_rtmp_secrets(status, status_raw)


def _live_controller_with_popen(popen):
    return LiveController(
        restream_factory=lambda: XLiveRestream(
            resolver=_LivePageResolver(),
            popen=popen,
        )
    )


def test_start_after_ffmpeg_death_error_same_server():
    """ffmpeg death → error → POST start again on the same HTTPServer is 200."""
    created: list[HTTPServer] = []

    class CountingHTTPServer(HTTPServer):
        def __init__(self, *args, **kwargs):
            created.append(self)
            super().__init__(*args, **kwargs)

    holder, popen = _popen_holder()
    controller = _live_controller_with_popen(popen)
    httpd = CountingHTTPServer(
        (LOOPBACK_HOST, 0),
        make_handler(controller, resolver=_live_resolver()),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        assert len(created) == 1
        only_server = created[0]

        code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
        assert code == 200
        assert data["state"] == "starting"
        _assert_no_rtmp_secrets(data, raw)

        live, _ = _wait_status(port, "live")
        assert live["state"] == "live"
        first_proc: _ControllableProc = holder["proc"]
        first_proc.die(
            1,
            stderr=f"Connection to {SECRET_URL}/{SECRET_KEY} failed: Broken pipe",
        )

        status, raw = _wait_status(port, "error")
        assert status["state"] == "error"
        assert status["error"]
        old_error = status["error"]
        _assert_no_rtmp_secrets(status, raw)

        # Same serve process — restart must not construct a new HTTPServer.
        code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
        assert code == 200
        assert data["state"] in {"starting", "live"}
        assert data.get("error") is None
        _assert_no_rtmp_secrets(data, raw)
        assert len(created) == 1
        assert created[0] is only_server

        recovered, rec_raw = _wait_status(port, "live")
        assert recovered["state"] == "live"
        assert recovered["error"] is None
        assert recovered["error"] != old_error
        assert recovered["source_url"] == SOURCE
        _assert_no_rtmp_secrets(recovered, rec_raw)
        assert holder["proc"] is not first_proc
        assert len(created) == 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_old_wait_thread_does_not_clobber_new_start(api_factory):
    """Late wait() from a dead session must not overwrite a new start's state."""
    holder, popen = _popen_holder()
    port = api_factory(_live_controller_with_popen(popen))

    _req(port, "POST", "/api/live/start", START_BODY)
    live, _ = _wait_status(port, "live")
    assert live["state"] == "live"
    first_proc: _ControllableProc = holder["proc"]
    first_proc.mark_dead(
        1,
        stderr=f"server rejected key {SECRET_KEY} at {SECRET_URL}",
    )

    status, raw = _wait_status(port, "error")
    assert status["state"] == "error"
    assert not first_proc._done.is_set()
    _assert_no_rtmp_secrets(status, raw)

    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data["state"] in {"starting", "live"}
    _assert_no_rtmp_secrets(data, raw)

    second_live, _ = _wait_status(port, "live")
    assert second_live["state"] == "live"
    assert second_live["error"] is None

    # Old wait() finishes after the new session is live.
    first_proc._done.set()
    threading.Event().wait(0.15)

    _, after, after_raw = _req(port, "GET", "/api/live/status")
    assert after["state"] == "live"
    assert after["error"] is None
    assert after["state"] != "error"
    _assert_no_rtmp_secrets(after, after_raw)


def test_start_recovers_from_stopped_and_idle_not_409(api_factory):
    holder, popen = _popen_holder()
    port = api_factory(_live_controller_with_popen(popen))

    # idle → start is 200, not 409
    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data["state"] == "starting"
    _assert_no_rtmp_secrets(data, raw)

    live, _ = _wait_status(port, "live")
    assert live["state"] == "live"

    # live → start is 409
    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 409
    assert data["ok"] is False
    assert data["error"] == "already running"
    assert data["state"] == "live"
    _assert_no_rtmp_secrets(data, raw)

    _req(port, "POST", "/api/live/stop")
    _, stopped, stopped_raw = _req(port, "GET", "/api/live/status")
    assert stopped["state"] == "stopped"
    assert stopped["error"] is None
    _assert_no_rtmp_secrets(stopped, stopped_raw)

    # stopped → start again is 200, not 409
    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data["state"] in {"starting", "live"}
    _assert_no_rtmp_secrets(data, raw)
    recovered, rec_raw = _wait_status(port, "live")
    assert recovered["state"] == "live"
    assert recovered["error"] is None
    _assert_no_rtmp_secrets(recovered, rec_raw)


def test_start_after_error_is_not_409(api_factory):
    holder, popen = _popen_holder()
    port = api_factory(_live_controller_with_popen(popen))
    _req(port, "POST", "/api/live/start", START_BODY)
    _wait_status(port, "live")
    holder["proc"].die(1, stderr="Broken pipe")
    status, _ = _wait_status(port, "error")
    assert status["state"] == "error"

    code, data, raw = _req(port, "POST", "/api/live/start", START_BODY)
    assert code == 200
    assert data["state"] in {"starting", "live"}
    assert data.get("ok") is True
    _assert_no_rtmp_secrets(data, raw)
