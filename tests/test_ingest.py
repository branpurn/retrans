from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from retrans.ingest import NotLiveError, ResolveError, StreamResolver, status_is_live

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
