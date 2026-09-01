from __future__ import annotations

import io
import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.request import Request

import pytest

from retrans.outputs.x import (
    RestreamError,
    XLiveRestream,
    build_ffmpeg_restream_cmd,
    debug_chunked_upload_and_post,
    escape_tee_sink,
    format_ffmpeg_exit_error,
    join_rtmp_destination,
)


def test_join_rtmp_appends_key():
    dest = join_rtmp_destination("rtmps://va.pscp.tv:443/x", "secret-key")
    assert dest == "rtmps://va.pscp.tv:443/x/secret-key"


def test_join_rtmp_key_x_is_playpath_not_app():
    """Default ingest app is /x. Key 'x' must still be a second path segment."""
    dest = join_rtmp_destination("rtmps://va.pscp.tv:443/x", "x")
    assert dest == "rtmps://va.pscp.tv:443/x/x"
    already = join_rtmp_destination("rtmps://va.pscp.tv:443/x/secret-key", "secret-key")
    assert already == "rtmps://va.pscp.tv:443/x/secret-key"


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
    assert "-r" in cmd and cmd[cmd.index("-r") + 1] == "30"
    assert "-b:v" in cmd and cmd[cmd.index("-b:v") + 1] == "9M"
    assert "-b:a" in cmd and cmd[cmd.index("-b:a") + 1] == "128k"
    assert "-flvflags" in cmd
    assert cmd[cmd.index("-flvflags") + 1] == "no_duration_filesize"
    vf = cmd[cmd.index("-vf") + 1]
    assert "1920:1080" in vf
    assert "force_original_aspect_ratio=decrease" in vf
    assert "pad=1920:1080" in vf
    joined = " ".join(cmd)
    assert "hevc" not in joined.lower()
    assert "libx265" not in joined
    assert "tee" not in joined.split()
    assert dest in cmd


def test_ffmpeg_tee_keeps_playpath_and_encode_lock(tmp_path: Path):
    dest = join_rtmp_destination("rtmps://va.pscp.tv:443/x", "placeholder-key")
    assert dest == "rtmps://va.pscp.tv:443/x/placeholder-key"
    preview = str(tmp_path / "index.m3u8")
    cmd = build_ffmpeg_restream_cmd(
        "https://cdn.example/live.m3u8", dest, preview_m3u8=preview
    )
    assert cmd[0] == "ffmpeg"
    assert "-map" in cmd and cmd[cmd.index("-map") + 1] == "0"
    assert cmd[cmd.index("-f") + 1] == "tee"
    assert "-use_fifo" in cmd
    spec = cmd[-1]
    assert escape_tee_sink(dest) in spec
    assert "f=flv" in spec
    assert "flvflags=no_duration_filesize" in spec
    assert "f=hls" in spec
    assert "hls_segment_type=fmp4" in spec
    assert escape_tee_sink(preview) in spec
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-b:v") + 1] == "9M"
    assert cmd[cmd.index("-r") + 1] == "30"
    assert cmd[cmd.index("-b:a") + 1] == "128k"
    vf = cmd[cmd.index("-vf") + 1]
    assert "1920:1080" in vf
    joined = " ".join(cmd)
    assert "hevc" not in joined.lower()
    assert "libx265" not in joined


