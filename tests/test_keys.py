"""Named key store + concurrent live sessions.

Placeholder values only — not real stream keys. Responses never echo secrets.
"""

from __future__ import annotations

import json
import stat
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from retrans.config import LOOPBACK_HOST
from retrans.ingest import NotLiveError
from retrans.keys import (
    DEFAULT_RTMP_URL,
    delete_key,
    get_key,
    keys_path,
    list_keys_public,
    upsert_key,
)
from retrans.serve import LiveController, make_handler

PLACEHOLDER_KEY_A = "placeholder-stream-key-aaa"
PLACEHOLDER_KEY_B = "placeholder-stream-key-bbb"
OVERRIDE_URL = "rtmp://placeholder.example/live"
SOURCE = "https://www.youtube.com/watch?v=press"


class ImmediateLive:
    def __init__(self):
        self.stopped = False
        self._started = threading.Event()
        self.rtmp_key = None

    def start(self, source_url, rtmp_url, rtmp_key, **_k):
        assert source_url == SOURCE
        self.rtmp_key = rtmp_key
        self._started.set()

    def wait(self):
        self._started.wait(timeout=2)
        while not self.stopped:
            threading.Event().wait(0.05)
        return 0

    def stop(self):
        self.stopped = True


class _AlwaysLive:
    def require_live(self, _url: str) -> None:
        return None


class _NeverLive:
    def require_live(self, _url: str) -> None:
        raise NotLiveError("source is not a live stream (not_live); VOD and clips are rejected")


@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("RETRANS_OUTBOUND_DIR", str(tmp_path / "outbound"))
    return tmp_path / "xdg"


