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
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from retrans.config import X_BEARER_ENV, redact
from retrans.ingest import NotLiveError
from retrans.sources import resolve_page

PopenFactory = Callable[..., subprocess.Popen]


class RestreamError(RuntimeError):
    """Live restream could not start or exited unexpectedly."""


def join_rtmp_destination(rtmp_url: str, rtmp_key: str) -> str:
    """Combine Media Studio RTMP(S) URL + stream key into an ffmpeg sink.

    Typical Media Studio values look like rtmps://…/x plus a separate key.
    The key is appended as a path segment when it is not already present.
    """
    url = rtmp_url.strip()
    key = rtmp_key.strip()
    if not url or not key:
        raise RestreamError("rtmp url and key are required")
    scheme = urlparse(url).scheme.lower()
    if scheme not in {"rtmp", "rtmps"}:
        raise RestreamError("rtmp url must start with rtmp:// or rtmps://")
    if url.rstrip("/").endswith(key) or url.endswith("/" + key):
        return url
    if url.endswith("/"):
        return url + key
    return url + "/" + key


def build_ffmpeg_restream_cmd(stream_url: str, destination: str) -> list[str]:
    """H.264 + AAC into FLV for Media Studio. Not HEVC."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-re",
        "-i",
        stream_url,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
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
        "-f",
        "flv",
        destination,
    ]


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

    def start(self, source_url: str, rtmp_url: str, rtmp_key: str) -> None:
        """Resolve + spawn ffmpeg. Returns once the process is running."""
        dest = join_rtmp_destination(rtmp_url, rtmp_key)
        try:
            if self._resolver is not None:
                require = getattr(self._resolver, "require_live", None)
                if require is not None:
                    require(source_url)
                stream_url = self._resolver.resolve(source_url)
            else:
                resolved = resolve_page(source_url)
                if not resolved.live:
                    raise RestreamError(
                        "source is not a live stream (VOD / not live)"
                    )
                stream_url = resolved.stream_url
            cmd = build_ffmpeg_restream_cmd(stream_url, dest)
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
        if self._proc.poll() is not None:
            err = ""
            if self._proc.stderr is not None:
                err = self._proc.stderr.read() or ""
            raise RestreamError(
                redact(
                    f"ffmpeg exited immediately: {err.strip()}",
                    rtmp_url,
                    rtmp_key,
                    dest,
                )
            )

    def wait(self) -> int:
        if self._proc is None:
            return 0
        return int(self._proc.wait())

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

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