def test_restream_start_tees_when_preview_dir(tmp_path: Path):
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
        "placeholder-key",
        preview_dir=str(tmp_path),
    )
    cmd = spawned["cmd"]
    dest = join_rtmp_destination("rtmps://va.pscp.tv:443/x", "placeholder-key")
    assert dest == "rtmps://va.pscp.tv:443/x/placeholder-key"
    assert cmd[cmd.index("-map") + 1] == "0"
    assert cmd[cmd.index("-f") + 1] == "tee"
    assert escape_tee_sink(dest) in cmd[-1]
    assert "index.m3u8" in cmd[-1]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_tee_writes_h264_aac_picture_and_sound(tmp_path: Path):
    """Real encode: same H.264/AAC bytes to FLV sink and HLS fMP4 playlist."""
    src = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(src),
        ],
        check=True,
    )
    dest = tmp_path / "out.flv"
    preview = tmp_path / "index.m3u8"
    cmd = build_ffmpeg_restream_cmd(str(src), str(dest), preview_m3u8=str(preview))
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    assert preview.is_file()
    assert dest.is_file()
    text = preview.read_text(encoding="utf-8")
    assert "#EXTM3U" in text
    assert "init.mp4" in text
    probe = subprocess.run(
        [
            "ffprobe",
            "-hide_banner",
            "-loglevel",
            "error",
            "-show_entries",
            "stream=codec_name,width,height,codec_type",
            "-of",
            "csv=p=0",
            str(preview),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    out = probe.stdout
    assert "h264" in out
    assert "aac" in out
    assert "1920" in out
    assert "1080" in out


class _FakeProc:
    def __init__(self, code=None):
        self._code = code
        self.stderr = io.StringIO("")

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        return 0 if self._code is None else self._code

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


def test_restream_start_allows_vod_when_require_live_false():
    spawned = {}

    class Resolver:
        def require_live(self, page_url: str) -> None:
            raise AssertionError("playlist path must not require_live")

        def resolve(self, page_url: str) -> str:
            return "https://cdn.example/vod.m3u8"

    def popen(cmd, **_kwargs):
        spawned["cmd"] = cmd
        return _FakeProc(code=None)

    job = XLiveRestream(resolver=Resolver(), popen=popen)
    job.start(
        "https://www.youtube.com/watch?v=vod",
        "rtmps://va.pscp.tv:443/x",
        "secret-key",
        require_live=False,
    )
    assert job.running()
    assert spawned["cmd"][0] == "ffmpeg"
    assert spawned["cmd"][-1].endswith("/secret-key")
    assert "https://cdn.example/vod.m3u8" in spawned["cmd"]
    assert spawned["cmd"][spawned["cmd"].index("-b:v") + 1] == "9M"


def test_restream_start_spawns_ffmpeg_after_resolve():
    spawned = {}

    class Resolver:
        def resolve(self, page_url: str) -> str:
            return "https://cdn.example/live.m3u8"

    def popen(cmd, **_kwargs):
        spawned["cmd"] = cmd
        spawned["proc"] = _FakeProc(code=None)
        return spawned["proc"]

    job = XLiveRestream(resolver=Resolver(), popen=popen)
    job.start(
        "https://www.youtube.com/watch?v=abc",
        "rtmps://va.pscp.tv:443/x",
        "secret-key",
    )
    assert job.running()
    assert spawned["cmd"][0] == "ffmpeg"
    assert spawned["cmd"][-1].endswith("/secret-key")
    with pytest.raises(RestreamError, match="cannot be reused"):
        job.start(
            "https://www.youtube.com/watch?v=abc",
            "rtmps://va.pscp.tv:443/x",
            "secret-key",
        )
    spawned["proc"]._code = 1
    assert job.running() is False
    with pytest.raises(RestreamError, match="cannot be reused"):
        job.start(
            "https://www.youtube.com/watch?v=abc",
            "rtmps://va.pscp.tv:443/x",
            "secret-key",
        )


def test_restream_start_output_open_io_is_restream_error():
    class Resolver:
        def resolve(self, page_url: str) -> str:
            return "https://cdn.example/live.m3u8"

    class Dead:
        def __init__(self):
            self.stderr = io.StringIO(
                "Error opening output file rtmps://va.pscp.tv:443/x/secret-key.\n"
                "Error opening output files: Input/output error\n"
            )

        def poll(self):
            return 1

    job = XLiveRestream(resolver=Resolver(), popen=lambda *_a, **_k: Dead())
    with pytest.raises(RestreamError) as exc:
        job.start("https://youtu.be/a", "rtmps://va.pscp.tv:443/x", "secret-key")
    text = str(exc.value)
    assert "secret-key" not in text
    assert "Input/output error" in text
    assert "RTMP output could not be opened" in text


def test_format_ffmpeg_exit_error_output_open_io():
    msg = format_ffmpeg_exit_error("Error opening output files: Input/output error")
    assert "ffmpeg restream exited" in msg
    assert "Input/output error" in msg
    assert "RTMP output could not be opened" in msg


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


class _DrainPipe:
    def __init__(self):
        self._q: queue.Queue[str | None] = queue.Queue()
        self.reads = 0

    def feed(self, text: str) -> None:
        self._q.put(text if text.endswith("\n") else text + "\n")

    def close(self) -> None:
        self._q.put(None)

    def __iter__(self):
        return self

    def __next__(self) -> str:
        item = self._q.get()
        if item is None:
            raise StopIteration
        self.reads += 1
        return item

    def read(self) -> str:
        return ""


def test_restream_drains_stderr_and_redacts():
    class Resolver:
        def resolve(self, page_url: str) -> str:
            return "https://cdn.example/live.m3u8"

    stderr = _DrainPipe()
    proc = _FakeProc(code=None)
    proc.stderr = stderr
    spawned = {}

    def popen(cmd, **kwargs):
        spawned["kwargs"] = kwargs
        return proc

    job = XLiveRestream(resolver=Resolver(), popen=popen)
    job.start(
        "https://www.youtube.com/watch?v=abc",
        "rtmps://va.pscp.tv:443/x",
        "secret-key",
    )
    assert spawned["kwargs"]["stderr"] is not None
    for i in range(40):
        stderr.feed(f"progress {i} dest=rtmps://va.pscp.tv:443/x/secret-key")
    for _ in range(80):
        if stderr.reads >= 40:
            break
        threading.Event().wait(0.02)
    assert stderr.reads >= 40
    last = job.last_stderr_line()
    assert last
    assert "secret-key" not in last
    assert "secret-key" not in job.ffmpeg_exit_error()
    proc._code = 1
    stderr.close()
    assert job.poll() == 1
    assert job.wait() == 1
    assert "ffmpeg restream exited" in job.ffmpeg_exit_error()
    assert "secret-key" not in job.ffmpeg_exit_error()


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
