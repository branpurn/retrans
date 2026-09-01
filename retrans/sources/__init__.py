"""Input plugins. YouTube is first; a generic yt-dlp/streamlink plugin follows."""

from __future__ import annotations

from retrans.ingest import StreamResolver
from retrans.sources.base import ResolvedStream, SourceError, SourcePlugin
from retrans.sources.youtube import YouTubeSource


class GenericSource:
    """Catch-all: any page URL yt-dlp or streamlink can resolve."""

    name = "generic"

    def __init__(self, resolver: StreamResolver | None = None) -> None:
        self._resolver = resolver or StreamResolver()

    def matches(self, page_url: str) -> bool:
        return bool(page_url.strip())

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


def default_plugins(resolver: StreamResolver | None = None) -> list[SourcePlugin]:
    shared = resolver or StreamResolver()
    return [YouTubeSource(shared), GenericSource(shared)]


def resolve_page(
    page_url: str,
    plugins: list[SourcePlugin] | None = None,
    resolver: StreamResolver | None = None,
) -> ResolvedStream:
    """Pick the first matching plugin and resolve the page URL to a stream."""
    for plugin in plugins if plugins is not None else default_plugins(resolver):
        if plugin.matches(page_url):
            return plugin.resolve(page_url)
    raise SourceError(f"no source plugin matched {page_url!r}")
