"""YouTube page URL → live stream. First-class Wave 1 source plugin."""

from __future__ import annotations

from urllib.parse import urlparse

from retrans.ingest import StreamResolver
from retrans.sources.base import ResolvedStream


def is_youtube_url(page_url: str) -> bool:
    host = (urlparse(page_url).hostname or "").lower()
    if host == "youtu.be":
        return True
    return host in {"youtube.com", "youtube-nocookie.com"} or host.endswith(
        (".youtube.com", ".youtube-nocookie.com")
    )


class YouTubeSource:
    """YouTube first: live press conferences and similar page URLs."""

    name = "youtube"

    def __init__(self, resolver: StreamResolver | None = None) -> None:
        self._resolver = resolver or StreamResolver()

    def matches(self, page_url: str) -> bool:
        return is_youtube_url(page_url)

    def resolve(self, page_url: str) -> ResolvedStream:
        live = False
        probe = getattr(self._resolver, "is_currently_live", None)
        if probe is not None:
            try:
                live = bool(probe(page_url))
            except Exception:  # noqa: BLE001 — VOD/probe failure is not live
                live = False
        stream_url = self._resolver.resolve(page_url)
        return ResolvedStream(
            page_url=page_url,
            stream_url=stream_url,
            plugin=self.name,
            live=live,
        )
