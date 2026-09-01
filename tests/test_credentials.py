"""Local RTMP credential store + loopback credentials API.

Mocked fs/env only. Responses never echo secrets. GET never contains an
rtmp substring from the fixtures.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
import pytest

from retrans.config import LOOPBACK_HOST, RTMP_KEY_ENV, RTMP_URL_ENV
from retrans.credentials import (
    credentials_path,
    delete_credentials,
    env_credentials,
    file_credentials,
    is_configured,
    load_credentials,
    save_credentials,
)
from retrans.ingest import StreamResolver
from retrans.serve import (
    BindRefused,
    LiveController,
    make_handler,
    normalize_bind_host,
    validate_credentials_payload,
    validate_start_payload,
)

from tests.test_serve import ImmediateLive, SECRET_KEY, SECRET_URL, SOURCE, _live_resolver

OTHER_URL = "rtmp://other.example/live"
OTHER_KEY = "other-stream-key-abc"


@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    monkeypatch.delenv(RTMP_URL_ENV, raising=False)
    monkeypatch.delenv(RTMP_KEY_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return tmp_path / "xdg"


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


def _assert_no_fixture_rtmp(data: dict, raw: str) -> None:
    assert "rtmp_url" not in data
    assert "rtmp_key" not in data
    assert SECRET_URL not in raw
    assert SECRET_KEY not in raw
    assert OTHER_URL not in raw
    assert OTHER_KEY not in raw
    assert SECRET_URL not in json.dumps(data)
    assert SECRET_KEY not in json.dumps(data)
    # GET/PUT/DELETE bodies must not contain an rtmp substring from fixtures.
    assert "rtmps://" not in raw.lower()
    assert "rtmp://" not in raw.lower()


def test_credentials_path_uses_xdg(isolate_store):
    path = credentials_path()
    assert path == isolate_store / "retrans" / "credentials.json"


def test_save_file_mode_0600(isolate_store):
    path = save_credentials(SECRET_URL, SECRET_KEY)
    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == {"rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY}


def test_env_wins_over_file_on_read(isolate_store, monkeypatch):
    save_credentials(OTHER_URL, OTHER_KEY)
    assert file_credentials() == (OTHER_URL, OTHER_KEY)
    monkeypatch.setenv(RTMP_URL_ENV, SECRET_URL)
    monkeypatch.setenv(RTMP_KEY_ENV, SECRET_KEY)
    assert env_credentials() == (SECRET_URL, SECRET_KEY)
    assert load_credentials() == (SECRET_URL, SECRET_KEY)
    assert is_configured() is True


def test_delete_removes_file_not_env(isolate_store, monkeypatch):
    save_credentials(SECRET_URL, SECRET_KEY)
    monkeypatch.setenv(RTMP_URL_ENV, OTHER_URL)
    monkeypatch.setenv(RTMP_KEY_ENV, OTHER_KEY)
    delete_credentials()
    assert not credentials_path().exists()
    assert env_credentials() == (OTHER_URL, OTHER_KEY)
    assert is_configured() is True


def test_put_get_delete_credentials_api(api_factory, isolate_store):
    port = api_factory(LiveController(restream_factory=ImmediateLive))

    status, data, raw = _req(port, "GET", "/api/live/credentials")
    assert status == 200
    assert data == {"ok": True, "configured": False}
    _assert_no_fixture_rtmp(data, raw)

    status, data, raw = _req(
        port,
        "PUT",
        "/api/live/credentials",
        {"rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY},
    )
    assert status == 200
    assert data == {"ok": True, "configured": True}
    _assert_no_fixture_rtmp(data, raw)

    path = credentials_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    status, data, raw = _req(port, "GET", "/api/live/credentials")
    assert status == 200
    assert data == {"ok": True, "configured": True}
    _assert_no_fixture_rtmp(data, raw)
    assert "rtmp" not in raw.lower() or "configured" in raw
    # Strict: GET body must not contain the fixture rtmp substring at all.
    for fragment in (SECRET_URL, SECRET_KEY, "rtmps://", "rtmp://", "rtmp_url", "rtmp_key"):
        assert fragment not in raw

    status, data, raw = _req(port, "DELETE", "/api/live/credentials")
    assert status == 200
    assert data == {"ok": True, "configured": False}
    _assert_no_fixture_rtmp(data, raw)
    assert not path.exists()


def test_delete_still_configured_when_env_set(api_factory, monkeypatch):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    _req(
        port,
        "PUT",
        "/api/live/credentials",
        {"rtmp_url": OTHER_URL, "rtmp_key": OTHER_KEY},
    )
    monkeypatch.setenv(RTMP_URL_ENV, SECRET_URL)
    monkeypatch.setenv(RTMP_KEY_ENV, SECRET_KEY)
    status, data, raw = _req(port, "DELETE", "/api/live/credentials")
    assert status == 200
    assert data == {"ok": True, "configured": True}
    _assert_no_fixture_rtmp(data, raw)
    assert os.environ.get(RTMP_URL_ENV) == SECRET_URL


def test_put_empty_or_invalid_400(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    cases = [
        {},
        {"rtmp_url": "", "rtmp_key": SECRET_KEY},
        {"rtmp_url": SECRET_URL, "rtmp_key": ""},
        {"rtmp_url": "https://nope", "rtmp_key": "k"},
        {"rtmp_key": SECRET_KEY},
    ]
    for body in cases:
        status, data, raw = _req(port, "PUT", "/api/live/credentials", body)
        assert status == 400
        assert data["ok"] is False
        assert data.get("error")
        _assert_no_fixture_rtmp(data, raw)


def test_get_credentials_never_contains_rtmp_from_fixtures(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    _req(
        port,
        "PUT",
        "/api/live/credentials",
        {"rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY},
    )
    status, data, raw = _req(port, "GET", "/api/live/credentials")
    assert status == 200
    assert data == {"ok": True, "configured": True}
    _assert_no_fixture_rtmp(data, raw)
    assert SECRET_URL.lower() not in raw.lower()
    assert "rtmp" not in json.dumps(data).lower()


def test_start_with_only_source_url_when_file_set(api_factory):
    received = {}

    class CaptureLive(ImmediateLive):
        def start(self, source_url, rtmp_url, rtmp_key):
            received["source_url"] = source_url
            received["rtmp_url"] = rtmp_url
            received["rtmp_key"] = rtmp_key
            super().start(source_url, rtmp_url, rtmp_key)

    port = api_factory(LiveController(restream_factory=CaptureLive))
    put_status, put_data, put_raw = _req(
        port,
        "PUT",
        "/api/live/credentials",
        {"rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY},
    )
    assert put_status == 200
    _assert_no_fixture_rtmp(put_data, put_raw)

    status, data, raw = _req(port, "POST", "/api/live/start", {"source_url": SOURCE})
    assert status == 200
    assert data == {"ok": True, "state": "starting"}
    _assert_no_fixture_rtmp(data, raw)
    assert received["source_url"] == SOURCE
    assert received["rtmp_url"] == SECRET_URL
    assert received["rtmp_key"] == SECRET_KEY
    _req(port, "POST", "/api/live/stop")


def test_start_with_only_source_url_when_env_set(api_factory, monkeypatch):
    monkeypatch.setenv(RTMP_URL_ENV, SECRET_URL)
    monkeypatch.setenv(RTMP_KEY_ENV, SECRET_KEY)
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(port, "GET", "/api/live/credentials")
    assert status == 200
    assert data == {"ok": True, "configured": True}
    _assert_no_fixture_rtmp(data, raw)

    status, data, raw = _req(port, "POST", "/api/live/start", {"source_url": SOURCE})
    assert status == 200
    assert data == {"ok": True, "state": "starting"}
    _assert_no_fixture_rtmp(data, raw)
    _req(port, "POST", "/api/live/stop")


def test_start_without_store_400(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(port, "POST", "/api/live/start", {"source_url": SOURCE})
    assert status == 400
    assert data["ok"] is False
    assert "not configured" in data["error"].lower()
    _assert_no_fixture_rtmp(data, raw)


def test_start_body_override_not_required(api_factory):
    received = {}

    class CaptureLive(ImmediateLive):
        def start(self, source_url, rtmp_url, rtmp_key):
            received["rtmp_url"] = rtmp_url
            received["rtmp_key"] = rtmp_key
            super().start(source_url, SECRET_URL, SECRET_KEY)

    save_credentials(SECRET_URL, SECRET_KEY)
    port = api_factory(LiveController(restream_factory=CaptureLive))
    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE, "rtmp_url": OTHER_URL, "rtmp_key": OTHER_KEY},
    )
    assert status == 200
    _assert_no_fixture_rtmp(data, raw)
    assert received["rtmp_url"] == OTHER_URL
    assert received["rtmp_key"] == OTHER_KEY
    _req(port, "POST", "/api/live/stop")


def test_validate_credentials_same_rtmp_rules_as_start():
    err = validate_credentials_payload({"rtmp_url": "https://nope", "rtmp_key": "k"})
    assert isinstance(err, str)
    assert "invalid" in err
    err = validate_start_payload(
        {"source_url": SOURCE, "rtmp_url": "https://nope", "rtmp_key": "k"}
    )
    assert isinstance(err, str)
    assert "invalid" in err
    ok = validate_credentials_payload({"rtmp_url": SECRET_URL, "rtmp_key": SECRET_KEY})
    assert ok == (SECRET_URL, SECRET_KEY)


def test_no_clip_route_still_404(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, _ = _req(port, "PUT", "/api/clip", {"rtmp_url": SECRET_URL})
    assert status == 404
    assert data["ok"] is False


def test_malformed_file_is_not_configured(isolate_store):
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-json", encoding="utf-8")
    assert file_credentials() is None
    assert is_configured() is False


def test_bind_still_refuses_0_0_0_0():
    with pytest.raises(BindRefused, match="0.0.0.0"):
        normalize_bind_host("0.0.0.0")
