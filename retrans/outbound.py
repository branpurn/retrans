"""Same-origin outbound of the live ffmpeg encode (HLS fMP4).

Path-only URLs under /live/<session_id>/… . Files live under a temp root
(or RETRANS_OUTBOUND_DIR). This is the encode tee sink — not Drop-link
preview, not a YouTube embed, not a clip.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from retrans.config import OUTBOUND_DIR_ENV

SESSION_ID_RE = re.compile(r"^[0-9a-f]{12}$")
FILE_RE = re.compile(r"^[A-Za-z0-9._-]+$")
INDEX_NAME = "index.m3u8"
_DEFAULT_ROOT_NAME = "retrans-outbound"

_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".m4s": "video/iso.segment",
    ".mp4": "video/mp4",
    ".ts": "video/mp2t",
}


def outbound_url_path(session_id: str) -> str:
    """Path-only playlist URL for a running session. Never a host or secret."""
    return f"/live/{session_id}/{INDEX_NAME}"


def outbound_root() -> Path:
    raw = (os.environ.get(OUTBOUND_DIR_ENV) or "").strip()
    if raw:
        return Path(raw)
    return Path(os.environ.get("TMPDIR") or "/tmp") / _DEFAULT_ROOT_NAME


def ensure_session_dir(session_id: str) -> Path:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("invalid session id")
    dest = outbound_root() / session_id
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def clear_session_dir(session_id: str) -> None:
    if not SESSION_ID_RE.fullmatch(session_id):
        return
    path = outbound_root() / session_id
    shutil.rmtree(path, ignore_errors=True)


def parse_outbound_path(url_path: str) -> tuple[str, str] | None:
    """Parse /live/<session_id>/<file> → (session_id, filename) or None."""
    raw = (url_path or "").split("?", 1)[0]
    parts = [p for p in raw.split("/") if p]
    if len(parts) != 3 or parts[0] != "live":
        return None
    session_id, name = parts[1], parts[2]
    if not SESSION_ID_RE.fullmatch(session_id) or not FILE_RE.fullmatch(name):
        return None
    return session_id, name


def resolve_outbound_file(session_id: str, name: str) -> Path | None:
    if not SESSION_ID_RE.fullmatch(session_id) or not FILE_RE.fullmatch(name):
        return None
    root = outbound_root().resolve()
    session_root = (root / session_id).resolve()
    try:
        session_root.relative_to(root)
    except ValueError:
        return None
    try:
        target = (session_root / name).resolve()
        target.relative_to(session_root)
    except (OSError, ValueError):
        return None
    if target.is_file():
        return target
    return None


def outbound_content_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return _CONTENT_TYPES.get(suffix, "application/octet-stream")
