"""X (Twitter) output.

PRIMARY (product): continuous live RTMP restream to Media Studio ingest.
The operator creates the RTMP source and broadcast in studio.x.com — there
is no public X API to create a live broadcast or mint an RTMP key. Do not
invent one. Sending RTMP alone is not enough; the operator must Create
Broadcast and Go Live in Media Studio (see Restream / Castr / vMix docs).

OPTIONAL DEBUG: chunked media upload + create post (no URL in the post body),
behind a debug CLI flag. Not the product. Not a live broadcast.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from retrans.outbound import INDEX_NAME

from retrans.config import X_BEARER_ENV, redact
from retrans.ingest import NotLiveError
from retrans.sources import resolve_page

PopenFactory = Callable[..., subprocess.Popen]
_STDERR_TAIL = 32


class RestreamError(RuntimeError):
    """Live restream could not start or exited unexpectedly."""


def join_rtmp_destination(rtmp_url: str, rtmp_key: str) -> str:
    """Combine Media Studio RTMP(S) URL + stream key into an ffmpeg sink.

    Typical Media Studio values look like rtmps://…/x plus a separate key.
    The key is appended as a path segment when it is not already present.
    RTMP publish needs app + playpath (two path segments). A bare /x app
    with an empty playpath makes ffmpeg fail output-open with EIO.
    """
    url = rtmp_url.strip()
    key = rtmp_key.strip()
    if not url or not key:
        raise RestreamError("rtmp url and key are required")
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"rtmp", "rtmps"}:
        raise RestreamError("rtmp url must start with rtmp:// or rtmps://")
    segments = [part for part in (parsed.path or "").split("/") if part]
    if len(segments) >= 2 and segments[-1] == key:
        return url
    if url.endswith("/"):
        return url + key
    return url + "/" + key


# Encode lock: 1080p / 9 Mbps / 30 fps / 128k AAC. One encode, then mux.
_ENCODE_LOCK = (
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-tune",
    "zerolatency",
    "-vf",
    "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
    "-r",
    "30",
    "-b:v",
    "9M",
    "-maxrate",
    "9M",
    "-bufsize",
    "18M",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-ar",
    "44100",
    "-ac",
    "2",
    "-b:a",
    "128k",
)


def escape_tee_sink(url: str) -> str:
    """Escape ffmpeg tee muxer special characters in a sink URL or path."""
    out: list[str] = []
    for char in url:
        if char in "\\:|[]":
            out.append("\\")
        out.append(char)
    return "".join(out)


def build_ffmpeg_restream_cmd(
    stream_url: str,
    destination: str,
    preview_m3u8: str | None = None,
) -> list[str]:
    """H.264 + AAC. FLV to Media Studio; optional tee to local HLS fMP4.

    destination must already be join_rtmp_destination (app + playpath).
    When preview_m3u8 is set: one encode, two sinks (RTMP + local playlist).
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-re",
        "-i",
        stream_url,
        *_ENCODE_LOCK,
    ]
    if preview_m3u8:
        rtmp_sink = escape_tee_sink(destination)
        hls_sink = escape_tee_sink(preview_m3u8)
        # flvflags on the RTMP sink only — same no-seek header as -f flv.
        tee_spec = (
            f"[f=flv:flvflags=no_duration_filesize]{rtmp_sink}"
            f"|[f=hls:onfail=ignore:hls_time=1:hls_list_size=10:"
            f"hls_flags=delete_segments+independent_segments:"
            f"hls_segment_type=fmp4:hls_fmp4_init_filename=init.mp4]"
            f"{hls_sink}"
        )
        cmd.extend(["-f", "tee", "-use_fifo", "1", tee_spec])
        return cmd
    cmd.extend(
        [
            "-flvflags",
            "no_duration_filesize",
            "-f",
            "flv",
            destination,
        ]
    )
    return cmd


_OUTPUT_OPEN_IO = "error opening output files: input/output error"


def is_output_open_io_error(message: str) -> bool:
    """True when ffmpeg failed to open the RTMP sink (EIO), not a mid-stream drop."""
    return _OUTPUT_OPEN_IO in (message or "").lower()