@pytest.fixture
def api_factory():
    servers = []

    def start(controller: LiveController, resolver=None):
        httpd = HTTPServer(
            (LOOPBACK_HOST, 0),
            make_handler(controller, resolver=resolver or _AlwaysLive()),
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


def _assert_no_secrets(data: dict, raw: str) -> None:
    assert "rtmp_key" not in data
    assert "rtmp_url" not in data
    blob = raw + json.dumps(data)
    assert PLACEHOLDER_KEY_A not in blob
    assert PLACEHOLDER_KEY_B not in blob
    assert OVERRIDE_URL not in blob


def _wait_session(port: int, key_id: str, state: str) -> dict:
    last = {}
    for _ in range(50):
        _, data, _ = _req(port, "GET", "/api/live/status")
        last = data
        for sess in data.get("sessions") or []:
            if sess.get("key_id") == key_id and sess.get("state") == state:
                return sess
        threading.Event().wait(0.05)
    raise AssertionError(f"session {key_id} never reached {state}: {last}")


def test_keys_path_uses_xdg(isolate_store):
    path = keys_path()
    assert path == isolate_store / "retrans" / "keys.json"


def test_upsert_defaults_ingest_url_and_mode_0600(isolate_store):
    public = upsert_key(name="Studio A", rtmp_key=PLACEHOLDER_KEY_A)
    assert public["name"] == "Studio A"
    assert public["configured"] is True
    assert "rtmp_key" not in public
    path = keys_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    stored = get_key(public["id"])
    assert stored is not None
    assert stored["rtmp_url"] == DEFAULT_RTMP_URL
    assert stored["rtmp_key"] == PLACEHOLDER_KEY_A


def test_list_keys_public_never_includes_secrets(isolate_store):
    upsert_key(name="A", rtmp_key=PLACEHOLDER_KEY_A, key_id="key-a")
    listed = list_keys_public()
    assert listed == [{"id": "key-a", "name": "A", "configured": True}]
    blob = json.dumps(listed)
    assert PLACEHOLDER_KEY_A not in blob
    assert "rtmp_key" not in blob
    assert "rtmp_url" not in blob


def test_put_get_delete_keys_api(api_factory, isolate_store):
    port = api_factory(LiveController(restream_factory=ImmediateLive))

    status, data, raw = _req(port, "GET", "/api/live/keys")
    assert status == 200
    assert data == {"ok": True, "keys": []}
    _assert_no_secrets(data, raw)

    status, data, raw = _req(
        port,
        "PUT",
        "/api/live/keys",
        {"name": "Studio A", "rtmp_key": PLACEHOLDER_KEY_A},
    )
    assert status == 200
    assert data["ok"] is True
    assert data["name"] == "Studio A"
    assert data["configured"] is True
    assert data["id"]
    key_id = data["id"]
    _assert_no_secrets(data, raw)

    path = keys_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["keys"][0]["rtmp_url"] == DEFAULT_RTMP_URL

    status, data, raw = _req(port, "GET", "/api/live/keys")
    assert status == 200
    assert data == {
        "ok": True,
        "keys": [{"id": key_id, "name": "Studio A", "configured": True}],
    }
    _assert_no_secrets(data, raw)

    status, data, raw = _req(
        port,
        "PUT",
        "/api/live/keys",
        {
            "id": key_id,
            "name": "Studio A2",
            "rtmp_key": PLACEHOLDER_KEY_B,
            "rtmp_url": OVERRIDE_URL,
        },
    )
    assert status == 200
    assert data == {"ok": True, "id": key_id, "name": "Studio A2", "configured": True}
    _assert_no_secrets(data, raw)

    status, data, raw = _req(port, "DELETE", f"/api/live/keys/{key_id}")
    assert status == 200
    assert data == {"ok": True}
    _assert_no_secrets(data, raw)
    assert not path.exists()

    status, data, raw = _req(port, "GET", "/api/live/keys")
    assert status == 200
    assert data == {"ok": True, "keys": []}


def test_put_key_validation(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    cases = [
        {},
        {"name": "A"},
        {"rtmp_key": PLACEHOLDER_KEY_A},
        {"name": "", "rtmp_key": PLACEHOLDER_KEY_A},
        {"name": "A", "rtmp_key": ""},
        {"name": "A", "rtmp_key": PLACEHOLDER_KEY_A, "rtmp_url": "https://nope"},
        {"id": "bad/id", "name": "A", "rtmp_key": PLACEHOLDER_KEY_A},
    ]
    for body in cases:
        status, data, raw = _req(port, "PUT", "/api/live/keys", body)
        assert status == 400
        assert data["ok"] is False
        _assert_no_secrets(data, raw)


def test_delete_unknown_key_404(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(port, "DELETE", "/api/live/keys/missing")
    assert status == 404
    assert data["ok"] is False
    _assert_no_secrets(data, raw)


def test_start_stop_named_key_and_status_sessions(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    _, created, _ = _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": "studio-a", "name": "Studio A", "rtmp_key": PLACEHOLDER_KEY_A},
    )
    key_id = created["id"]

    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE, "key_id": key_id},
    )
    assert status == 200
    assert data["ok"] is True
    assert data["state"] == "starting"
    assert data["key_id"] == key_id
    session_id = data["session_id"]
    _assert_no_secrets(data, raw)

    sess = _wait_session(port, key_id, "live")
    assert sess["session_id"] == session_id
    assert sess["name"] == "Studio A"
    assert sess["source_url"] == SOURCE
    assert sess["error"] is None
    _, live, live_raw = _req(port, "GET", "/api/live/status")
    assert "sessions" in live
    _assert_no_secrets(live, live_raw)

    status, data, raw = _req(
        port, "POST", "/api/live/stop", {"session_id": session_id}
    )
    assert status == 200
    assert data == {"ok": True, "state": "stopped"}
    _assert_no_secrets(data, raw)

    _, after, after_raw = _req(port, "GET", "/api/live/status")
    stopped = [s for s in after["sessions"] if s["key_id"] == key_id][0]
    assert stopped["state"] == "stopped"
    _assert_no_secrets(after, after_raw)


def test_concurrent_keys_409_only_same_key(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": "studio-a", "name": "A", "rtmp_key": PLACEHOLDER_KEY_A},
    )
    _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": "studio-b", "name": "B", "rtmp_key": PLACEHOLDER_KEY_B},
    )

    a_code, a_data, a_raw = _req(
        port, "POST", "/api/live/start", {"source_url": SOURCE, "key_id": "studio-a"}
    )
    b_code, b_data, b_raw = _req(
        port, "POST", "/api/live/start", {"source_url": SOURCE, "key_id": "studio-b"}
    )
    assert a_code == 200
    assert b_code == 200
    assert a_data["session_id"] != b_data["session_id"]
    _assert_no_secrets(a_data, a_raw)
    _assert_no_secrets(b_data, b_raw)

    _wait_session(port, "studio-a", "live")
    _wait_session(port, "studio-b", "live")

    again, conflict, conflict_raw = _req(
        port, "POST", "/api/live/start", {"source_url": SOURCE, "key_id": "studio-a"}
    )
    assert again == 409
    assert conflict["ok"] is False
    assert conflict["key_id"] == "studio-a"
    _assert_no_secrets(conflict, conflict_raw)

    _, status, status_raw = _req(port, "GET", "/api/live/status")
    states = {s["key_id"]: s["state"] for s in status["sessions"]}
    assert states["studio-a"] == "live"
    assert states["studio-b"] == "live"
    _assert_no_secrets(status, status_raw)

    stop_b, stop_data, stop_raw = _req(
        port, "POST", "/api/live/stop", {"key_id": "studio-b"}
    )
    assert stop_b == 200
    assert stop_data["state"] == "stopped"
    _assert_no_secrets(stop_data, stop_raw)
    _wait_session(port, "studio-b", "stopped")
    still_a = _wait_session(port, "studio-a", "live")
    assert still_a["state"] == "live"


def test_start_unknown_key_400(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(
        port, "POST", "/api/live/start", {"source_url": SOURCE, "key_id": "missing"}
    )
    assert status == 400
    assert data["ok"] is False
    _assert_no_secrets(data, raw)


def test_named_start_rejects_vod_no_ffmpeg(api_factory):
    port = api_factory(
        LiveController(restream_factory=ImmediateLive),
        resolver=_NeverLive(),
    )
    _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": "studio-a", "name": "A", "rtmp_key": PLACEHOLDER_KEY_A},
    )
    status, data, raw = _req(
        port, "POST", "/api/live/start", {"source_url": SOURCE, "key_id": "studio-a"}
    )
    assert status == 400
    assert data["ok"] is False
    assert "not a live stream" in data["error"].lower() or "vod" in data["error"].lower()
    _assert_no_secrets(data, raw)
    _, live, live_raw = _req(port, "GET", "/api/live/status")
    assert live["sessions"] == []
    _assert_no_secrets(live, live_raw)


def test_stop_unknown_session_is_ok(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw = _req(
        port, "POST", "/api/live/stop", {"session_id": "nobody"}
    )
    assert status == 200
    assert data == {"ok": True, "state": "stopped"}
    _assert_no_secrets(data, raw)


def test_delete_key_module(isolate_store):
    upsert_key(name="A", rtmp_key=PLACEHOLDER_KEY_A, key_id="studio-a")
    assert delete_key("studio-a") is True
    assert get_key("studio-a") is None
    assert delete_key("studio-a") is False
