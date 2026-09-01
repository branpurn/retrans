"""Env-var names and secret handling.

Never log RTMP keys / X tokens. The only persist path is the operator-local
0600 credentials file (see retrans.credentials). API responses never echo them.
"""

from __future__ import annotations

import os
from pathlib import Path

RTMP_URL_ENV = "RETRANS_X_RTMP_URL"
RTMP_KEY_ENV = "RETRANS_X_RTMP_KEY"
X_BEARER_ENV = "RETRANS_X_BEARER_TOKEN"
SOURCE_URL_ENV = "SOURCE_URL"
TITLE_ENV = "RETRANS_TITLE"
TITLE_ENV_ALIAS = "TITLE"

# Hidden default ingest. Operators pass a stream key, not this URL.
DEFAULT_RTMP_URL = "rtmps://va.pscp.tv:443/x"

# Serve bind — host: 127.0.0.1 only. Container (/.dockerenv): 0.0.0.0:8788.
# Host publish is -p 127.0.0.1:8788:8788. LAN/hotspot IPs are refused.
HOST_ENV = "HOST"
PORT_ENV = "PORT"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8788
# Per-session HLS/fMP4 outbound of the live encode (same process, no second port).
OUTBOUND_DIR_ENV = "RETRANS_OUTBOUND_DIR"


def redact(text: str, *secrets: str | None) -> str:
    """Replace any provided secret substrings so logs/errors cannot leak them."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


def env_value(*names: str) -> str:
    """First nonempty environment value among names, else empty string."""
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def load_env_file(path: str | Path) -> None:
    """Load KEY=VALUE lines into os.environ. Does not override nonempty env.

    Never logs values. Comments and blank lines are ignored. Optional
    export prefix and single/double quotes around values are accepted.
    """
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not key:
            continue
        if not (os.environ.get(key) or "").strip():
            os.environ[key] = value
