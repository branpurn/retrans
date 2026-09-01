from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from retrans.ingest import ResolveError, StreamResolver


def _ok(stdout: str):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


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
