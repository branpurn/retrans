"""GET /api/live/preview — drop-link title + is_live. Mocked yt-dlp only."""

from __future__ import annotations

import json
import subprocess
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from retrans.config import LOOPBACK_HOST
from retrans.credentials import save_credentials
from retrans.ingest import StreamResolver, parse_preview_json, parse_preview_print, preview_is_live
from retrans.serve import LiveController, make_handler
from retrans.sources.youtube import is_youtube_url

SECRET_KEY = "super-secret-stream-key-xyz"
SECRET_URL = "rtmps://va.pscp.tv:443/x"
SOURCE = "https://www.youtube.com/watch?v=press"
LIVE_TITLE = "Press conference live"


class MustNotStart:
    """Restream factory that fails the test if instantiated or started."""

    def __init__(self):
        raise AssertionError("preview must not start a restream worker")

    def start(self, *_a, **_k):
        raise AssertionError("ffmpeg/RTMP must not start for preview")

    def wait(self):
        return 1

    def stop(self):
        return None


def _ytdlp_preview_run(
    title: str,
    status: str,
    calls: list | None = None,
    is_live_field: object = None,
):
    """Mock subprocess.run for yt-dlp -J. No network."""

    def run(argv, **_kwargs):
        if calls is not None:
            calls.append(list(argv))
        if argv[0] != "yt-dlp":
            raise AssertionError(f"unexpected binary: {argv}")
        joined = " ".join(argv)
        if "ffmpeg" in joined:
            raise AssertionError("ffmpeg must not start")
        if "-g" in argv:
            raise AssertionError("preview must not run yt-dlp -g")
        assert "-J" in argv
        assert "--no-playlist" in argv
        assert "--no-warnings" in argv
        payload = {"title": title, "live_status": status}
        if is_live_field is not None:
            payload["is_live"] = is_live_field
        elif status == "is_live":
            payload["is_live"] = True
        else:
            payload["is_live"] = False
        return SimpleNamespace(stdout=json.dumps(payload) + "\n", stderr="", returncode=0)

    return run


def _preview_resolver(
    title: str = LIVE_TITLE,
    status: str = "is_live",
    calls: list | None = None,
    is_live_field: object = None,
):
    return StreamResolver(
        run=_ytdlp_preview_run(title, status, calls=calls, is_live_field=is_live_field)
    )


