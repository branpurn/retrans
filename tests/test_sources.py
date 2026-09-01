from __future__ import annotations

from retrans.ingest import StreamResolver
from retrans.sources import GenericSource, default_plugins, resolve_page
from retrans.sources.youtube import YouTubeSource, is_youtube_url


class FakeResolver:
    def resolve(self, page_url: str) -> str:
        return f"https://stream.example/{page_url.split('/')[-1]}"


def test_youtube_plugin_matches_common_hosts():
    yt = YouTubeSource(resolver=FakeResolver())
    assert yt.matches("https://www.youtube.com/watch?v=abc")
    assert yt.matches("https://youtu.be/abc")
    assert yt.matches("https://m.youtube.com/watch?v=abc")
    assert not yt.matches("https://example.com/live")


def test_youtube_is_first_plugin():
    plugins = default_plugins(resolver=StreamResolver(run=lambda *_a, **_k: None))
    assert plugins[0].name == "youtube"
    assert isinstance(plugins[0], YouTubeSource)
    assert plugins[-1].name == "generic"
    assert isinstance(plugins[-1], GenericSource)


def test_resolve_page_uses_youtube_plugin():
    resolved = resolve_page(
        "https://www.youtube.com/watch?v=press",
        plugins=default_plugins(resolver=FakeResolver()),
    )
    assert resolved.plugin == "youtube"
    assert resolved.live is True
    assert resolved.stream_url.endswith("press")


def test_resolve_page_generic_fallback():
    resolved = resolve_page(
        "https://example.com/live",
        plugins=default_plugins(resolver=FakeResolver()),
    )
    assert resolved.plugin == "generic"


def test_is_youtube_url_nocookie():
    assert is_youtube_url("https://www.youtube-nocookie.com/embed/abc")
