"""Playlist ingest: ordered source_urls, VOD+live, roll on ffmpeg EOF.

Placeholder keys only. Responses never echo rtmp_key / rtmp_url.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from retrans.config import LOOPBACK_HOST
from retrans.ingest import NotLiveError
from retrans.serve import LiveController, make_handler, parse_source_urls

PLACEHOLDER_KEY = "placeholder-stream-key-playlist"
SOURCE_A = "https://www.youtube.com/watch?v=vod-a"
SOURCE_B = "https://www.youtube.com/watch?v=vod-b"
SOURCE_LIVE = "https://www.youtube.com/watch?v=live-c"


class _NeverLive:
    def require_live(self, _url: str) -> None:
        raise NotLiveError("source is not a live stream (not_live); VOD and clips are rejected")


class _ControllableJob:
    """One ffmpeg restream stand-in. wait() blocks until release() or stop()."""

    def __init__(self, exit_code: int = 0):
        self.exit_code = exit_code
        self.source_url = None
        self.rtmp_url = None
        self.rtmp_key = None
        self.require_live = None
        self.stopped = False
        self._started = threading.Event()
        self._released = threading.Event()

    def start(self, source_url, rtmp_url, rtmp_key, require_live=True, preview_dir=None):
        self.source_url = source_url
        self.rtmp_url = rtmp_url
        self.rtmp_key = rtmp_key
        self.require_live = require_live
        self.preview_dir = preview_dir
        self._started.set()

    def wait(self):
        self._started.wait(timeout=2)
        self._released.wait(timeout=5)
        return self.exit_code

    def poll(self):
        if self._released.is_set():
            return self.exit_code
        return None

    def release(self):
        self._released.set()

    def stop(self):
        self.stopped = True
        self._released.set()


class _JobFactory:
    def __init__(self):
        self.jobs: list[_ControllableJob] = []

    def __call__(self):
        job = _ControllableJob()
        self.jobs.append(job)
        return job


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
            make_handler(controller, resolver=resolver or _NeverLive()),
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
    assert PLACEHOLDER_KEY not in blob
    err = data.get("error") or ""
    assert PLACEHOLDER_KEY not in err


def _put_key(port: int, key_id: str = "studio-a") -> str:
    status, data, raw = _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": key_id, "name": "Studio A", "rtmp_key": PLACEHOLDER_KEY},
    )
    assert status == 200
    _assert_no_secrets(data, raw)
    return data["id"]


def _wait_session(port: int, key_id: str, **want) -> dict:
    last = {}
    for _ in range(80):
        _, data, raw = _req(port, "GET", "/api/live/status")
        last = data
        _assert_no_secrets(data, raw)
        for sess in data.get("sessions") or []:
            if sess.get("key_id") != key_id:
                continue
            if all(sess.get(k) == v for k, v in want.items()):
                return sess
        threading.Event().wait(0.05)
    raise AssertionError(f"session {key_id} never matched {want}: {last}")


def test_parse_source_urls_requires_nonempty_http_list():
    assert isinstance(parse_source_urls({}), str)
    assert parse_source_urls({"source_urls": []}) == "invalid fields: source_urls"
    assert parse_source_urls({"source_urls": ["not-a-url"]}) == "invalid fields: source_urls"
    assert parse_source_urls({"source_urls": [SOURCE_A, SOURCE_B]}) == [SOURCE_A, SOURCE_B]


def test_playlist_empty_or_missing_key_400(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory))
    _put_key(port)

    status, data, raw = _req(
        port, "POST", "/api/live/start", {"source_urls": [SOURCE_A]}
    )
    assert status == 400
    assert data["ok"] is False
    assert "key_id" in data["error"]
    _assert_no_secrets(data, raw)
    assert factory.jobs == []

    status, data, raw = _req(
        port, "POST", "/api/live/start", {"source_urls": [], "key_id": "studio-a"}
    )
    assert status == 400
    assert data["ok"] is False
    _assert_no_secrets(data, raw)
    assert factory.jobs == []


def test_playlist_accepts_vod_and_exposes_current_index(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory), resolver=_NeverLive())
    key_id = _put_key(port)

    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_A, SOURCE_B], "key_id": key_id},
    )
    assert status == 200
    assert data["ok"] is True
    assert data["state"] == "starting"
    assert data["key_id"] == key_id
    session_id = data["session_id"]
    _assert_no_secrets(data, raw)

    sess = _wait_session(port, key_id, state="live", source_url=SOURCE_A)
    assert factory.jobs
    assert factory.jobs[0].require_live is False
    assert sess["session_id"] == session_id
    assert sess["source_index"] == 0
    assert sess["error"] is None
    _, live, live_raw = _req(port, "GET", "/api/live/status")
    _assert_no_secrets(live, live_raw)


def test_playlist_rolls_on_eof_then_stops(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory))
    key_id = _put_key(port)

    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_A, SOURCE_B, SOURCE_LIVE], "key_id": key_id},
    )
    assert status == 200
    _assert_no_secrets(data, raw)
    _wait_session(port, key_id, state="live", source_url=SOURCE_A, source_index=0)
    assert factory.jobs[0].rtmp_key == PLACEHOLDER_KEY

    factory.jobs[0].release()
    _wait_session(port, key_id, state="live", source_url=SOURCE_B, source_index=1)
    assert factory.jobs[1].require_live is False
    assert factory.jobs[1].rtmp_key == PLACEHOLDER_KEY

    factory.jobs[1].release()
    _wait_session(port, key_id, state="live", source_url=SOURCE_LIVE, source_index=2)

    factory.jobs[2].release()
    stopped = _wait_session(port, key_id, state="stopped")
    assert stopped["source_url"] == SOURCE_LIVE
    assert stopped["source_index"] == 2
    assert stopped["error"] is None
    _, after, after_raw = _req(port, "GET", "/api/live/status")
    _assert_no_secrets(after, after_raw)


def test_playlist_mid_item_death_is_error(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory))
    key_id = _put_key(port)
    _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_A, SOURCE_B], "key_id": key_id},
    )
    _wait_session(port, key_id, state="live", source_url=SOURCE_A)
    factory.jobs[0].exit_code = 1
    factory.jobs[0].release()
    errored = _wait_session(port, key_id, state="error")
    assert errored["source_url"] == SOURCE_A
    assert errored["error"]
    assert len(factory.jobs) == 1
    _, data, raw = _req(port, "GET", "/api/live/status")
    _assert_no_secrets(data, raw)


def test_playlist_stop_halts_remaining_items(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory))
    key_id = _put_key(port)
    _, started, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_A, SOURCE_B], "key_id": key_id},
    )
    _assert_no_secrets(started, raw)
    _wait_session(port, key_id, state="live")

    status, data, raw = _req(
        port, "POST", "/api/live/stop", {"session_id": started["session_id"]}
    )
    assert status == 200
    assert data == {"ok": True, "state": "stopped"}
    _assert_no_secrets(data, raw)
    stopped = _wait_session(port, key_id, state="stopped")
    assert stopped["error"] is None
    assert factory.jobs[0].stopped is True
    assert len(factory.jobs) == 1

    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_B], "key_id": key_id},
    )
    assert status == 200
    _wait_session(port, key_id, state="live", source_url=SOURCE_B)
    stop_key, stop_data, stop_raw = _req(
        port, "POST", "/api/live/stop", {"key_id": key_id}
    )
    assert stop_key == 200
    assert stop_data["state"] == "stopped"
    _assert_no_secrets(stop_data, stop_raw)


def test_playlist_409_per_key_only(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory))
    _put_key(port, "studio-a")
    _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": "studio-b", "name": "B", "rtmp_key": PLACEHOLDER_KEY + "-b"},
    )

    a_code, a_data, a_raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_A], "key_id": "studio-a"},
    )
    b_code, b_data, b_raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_B], "key_id": "studio-b"},
    )
    assert a_code == 200
    assert b_code == 200
    _assert_no_secrets(a_data, a_raw)
    _assert_no_secrets(b_data, b_raw)
    _wait_session(port, "studio-a", state="live")
    _wait_session(port, "studio-b", state="live")

    again, conflict, conflict_raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_urls": [SOURCE_LIVE], "key_id": "studio-a"},
    )
    assert again == 409
    assert conflict["ok"] is False
    assert conflict["key_id"] == "studio-a"
    _assert_no_secrets(conflict, conflict_raw)


def test_single_source_url_named_start_still_rejects_vod(api_factory):
    factory = _JobFactory()
    port = api_factory(LiveController(restream_factory=factory), resolver=_NeverLive())
    _put_key(port)
    status, data, raw = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE_A, "key_id": "studio-a"},
    )
    assert status == 400
    assert data["ok"] is False
    err = (data.get("error") or "").lower()
    assert "not a live stream" in err or "vod" in err
    _assert_no_secrets(data, raw)
    assert factory.jobs == []
    _, live, live_raw = _req(port, "GET", "/api/live/status")
    assert live["sessions"] == []
    _assert_no_secrets(live, live_raw)
