"""Resolve a page URL to a playable live stream.

Priority: live YouTube (press conferences, briefings). Uses yt-dlp first,
then streamlink as a fallback. Both are operator-installed CLI tools.

A live-status probe runs before restream: only currently live pages are
accepted. VOD, clips, upcoming, and ended livestreams are rejected.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence


class ResolveError(RuntimeError):
    """Page URL could not be resolved to a stream."""


class NotLiveError(ResolveError):
    """Page URL is not a currently live stream (VOD / clip / upcoming / ended)."""


Runner = Callable[..., subprocess.CompletedProcess]

# yt-dlp live_status / --print is_live values that mean "on air now".
_LIVE_STATUS_OK = frozenset({"is_live"})
_LIVE_BOOL_OK = frozenset({"true", "1", "yes"})
_LIVE_STATUS_TOKENS = frozenset(
    {"is_live", "not_live", "was_live", "is_upcoming", "post_live", "NA"}
)
_UNKNOWN_TITLE = frozenset({"", "na", "n/a", "none", "null", "nan"})


def status_is_live(live_status: str, is_live: object = None) -> bool:
    """True only for a current livestream (live_status is_live or is_live true)."""
    status = (live_status or "").strip()
    if status in _LIVE_STATUS_OK:
        return True
    if status.lower() in _LIVE_BOOL_OK:
        return True
    if is_live is True:
        return True
    if isinstance(is_live, str) and is_live.strip().lower() in _LIVE_BOOL_OK:
        return True
    return False


def preview_is_live(live_status: str) -> bool:
    """Drop-link preview: true only when yt-dlp live_status is exactly is_live."""
    return (live_status or "").strip() == "is_live"


def clean_preview_title(title: str) -> str:
    """Empty string when yt-dlp has no title (NA / missing)."""
    text = (title or "").strip()
    if text.lower() in _UNKNOWN_TITLE:
        return ""
    return text


def parse_preview_print(stdout: str) -> tuple[str, str]:
    """Parse yt-dlp --print title --print live_status stdout → (title, live_status)."""
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if not lines:
        return "", ""
    if len(lines) == 1:
        only = lines[0]
        if only in _LIVE_STATUS_TOKENS:
            return "", only
        return clean_preview_title(only), ""
    return clean_preview_title("\n".join(lines[:-1])), lines[-1]


class StreamResolver:
    """yt-dlp / streamlink resolver. Live YouTube is the Wave 1 priority."""

    def __init__(self, run: Runner | None = None) -> None:
        self._run = run or subprocess.run

    def live_status(self, page_url: str) -> str:
        """Return yt-dlp live_status (is_live, not_live, was_live, is_upcoming, …)."""
        try:
            proc = self._run(
                [
                    "yt-dlp",
                    "--print",
                    "live_status",
                    "--no-playlist",
                    "--no-warnings",
                    page_url,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ResolveError("yt-dlp is not installed") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise ResolveError(f"yt-dlp live probe failed: {stderr}") from exc
        for line in (proc.stdout or "").splitlines():
            candidate = line.strip()
            if candidate:
                return candidate
        return ""

    def preview_meta(self, page_url: str) -> tuple[str, bool]:
        """Return (title, is_live) via yt-dlp --print. Never starts ffmpeg.

        is_live is true only when live_status is exactly ``is_live``.
        Title is "" when unknown. Does not run yt-dlp -g or a restream worker.
        """
        try:
            proc = self._run(
                [
                    "yt-dlp",
                    "--print",
                    "title",
                    "--print",
                    "live_status",
                    "--no-playlist",
                    "--no-warnings",
                    page_url,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ResolveError("yt-dlp is not installed") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise ResolveError(f"yt-dlp preview probe failed: {stderr}") from exc
        title, status = parse_preview_print(proc.stdout or "")
        return title, preview_is_live(status)

    def is_currently_live(self, page_url: str) -> bool:
        """True when yt-dlp reports live_status is_live (or is_live true)."""
        try:
            return status_is_live(self.live_status(page_url))
        except ResolveError:
            return False

    def require_live(self, page_url: str) -> None:
        """Raise NotLiveError unless the page is a current livestream.

        Accepts only live_status ``is_live`` (or is_live true). Rejects
        not_live, was_live, is_upcoming, missing, VOD, and clips.
        """
        try:
            status = self.live_status(page_url)
        except ResolveError as exc:
            raise NotLiveError(
                f"could not confirm live stream (VOD / not live): {exc}"
            ) from exc
        if status_is_live(status):
            return
        label = status if status else "missing"
        raise NotLiveError(
            f"source is not a live stream ({label}); VOD and clips are rejected"
        )

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
