from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from retrans.ingest import (
    NotLiveError,
    ResolveError,
    StreamResolver,
    parse_preview_json,
    parse_preview_print,
    preview_is_live,
    status_is_live,
)

PAGE = "https://www.youtube.com/watch?v=abc"


def _ok(stdout: str):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


def _print_live_run(status: str):
    def run(argv, **_kwargs):
        assert argv[0] == "yt-dlp"
        assert "--print" in argv
        assert "live_status" in argv
        assert "--no-playlist" in argv
        assert "--no-warnings" in argv
        assert "-g" not in argv
        assert PAGE in argv
        return _ok(f"{status}\n")

    return run


def test_resolve_uses_ytdlp_first():
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(argv)
        if argv[0] == "yt-dlp":
            return _ok("https://manifest.example/live.m3u8\n")
        raise AssertionError("streamlink should not run")

    url = StreamResolver(run=run).resolve("https://www.youtube.com/watch?v=abc")
    assert url == "https://manifest.example/live.m3u8"
    assert calls[0][0] == "yt-dlp"
    assert "-g" in calls[0]


def test_resolve_falls_back_to_streamlink():
    def run(argv, **_kwargs):
        if argv[0] == "yt-dlp":
            raise subprocess.CalledProcessError(1, argv, stderr="nope")
        return _ok("https://cdn.example/best.m3u8\n")

    url = StreamResolver(run=run).resolve("https://www.youtube.com/watch?v=abc")
    assert url == "https://cdn.example/best.m3u8"


def test_resolve_errors_when_both_fail():
    def run(argv, **_kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="fail")

    with pytest.raises(ResolveError, match="could not resolve"):
        StreamResolver(run=run).resolve("https://www.youtube.com/watch?v=abc")


def test_resolve_ignores_non_http_lines():
    def run(argv, **_kwargs):
        return _ok("not-a-url\nhttps://ok.example/s.m3u8\n")

    assert StreamResolver(run=run).resolve("https://youtu.be/x") == "https://ok.example/s.m3u8"


@pytest.mark.parametrize(
    "raw,is_live_field,expected",
    [
        ("is_live", None, True),
        ("True", None, True),
        ("true", None, True),
        ("not_live", None, False),
        ("was_live", None, False),
        ("is_upcoming", None, False),
        ("", None, False),
        ("NA", None, False),
        ("not_live", True, True),
        ("", False, False),
    ],
)
def test_status_is_live_accepts_only_current_live(raw, is_live_field, expected):
    assert status_is_live(raw, is_live_field) is expected


def test_live_status_uses_print_not_dash_g():
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(argv)
        return _ok("is_live\n")

    status = StreamResolver(run=run).live_status(PAGE)
    assert status == "is_live"
    assert calls[0][0] == "yt-dlp"
    assert "--print" in calls[0]
    assert "live_status" in calls[0]
    assert "-g" not in calls[0]


def test_is_currently_live_true_for_is_live():
    assert StreamResolver(run=_print_live_run("is_live")).is_currently_live(PAGE) is True


@pytest.mark.parametrize("status", ["not_live", "was_live", "is_upcoming", "", "NA"])
def test_is_currently_live_false_for_non_live(status: str):
    assert StreamResolver(run=_print_live_run(status)).is_currently_live(PAGE) is False


def test_require_live_accepts_is_live():
    StreamResolver(run=_print_live_run("is_live")).require_live(PAGE)


@pytest.mark.parametrize("status", ["not_live", "was_live", "is_upcoming", "", "NA"])
def test_require_live_rejects_vod_and_non_live(status: str):
    with pytest.raises(NotLiveError, match="not a live stream|VOD"):
        StreamResolver(run=_print_live_run(status)).require_live(PAGE)


def test_require_live_does_not_fetch_stream_url():
    def run(argv, **_kwargs):
        if "-g" in argv:
            raise AssertionError("require_live must not run yt-dlp -g")
        return _ok("not_live\n")

    with pytest.raises(NotLiveError):
        StreamResolver(run=run).require_live(PAGE)


