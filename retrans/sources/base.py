"""Extensible input-plugin sketch. A plugin maps a page URL to a live stream."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SourceError(RuntimeError):
    """No plugin could resolve the page URL."""


@dataclass(frozen=True)
class ResolvedStream:
    page_url: str
    stream_url: str
    plugin: str
    live: bool = True


class SourcePlugin(Protocol):
    name: str

    def matches(self, page_url: str) -> bool:
        """Return True if this plugin should handle the page URL."""

    def resolve(self, page_url: str) -> ResolvedStream:
        """Resolve the page URL to a playable stream URL."""
