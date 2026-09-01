from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from retrans.config import LOOPBACK_HOST
from retrans.outputs.x import RestreamError
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


@pytest.fixture
def api_factory():
    servers = []

    def start(controller: LiveController):
        httpd = HTTPServer((LOOPBACK_HOST, 0), make_handler(controller))
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
        status, data, raw = _req(port, "GET", "/api/live/status")
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
