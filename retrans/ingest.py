"""Resolve a page URL to a playable live stream.

Priority: live YouTube (press conferences, briefings). Uses yt-dlp first,
then streamlink as a fallback. Both are operator-installed CLI tools.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence


class ResolveError(RuntimeError):
    """Page URL could not be resolved to a stream."""


Runner = Callable[..., subprocess.CompletedProcess]


class StreamResolver:
    """yt-dlp / streamlink resolver. Live YouTube is the Wave 1 priority."""

    def __init__(self, run: Runner | None = None) -> None:
        self._run = run or subprocess.run

    def resolve(self, page_url: str) -> str:
        last_error: Exception | None = None
        for method in (self._ytdlp, self._streamlink):
            try:
                url = method(page_url)
            except Exception as exc:  # noqa: BLE001 — try the next backend
                last_error = exc
                continue
            if url:
                return url
        detail = f": {last_error}" if last_error else ""
        raise ResolveError(f"could not resolve live stream for {page_url}{detail}")

    def _ytdlp(self, page_url: str) -> str:
        # -g prints the direct stream URL. Prefer muxed/live-friendly formats.
        return self._first_url(
            [
                "yt-dlp",
                "-g",
                "--no-playlist",
                "--no-warnings",
                "-f",
                "best[vcodec^=avc]/best[vcodec^=h264]/best",
                page_url,
            ]
        )

    def _streamlink(self, page_url: str) -> str:
        return self._first_url(["streamlink", "--stream-url", page_url, "best"])

    def _first_url(self, argv: Sequence[str]) -> str:
        try:
            proc = self._run(
                list(argv),
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ResolveError(f"{argv[0]} is not installed") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise ResolveError(f"{argv[0]} failed: {stderr}") from exc
        for line in (proc.stdout or "").splitlines():
            candidate = line.strip()
            if candidate.startswith(("http://", "https://")):
                return candidate
        raise ResolveError(f"{argv[0]} produced no stream URL")
