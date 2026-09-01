from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.request import Request

import pytest

from retrans.outputs.x import (
    RestreamError,
    XLiveRestream,
    build_ffmpeg_restream_cmd,
    debug_chunked_upload_and_post,
    join_rtmp_destination,
)


def test_join_rtmp_appends_key():
    dest = join_rtmp_destination("rtmps://va.pscp.tv:443/x", "secret-key")
    assert dest == "rtmps://va.pscp.tv:443/x/secret-key"


def test_join_rtmp_rejects_non_rtmp():
    with pytest.raises(RestreamError):
        join_rtmp_destination("https://example.com/x", "key")


def test_ffmpeg_cmd_is_h264_aac_flv_not_hevc():
    dest = "rtmps://va.pscp.tv:443/x/key"
    cmd = build_ffmpeg_restream_cmd("https://cdn.example/live.m3u8", dest)
    assert cmd[0] == "ffmpeg"
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "flv"
    joined = " ".join(cmd)
    assert "hevc" not in joined.lower()
    assert "libx265" not in joined
    assert dest in cmd


class _FakeProc:
    def __init__(self, code=None):
        self._code = code
        self.stderr = io.StringIO("")

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        self._code = 0

    def kill(self):
        self._code = 0


def test_restream_start_refuses_vod_before_ffmpeg():
    spawned = {}

    class Resolver:
        def require_live(self, page_url: str) -> None:
            from retrans.ingest import NotLiveError

            raise NotLiveError("source is not a live stream (not_live); VOD and clips are rejected")

        def resolve(self, page_url: str) -> str:
            raise AssertionError("must not resolve stream URL for VOD")

    def popen(cmd, **_kwargs):
        spawned["cmd"] = cmd
        return _FakeProc(code=None)

    job = XLiveRestream(resolver=Resolver(), popen=popen)
    with pytest.raises(RestreamError, match="not a live stream|VOD"):
        job.start(
            "https://www.youtube.com/watch?v=vod",
            "rtmps://va.pscp.tv:443/x",
            "secret-key",
        )
    assert "cmd" not in spawned
    assert job.running() is False


def test_restream_start_spawns_ffmpeg_after_resolve():
    spawned = {}

    class Resolver:
        def resolve(self, page_url: str) -> str:
            return "https://cdn.example/live.m3u8"

    def popen(cmd, **_kwargs):
        spawned["cmd"] = cmd
        return _FakeProc(code=None)

    job = XLiveRestream(resolver=Resolver(), popen=popen)
    job.start(
        "https://www.youtube.com/watch?v=abc",
        "rtmps://va.pscp.tv:443/x",
        "secret-key",
    )
    assert job.running()
    assert spawned["cmd"][0] == "ffmpeg"
    assert spawned["cmd"][-1].endswith("/secret-key")


def test_restream_start_redacts_key_on_immediate_exit():
    class Resolver:
        def resolve(self, page_url: str) -> str:
            return "https://cdn.example/live.m3u8"

    class Dead:
        def __init__(self):
            self.stderr = io.StringIO("bad rtmps://va.pscp.tv:443/x/secret-key boom")

        def poll(self):
            return 1

    job = XLiveRestream(resolver=Resolver(), popen=lambda *_a, **_k: Dead())
    with pytest.raises(RestreamError) as exc:
        job.start("https://youtu.be/a", "rtmps://va.pscp.tv:443/x", "secret-key")
    assert "secret-key" not in str(exc.value)
    assert "***" in str(exc.value)


class _FakeHTTP:
    def __init__(self):
        self.calls: list[str] = []
        self._step = 0

    def __call__(self, req: Request, timeout=60):
        self.calls.append(req.full_url)
        if self._step == 0:
            body = json.dumps({"data": {"id": "mid1"}})
        else:
            body = json.dumps({"data": {"id": "post1"}})
        self._step += 1
        return _Resp(body)


class _Resp:
    def __init__(self, body: str):
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_debug_upload_posts_without_url_in_body(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake-bytes-here")
    http = _FakeHTTP()
    result = debug_chunked_upload_and_post(
        str(media),
        text="debug sample",
        bearer_token="tok",
        chunk_size=8,
        opener=http,
    )
    assert result["data"]["id"] == "post1"
    assert any("initialize" in u for u in http.calls)
    assert any("tweets" in u for u in http.calls)


def test_debug_upload_rejects_url_in_text(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    with pytest.raises(Exception, match="must not contain a URL"):
        debug_chunked_upload_and_post(
            str(media),
            text="see https://example.com",
            bearer_token="tok",
        )