@pytest.fixture(autouse=True)
def isolate_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def api_factory():
    servers = []

    def start(controller: LiveController, resolver: StreamResolver | None = None):
        httpd = HTTPServer(
            (LOOPBACK_HOST, 0),
            make_handler(controller, resolver=resolver or _preview_resolver()),
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append(httpd)
        return httpd.server_address[1]

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def _req(port: int, method: str, path: str, body=None, origin: str | None = None):
    conn = HTTPConnection(LOOPBACK_HOST, port, timeout=5)
    payload = None
    headers = {}
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if origin is not None:
        headers["Origin"] = origin
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode()
    acao = resp.getheader("Access-Control-Allow-Origin")
    conn.close()
    data = json.loads(raw) if raw else {}
    return resp.status, data, raw, acao


def _preview_path(source_url: str | None = SOURCE, include_key: bool = True) -> str:
    if not include_key:
        return "/api/live/preview"
    return "/api/live/preview?" + urlencode({"source_url": source_url})


def _assert_no_rtmp(data: dict, raw: str) -> None:
    assert "rtmp" not in raw.lower()
    assert "rtmp_url" not in data
    assert "rtmp_key" not in data
    assert "destination" not in data
    assert SECRET_KEY not in raw
    assert SECRET_URL not in raw


def test_preview_live_youtube_200(api_factory):
    calls: list[list[str]] = []
    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=_preview_resolver(LIVE_TITLE, "is_live", calls=calls),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 200
    assert data == {
        "ok": True,
        "source_url": SOURCE,
        "title": LIVE_TITLE,
        "is_live": True,
    }
    _assert_no_rtmp(data, raw)
    assert calls
    assert calls[0][0] == "yt-dlp"
    assert "-J" in calls[0]
    assert "-g" not in calls[0]


def test_preview_json_is_live_true_when_live_status_na(api_factory):
    """live_status may be NA/empty while JSON is_live is true."""
    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=_preview_resolver("lofi hip hop radio", "NA", is_live_field=True),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 200
    assert data["ok"] is True
    assert data["title"] == "lofi hip hop radio"
    assert data["is_live"] is True
    _assert_no_rtmp(data, raw)


@pytest.mark.parametrize("status", ["not_live", "was_live", "is_upcoming", "", "NA"])
def test_preview_vod_is_live_false_with_title(api_factory, status: str):
    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=_preview_resolver("VOD title", status, is_live_field=False),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 200
    assert data["ok"] is True
    assert data["title"] == "VOD title"
    assert data["is_live"] is False
    _assert_no_rtmp(data, raw)


def test_preview_empty_title_when_unknown(api_factory):
    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=_preview_resolver("NA", "is_live"),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 200
    assert data["title"] == ""
    assert data["is_live"] is True
    _assert_no_rtmp(data, raw)


def test_preview_missing_source_url_400(api_factory):
    port = api_factory(LiveController(restream_factory=MustNotStart))
    code, data, raw, _ = _req(port, "GET", "/api/live/preview")
    assert code == 400
    assert data == {"ok": False, "error": "missing source_url"}
    _assert_no_rtmp(data, raw)


def test_preview_empty_source_url_400(api_factory):
    port = api_factory(LiveController(restream_factory=MustNotStart))
    code, data, raw, _ = _req(port, "GET", "/api/live/preview?source_url=")
    assert code == 400
    assert data["ok"] is False
    assert "missing" in data["error"]
    _assert_no_rtmp(data, raw)


def test_preview_invalid_source_url_400(api_factory):
    port = api_factory(LiveController(restream_factory=MustNotStart))
    code, data, raw, _ = _req(port, "GET", _preview_path("not-a-url"))
    assert code == 400
    assert data == {"ok": False, "error": "invalid source_url"}
    _assert_no_rtmp(data, raw)


def test_preview_youtube_first_400(api_factory):
    calls: list[list[str]] = []
    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=_preview_resolver(calls=calls),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path("https://example.com/live"))
    assert code == 400
    assert data == {"ok": False, "error": "YouTube first"}
    _assert_no_rtmp(data, raw)
    assert calls == []
    assert is_youtube_url(SOURCE)
    assert not is_youtube_url("https://example.com/live")


def test_preview_probe_failure_not_200_empty_false(api_factory):
    """yt-dlp missing/fail is 502 {ok:false,error}, not 200 title="" is_live=false."""

    def run(argv, **_kwargs):
        if argv[0] != "yt-dlp":
            raise AssertionError(f"unexpected binary: {argv}")
        raise FileNotFoundError("yt-dlp")

    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=StreamResolver(run=run),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 502
    assert data["ok"] is False
    assert "error" in data and data["error"]
    assert data.get("title") in (None, "")
    assert data.get("is_live") is not False
    assert "title" not in data
    assert "is_live" not in data
    _assert_no_rtmp(data, raw)


def test_preview_probe_calledprocesserror_502(api_factory):
    def run(argv, **_kwargs):
        if argv[0] != "yt-dlp":
            raise AssertionError(f"unexpected binary: {argv}")
        raise subprocess.CalledProcessError(1, argv, stderr="unavailable")

    port = api_factory(
        LiveController(restream_factory=MustNotStart),
        resolver=StreamResolver(run=run),
    )
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 502
    assert data == {"ok": False, "error": "yt-dlp preview probe failed: unavailable"}
    _assert_no_rtmp(data, raw)


def test_preview_never_leaks_stored_credentials(api_factory):
    save_credentials(SECRET_URL, SECRET_KEY)
    port = api_factory(LiveController(restream_factory=MustNotStart))
    code, data, raw, _ = _req(port, "GET", _preview_path())
    assert code == 200
    assert data["ok"] is True
    _assert_no_rtmp(data, raw)