def format_ffmpeg_exit_error(last_stderr: str) -> str:
    """Operator-visible ffmpeg death. Secrets must already be redacted in last_stderr."""
    last = (last_stderr or "").strip()
    if not last:
        return "ffmpeg restream exited"
    if is_output_open_io_error(last):
        return (
            "ffmpeg restream exited: Error opening output files: Input/output error "
            "(RTMP output could not be opened)"
        )
    return f"ffmpeg restream exited: {last}"


class XLiveRestream:
    """Resolve a page URL and ffmpeg-restream it to operator RTMP ingest."""

    def __init__(
        self,
        resolver=None,
        popen: PopenFactory | None = None,
    ) -> None:
        self._resolver = resolver
        self._popen = popen or subprocess.Popen
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._rtmp_url = ""
        self._rtmp_key = ""
        self._dest = ""
        self._stderr_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=_STDERR_TAIL)
        self._stderr_thread: threading.Thread | None = None

    def start(
        self,
        source_url: str,
        rtmp_url: str,
        rtmp_key: str,
        *,
        require_live: bool = True,
        preview_dir: str | None = None,
    ) -> None:
        """Resolve + spawn ffmpeg. Returns once the process is running.

        One instance, one spawn. A dead or running proc cannot be started
        again — LiveController must construct a new XLiveRestream.

        require_live=True (default, single-URL live path) rejects VOD.
        Playlist items pass require_live=False so VOD and live both encode
        through the same ffmpeg restream command.
        """
        if self._proc is not None:
            raise RestreamError(
                "XLiveRestream.start cannot be reused; create a new instance"
            )
        dest = join_rtmp_destination(rtmp_url, rtmp_key)
        self._rtmp_url = rtmp_url
        self._rtmp_key = rtmp_key
        self._dest = dest
        try:
            if self._resolver is not None:
                if require_live:
                    require = getattr(self._resolver, "require_live", None)
                    if require is not None:
                        require(source_url)
                stream_url = self._resolver.resolve(source_url)
            else:
                resolved = resolve_page(source_url)
                if require_live and not resolved.live:
                    raise RestreamError(
                        "source is not a live stream (VOD / not live)"
                    )
                stream_url = resolved.stream_url
            preview_m3u8 = None
            if preview_dir:
                out = Path(preview_dir)
                out.mkdir(parents=True, exist_ok=True)
                preview_m3u8 = str(out / INDEX_NAME)
            cmd = build_ffmpeg_restream_cmd(
                stream_url, dest, preview_m3u8=preview_m3u8
            )
            self._proc = self._popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except RestreamError:
            raise
        except NotLiveError as exc:
            raise RestreamError(str(exc)) from exc
        except Exception as exc:
            raise RestreamError(
                redact(f"restream failed to start: {exc}", rtmp_url, rtmp_key, dest)
            ) from exc
        self._start_stderr_reader()
        if self._proc.poll() is not None:
            self._join_stderr_reader(timeout=1.0)
            err = self.last_stderr_line()
            if is_output_open_io_error(err):
                raise RestreamError(
                    redact(
                        "ffmpeg restream exited: Error opening output files: "
                        "Input/output error (RTMP output could not be opened)",
                        rtmp_url,
                        rtmp_key,
                        dest,
                    )
                )
            raise RestreamError(
                redact(
                    f"ffmpeg exited immediately: {err or 'no stderr'}",
                    rtmp_url,
                    rtmp_key,
                    dest,
                )
            )

    def _start_stderr_reader(self) -> None:
        """Drain ffmpeg stderr so a full PIPE cannot deadlock wait()."""
        thread = threading.Thread(
            target=self._drain_stderr,
            name="retrans-ffmpeg-stderr",
            daemon=True,
        )
        self._stderr_thread = thread
        thread.start()

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        secrets = (self._rtmp_url, self._rtmp_key, self._dest)
        try:
            for raw in proc.stderr:
                line = raw.rstrip("\r\n")
                if not line:
                    continue
                with self._stderr_lock:
                    self._stderr_lines.append(redact(line, *secrets))
        except (ValueError, OSError):
            return

    def _join_stderr_reader(self, timeout: float | None = 1.0) -> None:
        thread = self._stderr_thread
        if thread is not None:
            thread.join(timeout=timeout)

    def last_stderr_line(self) -> str:
        """Most recent non-empty redacted stderr line, or empty string."""
        with self._stderr_lock:
            for line in reversed(self._stderr_lines):
                if line.strip():
                    return line.strip()
        return ""

    def ffmpeg_exit_error(self) -> str:
        """Operator-visible reason after an unexpected ffmpeg exit. Secrets redacted."""
        return format_ffmpeg_exit_error(self.last_stderr_line())

    def poll(self) -> int | None:
        """ffmpeg poll(); None if not spawned or still running."""
        if self._proc is None:
            return None
        return self._proc.poll()

    def wait(self) -> int:
        if self._proc is None:
            return 0
        code = int(self._proc.wait())
        self._join_stderr_reader(timeout=1.0)
        return code

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self._join_stderr_reader(timeout=1.0)
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        self._join_stderr_reader(timeout=1.0)

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def run_foreground(self, source_url: str, rtmp_url: str, rtmp_key: str) -> int:
        """Product CLI path: block until ffmpeg exits or the operator hits Ctrl-C."""
        self.start(source_url, rtmp_url, rtmp_key)
        try:
            return self.wait()
        except KeyboardInterrupt:
            self.stop()
            return 130


