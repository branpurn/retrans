"""Local RTMP credential store. Never log or echo secrets.

Sign in = persist Media Studio RTMP URL+key once (or set env).
Env RETRANS_X_RTMP_URL / RETRANS_X_RTMP_KEY wins over the file on read.
File: $XDG_CONFIG_HOME/retrans/credentials.json (else ~/.config/retrans/…), mode 0600.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from retrans.config import RTMP_KEY_ENV, RTMP_URL_ENV

CREDENTIALS_FILENAME = "credentials.json"


def credentials_path() -> Path:
    xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "retrans" / CREDENTIALS_FILENAME


def _pair(url: object, key: object) -> tuple[str, str] | None:
    if not isinstance(url, str) or not isinstance(key, str):
        return None
    url = url.strip()
    key = key.strip()
    if not url or not key:
        return None
    return url, key


def env_credentials() -> tuple[str, str] | None:
    return _pair(os.environ.get(RTMP_URL_ENV, ""), os.environ.get(RTMP_KEY_ENV, ""))


def file_credentials(path: Path | None = None) -> tuple[str, str] | None:
    target = path or credentials_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return _pair(data.get("rtmp_url"), data.get("rtmp_key"))


def load_credentials() -> tuple[str, str] | None:
    """Env pair wins over file pair. Do not mix env URL with file key."""
    return env_credentials() or file_credentials()


def is_configured() -> bool:
    return load_credentials() is not None


def save_credentials(rtmp_url: str, rtmp_key: str, path: Path | None = None) -> Path:
    """Write URL+key to the local file at mode 0600. Does not log secrets."""
    target = path or credentials_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    payload = json.dumps({"rtmp_url": rtmp_url, "rtmp_key": rtmp_key}, separators=(",", ":"))
    tmp = target.with_name(target.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target


def delete_credentials(path: Path | None = None) -> None:
    """Remove the credentials file. Does not unset process env."""
    target = path or credentials_path()
    try:
        target.unlink()
    except FileNotFoundError:
        return
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        return
