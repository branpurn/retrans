"""Env-var names and secret handling. Never log or persist RTMP keys / X tokens."""

from __future__ import annotations

RTMP_URL_ENV = "RETRANS_X_RTMP_URL"
RTMP_KEY_ENV = "RETRANS_X_RTMP_KEY"
X_BEARER_ENV = "RETRANS_X_BEARER_TOKEN"

# Serve bind — loopback only. HOST=0.0.0.0 is refused.
HOST_ENV = "HOST"
PORT_ENV = "PORT"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8788


def redact(text: str, *secrets: str | None) -> str:
    """Replace any provided secret substrings so logs/errors cannot leak them."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out
