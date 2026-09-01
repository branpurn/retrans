"""Same-origin outbound of the live encode (HLS fMP4 tee).

Not GET /api/live/preview (Drop-link yt-dlp). Placeholder keys only.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest

from retrans.config import LOOPBACK_HOST
from retrans.ingest import StreamResolver
from retrans.outbound import (
    INDEX_NAME,
    outbound_url_path,
    parse_outbound_path,
    resolve_outbound_file,
)
from retrans.serve import LiveController, make_handler

PLACEHOLDER_KEY = "placeholder-stream-key-outbound"
SOURCE = "https://www.youtube.com/watch?v=press"
PLAYLIST = (
    "#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:1\n"
    "#EXTINF:1.0,\nseg0.m4s\n"
)


class ImmediateLive:
    def __init__(self):
        self.stopped = False
        self._started = threading.Event()
        self.preview_dir = None

    def start(self, source_url, rtmp_url, rtmp_key, **kwargs):
        assert source_url == SOURCE
        assert rtmp_key == PLACEHOLDER_KEY
        self.preview_dir = kwargs.get("preview_dir")
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


class _LiveResolver:
    def require_live(self, _url: str) -> None:
        return None

    def resolve(self, _url: str) -> str:
        return "https://cdn.example/live.m3u8"

    def preview_meta(self, source: str) -> tuple[str, bool]:
        return "Press conference", True


@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("RETRANS_OUTBOUND_DIR", str(tmp_path / "outbound"))
    return tmp_path


@pytest.fixture
def api_factory():
    servers = []

    def start(controller: LiveController, resolver=None):
        httpd = HTTPServer(
            (LOOPBACK_HOST, 0),
            make_handler(controller, resolver=resolver or StreamResolver()),
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
    raw = resp.read()
    conn.close()
    text = raw.decode()
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {}
    return resp.status, data, text, raw, resp


def _assert_no_secrets(data: dict, raw: str) -> None:
    assert "rtmp_key" not in data
    assert "rtmp_url" not in data
    blob = raw + json.dumps(data)
    assert PLACEHOLDER_KEY not in blob


def _wait_session(port: int, key_id: str, state: str) -> dict:
    last = {}
    for _ in range(50):
        _, data, raw, _, _ = _req(port, "GET", "/api/live/status")
        last = data
        for sess in data.get("sessions") or []:
            if sess.get("key_id") == key_id and sess.get("state") == state:
                _assert_no_secrets(data, raw)
                return sess
        threading.Event().wait(0.05)
    raise AssertionError(f"session {key_id} never reached {state}: {last}")


def _put_key(port: int) -> str:
    status, data, raw, _, _ = _req(
        port,
        "PUT",
        "/api/live/keys",
        {"id": "studio-out", "name": "Outbound", "rtmp_key": PLACEHOLDER_KEY},
    )
    assert status == 200
    _assert_no_secrets(data, raw)
    return data["id"]


def test_parse_outbound_path_rejects_traversal():
    assert parse_outbound_path("/live/abc123def456/index.m3u8") == (
        "abc123def456",
        "index.m3u8",
    )
    assert parse_outbound_path("/live/abc123def456/../secrets") is None
    assert parse_outbound_path("/api/live/preview") is None
    assert parse_outbound_path("/live/not-hex/index.m3u8") is None


def test_session_outbound_url_and_live_encode_bytes(api_factory, isolate_store):
    port = api_factory(
        LiveController(restream_factory=ImmediateLive),
        resolver=_LiveResolver(),
    )
    key_id = _put_key(port)
    status, data, raw, _, _ = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE, "key_id": key_id},
    )
    assert status == 200
    session_id = data["session_id"]
    _assert_no_secrets(data, raw)

    sess = _wait_session(port, key_id, "live")
    expected = outbound_url_path(session_id)
    assert sess["outbound_url"] == expected
    assert sess["outbound_url"].startswith("/live/")
    assert "://" not in sess["outbound_url"]
    assert PLACEHOLDER_KEY not in sess["outbound_url"]

    dest = isolate_store / "outbound" / session_id
    (dest / INDEX_NAME).write_text(PLAYLIST, encoding="utf-8")
    (dest / "seg0.m4s").write_bytes(b"fake-fmp4-encode")

    code, body, text, raw_bytes, _ = _req(port, "GET", expected)
    assert code == 200
    assert PLAYLIST in text
    assert PLACEHOLDER_KEY not in text
    assert "youtube" not in text.lower()

    seg_code, _, _, seg_raw, _ = _req(port, "GET", f"/live/{session_id}/seg0.m4s")
    assert seg_code == 200
    assert seg_raw == b"fake-fmp4-encode"

    missing = resolve_outbound_file(session_id, "nope.m4s")
    assert missing is None

    # Drop-link preview stays yt-dlp metadata — not this encode path.
    prev_code, prev, prev_raw, _, _ = _req(
        port, "GET", f"/api/live/preview?source_url={SOURCE}"
    )
    assert prev_code == 200
    assert prev == {
        "ok": True,
        "source_url": SOURCE,
        "title": "Press conference",
        "is_live": True,
    }
    assert "outbound_url" not in prev
    _assert_no_secrets(prev, prev_raw)

    _req(port, "POST", "/api/live/stop", {"session_id": session_id})
    gone, _, _, _, _ = _req(port, "GET", expected)
    assert gone == 404


def test_idle_has_no_outbound_url(api_factory):
    port = api_factory(LiveController(restream_factory=ImmediateLive))
    status, data, raw, _, _ = _req(port, "GET", "/api/live/status")
    assert status == 200
    assert data["sessions"] == []
    assert "outbound_url" not in data
    _assert_no_secrets(data, raw)