def test_preview_cors_loopback_origin(api_factory):
    port = api_factory(LiveController(restream_factory=MustNotStart))
    origin = "http://127.0.0.1:8788"
    code, data, raw, acao = _req(port, "GET", _preview_path(), origin=origin)
    assert code == 200
    assert acao == origin
    _assert_no_rtmp(data, raw)
    _, data_local, raw_local, acao_local = _req(
        port, "GET", _preview_path(), origin="http://localhost:5173"
    )
    assert acao_local == "http://localhost:5173"
    _assert_no_rtmp(data_local, raw_local)
    _, _, raw_evil, acao_evil = _req(
        port, "GET", _preview_path(), origin="http://127.0.0.1.evil.com"
    )
    assert acao_evil is None
    assert "rtmp" not in raw_evil.lower()


def test_preview_keeps_credentials_start_stop_status(api_factory):
    """Existing live routes still work on the same handler as preview."""

    started = {"n": 0}

    class CaptureLive:
        def start(self, source_url, rtmp_url, rtmp_key):
            started["n"] += 1
            assert source_url == SOURCE
            assert rtmp_key == SECRET_KEY

        def wait(self):
            threading.Event().wait(0.05)
            return 0

        def stop(self):
            return None

    def run(argv, **_kwargs):
        if argv[0] != "yt-dlp":
            raise AssertionError(f"unexpected binary: {argv}")
        if "-g" in argv or "ffmpeg" in " ".join(argv):
            raise AssertionError("must not fetch stream or start ffmpeg")
        if "-J" in argv:
            return SimpleNamespace(
                stdout=json.dumps(
                    {"title": LIVE_TITLE, "live_status": "is_live", "is_live": True}
                ),
                stderr="",
                returncode=0,
            )
        return SimpleNamespace(stdout="is_live\n", stderr="", returncode=0)

    save_credentials(SECRET_URL, SECRET_KEY)
    port = api_factory(
        LiveController(restream_factory=CaptureLive),
        resolver=StreamResolver(run=run),
    )
    st, creds, creds_raw, _ = _req(port, "GET", "/api/live/credentials")
    assert st == 200
    assert creds == {"ok": True, "configured": True}
    assert "rtmp" not in creds_raw.lower()

    prev, data, raw, _ = _req(port, "GET", _preview_path())
    assert prev == 200
    assert data["is_live"] is True
    _assert_no_rtmp(data, raw)

    start_code, start_data, start_raw, _ = _req(
        port,
        "POST",
        "/api/live/start",
        {"source_url": SOURCE},
    )
    assert start_code == 200
    assert start_data == {"ok": True, "state": "starting"}
    assert "rtmp_url" not in start_data
    assert "rtmp_key" not in start_data
    assert SECRET_KEY not in start_raw
    assert started["n"] == 1

    stop_code, stop_data, stop_raw, _ = _req(port, "POST", "/api/live/stop")
    assert stop_code == 200
    assert stop_data == {"ok": True, "state": "stopped"}
    assert "rtmp" not in stop_raw.lower()

    status_code, status, status_raw, _ = _req(port, "GET", "/api/live/status")
    assert status_code == 200
    assert status["ok"] is True
    assert "rtmp_url" not in status
    assert "rtmp_key" not in status
    assert SECRET_KEY not in status_raw


def test_no_clip_route_on_preview_server(api_factory):
    port = api_factory(LiveController(restream_factory=MustNotStart))
    code, data, raw, _ = _req(port, "GET", "/api/clip")
    assert code == 404
    assert data["ok"] is False
    assert "rtmp" not in raw.lower()


def test_parse_preview_print_and_is_live_helpers():
    assert parse_preview_print("Press conference\nis_live\n") == (
        "Press conference",
        "is_live",
    )
    assert parse_preview_print("NA\nnot_live\n") == ("", "not_live")
    assert parse_preview_print("is_live\n") == ("", "is_live")
    assert parse_preview_print("") == ("", "")
    assert preview_is_live("is_live") is True
    assert preview_is_live("true") is False
    assert preview_is_live("not_live") is False
    assert preview_is_live("NA", True) is True
    assert preview_is_live("", True) is True
    title, status, flag = parse_preview_json(
        json.dumps({"title": "Press conference", "live_status": "is_live", "is_live": True})
    )
    assert title == "Press conference"
    assert status == "is_live"
    assert flag is True
