from __future__ import annotations

from retrans.ingest import StreamResolver
from retrans.sources import GenericSource, default_plugins, resolve_page
from retrans.sources.youtube import YouTubeSource, is_youtube_url


class FakeResolver:
    live = True

    def resolve(self, page_url: str) -> str:
        return f"https://stream.example/{page_url.split('/')[-1]}"

    def is_currently_live(self, page_url: str) -> bool:
        return self.live


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


def test_youtube_resolve_sets_live_false_for_vod():
    resolver = FakeResolver()
    resolver.live = False
    yt = YouTubeSource(resolver=resolver)
    resolved = yt.resolve("https://www.youtube.com/watch?v=vod")
    assert resolved.live is False
    assert resolved.plugin == "youtube"


def test_youtube_resolve_sets_live_true_only_when_probe_says_live():
    yt = YouTubeSource(resolver=FakeResolver())
    assert yt.resolve("https://www.youtube.com/watch?v=press").live is True


def test_generic_resolve_sets_live_from_probe():
    resolver = FakeResolver()
    resolver.live = False
    resolved = GenericSource(resolver=resolver).resolve("https://example.com/clip")
    assert resolved.live is False
    assert resolved.plugin == "generic"