def test_require_live_wraps_probe_failure():
    def run(argv, **_kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="unavailable")

    with pytest.raises(NotLiveError, match="not live|VOD"):
        StreamResolver(run=run).require_live(PAGE)


def _json_preview_run(
    title: str,
    status: str,
    is_live_field: object = None,
    calls: list | None = None,
):
    def run(argv, **_kwargs):
        if calls is not None:
            calls.append(list(argv))
        assert argv[0] == "yt-dlp"
        assert "-J" in argv
        assert "--no-playlist" in argv
        assert "--no-warnings" in argv
        assert "-g" not in argv
        assert "--print" not in argv
        assert PAGE in argv
        payload = {"title": title, "live_status": status}
        if is_live_field is not None:
            payload["is_live"] = is_live_field
        elif status == "is_live":
            payload["is_live"] = True
        else:
            payload["is_live"] = False
        return _ok(json.dumps(payload) + "\n")

    return run


def test_preview_meta_live_title():
    title, is_live = StreamResolver(run=_json_preview_run("Briefing", "is_live")).preview_meta(
        PAGE
    )
    assert title == "Briefing"
    assert is_live is True


@pytest.mark.parametrize("status", ["not_live", "was_live", "is_upcoming", "NA", ""])
def test_preview_meta_vod_is_not_live(status: str):
    title, is_live = StreamResolver(run=_json_preview_run("Talk", status, False)).preview_meta(
        PAGE
    )
    assert title == "Talk"
    assert is_live is False


def test_preview_meta_is_live_true_when_live_status_na():
    title, is_live = StreamResolver(
        run=_json_preview_run("Lofi girl", "NA", True)
    ).preview_meta(PAGE)
    assert title == "Lofi girl"
    assert is_live is True


def test_preview_meta_empty_title_when_na():
    title, is_live = StreamResolver(run=_json_preview_run("NA", "is_live")).preview_meta(PAGE)
    assert title == ""
    assert is_live is True


def test_preview_meta_does_not_fetch_stream_url():
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        if "-g" in argv:
            raise AssertionError("preview_meta must not run yt-dlp -g")
        if argv[0] != "yt-dlp":
            raise AssertionError("preview_meta must not start ffmpeg")
        return _ok(json.dumps({"title": "Title", "live_status": "is_live", "is_live": True}))

    title, is_live = StreamResolver(run=run).preview_meta(PAGE)
    assert title == "Title"
    assert is_live is True
    assert "-J" in calls[0]
    assert "-g" not in calls[0]


def test_preview_meta_wraps_probe_failure():
    def run(argv, **_kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="unavailable")

    with pytest.raises(ResolveError, match="preview probe failed"):
        StreamResolver(run=run).preview_meta(PAGE)


def test_preview_meta_wraps_invalid_json():
    def run(argv, **_kwargs):
        return _ok("not-json\n")

    with pytest.raises(ResolveError, match="invalid json"):
        StreamResolver(run=run).preview_meta(PAGE)


def test_parse_preview_json_and_is_live_helpers():
    title, status, flag = parse_preview_json(
        json.dumps({"title": "Hello", "live_status": "is_live", "is_live": True})
    )
    assert (title, status, flag) == ("Hello", "is_live", True)
    title, status, flag = parse_preview_json(
        json.dumps({"title": "NA", "live_status": "not_live", "is_live": False})
    )
    assert title == ""
    assert status == "not_live"
    assert flag is False
    title, status, flag = parse_preview_json(
        json.dumps({"title": "On air", "live_status": "NA", "is_live": True})
    )
    assert title == "On air"
    assert preview_is_live(status, flag) is True
    assert preview_is_live("is_live") is True
    assert preview_is_live("true") is False
    assert preview_is_live("not_live") is False
    assert preview_is_live("NA", True) is True
    assert preview_is_live("", True) is True
    assert preview_is_live("not_live", False) is False


def test_parse_preview_print_helpers():
    assert parse_preview_print("Hello\nis_live\n") == ("Hello", "is_live")
    assert parse_preview_print("NA\nnot_live\n") == ("", "not_live")
    assert preview_is_live("is_live") is True
    assert preview_is_live("true") is False