# --- debug-only VOD post (not live, not default) ---

X_MEDIA_INIT = "https://api.x.com/2/media/upload/initialize"
X_MEDIA_APPEND = "https://api.x.com/2/media/upload/{media_id}/append"
X_MEDIA_FINALIZE = "https://api.x.com/2/media/upload/{media_id}/finalize"
X_CREATE_POST = "https://api.x.com/2/tweets"


class DebugUploadError(RuntimeError):
    """Debug media upload / post failed."""


def _json_request(
    url: str,
    token: str,
    payload: dict | None = None,
    method: str = "POST",
    opener: Callable = urllib.request.urlopen,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DebugUploadError(f"X API {exc.code}: {detail}") from exc
    return json.loads(body) if body else {}


def debug_chunked_upload_and_post(
    media_path: str,
    text: str = "",
    bearer_token: str | None = None,
    chunk_size: int = 1024 * 1024,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """DEBUG ONLY. Chunked media upload + create post. No URL is added to the body.

    This is not live broadcasting. There is no public X API to create a
    broadcast or mint an RTMP key — do not use this as a live path.
    """
    token = bearer_token or os.environ.get(X_BEARER_ENV, "")
    if not token:
        raise DebugUploadError(
            f"{X_BEARER_ENV} is required for the debug upload path"
        )
    if "http://" in text or "https://" in text:
        raise DebugUploadError("debug post body must not contain a URL")
    path = Path(media_path)
    raw = path.read_bytes()
    init = _json_request(
        X_MEDIA_INIT,
        token,
        {
            "total_bytes": len(raw),
            "media_type": "video/mp4",
            "media_category": "tweet_video",
        },
        opener=opener,
    )
    media_id = str(init.get("data", {}).get("id") or init.get("media_id") or "")
    if not media_id:
        raise DebugUploadError("X media initialize returned no media id")
    index = 0
    offset = 0
    while offset < len(raw):
        chunk = raw[offset : offset + chunk_size]
        _json_request(
            X_MEDIA_APPEND.format(media_id=media_id),
            token,
            {"segment_index": index, "media": chunk.hex()},
            opener=opener,
        )
        offset += len(chunk)
        index += 1
    _json_request(
        X_MEDIA_FINALIZE.format(media_id=media_id),
        token,
        {},
        opener=opener,
    )
    return _json_request(
        X_CREATE_POST,
        token,
        {"text": text, "media": {"media_ids": [media_id]}},
        opener=opener,
    )
