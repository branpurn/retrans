"""Named RTMP key store. Never log or echo secrets.

File: $XDG_CONFIG_HOME/retrans/keys.json (else ~/.config/retrans/…), mode 0600.
Default ingest when rtmp_url is omitted: rtmps://va.pscp.tv:443/x.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from retrans.outputs.x import RestreamError, join_rtmp_destination

KEYS_FILENAME = "keys.json"
DEFAULT_RTMP_URL = "rtmps://va.pscp.tv:443/x"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_lock = threading.Lock()


class DuplicateKeyNameError(ValueError):
    """Name already used by a different key id. Maps to HTTP 409."""


def keys_path() -> Path:
    xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "retrans" / KEYS_FILENAME


def _valid_id(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not _ID_RE.fullmatch(value):
        return None
    return value


def _nonempty(raw: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _public(record: dict[str, str]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "name": record["name"],
        "configured": bool(record.get("rtmp_key")),
    }


def _read_records(path: Path | None = None) -> list[dict[str, str]]:
    target = path or keys_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and isinstance(data.get("keys"), list):
        items = data["keys"]
    elif isinstance(data, list):
        items = data
    else:
        return []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kid = _valid_id(item.get("id"))
        name = _nonempty(item.get("name"))
        key = _nonempty(item.get("rtmp_key"))
        url = _nonempty(item.get("rtmp_url")) or DEFAULT_RTMP_URL
        if kid is None or name is None or key is None:
            continue
        out.append({"id": kid, "name": name, "rtmp_url": url, "rtmp_key": key})
    return out


def _write_records(records: list[dict[str, str]], path: Path | None = None) -> Path:
    target = path or keys_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    payload = json.dumps({"keys": records}, separators=(",", ":"))
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


def list_keys_public(path: Path | None = None) -> list[dict[str, Any]]:
    with _lock:
        return [_public(record) for record in _read_records(path)]


def get_key(key_id: str, path: Path | None = None) -> dict[str, str] | None:
    wanted = _valid_id(key_id)
    if wanted is None:
        return None
    with _lock:
        for record in _read_records(path):
            if record["id"] == wanted:
                return dict(record)
    return None


def upsert_key(
    *,
    name: str,
    rtmp_key: str,
    key_id: str | None = None,
    rtmp_url: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Create or update a named key. Returns public {id, name, configured}."""
    clean_name = _nonempty(name)
    clean_key = _nonempty(rtmp_key)
    if clean_name is None:
        raise ValueError("invalid fields: name")
    if clean_key is None:
        raise ValueError("invalid fields: rtmp_key")
    url = _nonempty(rtmp_url) or DEFAULT_RTMP_URL
    try:
        join_rtmp_destination(url, clean_key)
    except RestreamError as exc:
        raise ValueError("invalid fields: rtmp_url") from exc
    if key_id is None:
        new_id = uuid.uuid4().hex[:12]
    else:
        new_id = _valid_id(key_id)
        if new_id is None:
            raise ValueError("invalid fields: id")
    record = {
        "id": new_id,
        "name": clean_name,
        "rtmp_url": url,
        "rtmp_key": clean_key,
    }
    with _lock:
        records = _read_records(path)
        for existing in records:
            if existing["name"] == clean_name and existing["id"] != new_id:
                raise DuplicateKeyNameError("name already exists")
        replaced = False
        for i, existing in enumerate(records):
            if existing["id"] == new_id:
                records[i] = record
                replaced = True
                break
        if not replaced:
            records.append(record)
        _write_records(records, path)
    return _public(record)


def delete_key(key_id: str, path: Path | None = None) -> bool:
    wanted = _valid_id(key_id)
    if wanted is None:
        return False
    with _lock:
        records = _read_records(path)
        kept = [record for record in records if record["id"] != wanted]
        if len(kept) == len(records):
            return False
        if kept:
            _write_records(kept, path)
        else:
            target = path or keys_path()
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            tmp = target.with_name(target.name + ".tmp")
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        return True


def validate_key_payload(payload: Any) -> dict[str, str] | str:
    """Return upsert kwargs (id optional) or an error string. No secrets in errors."""
    if not isinstance(payload, dict):
        return "invalid fields"
    missing = [key for key in ("name", "rtmp_key") if key not in payload]
    if missing:
        return f"missing fields: {', '.join(missing)}"
    name = _nonempty(payload.get("name"))
    key = _nonempty(payload.get("rtmp_key"))
    if name is None:
        return "invalid fields: name"
    if key is None:
        return "invalid fields: rtmp_key"
    parsed: dict[str, str] = {"name": name, "rtmp_key": key}
    if "id" in payload:
        kid = _valid_id(payload.get("id"))
        if kid is None:
            return "invalid fields: id"
        parsed["id"] = kid
    if "rtmp_url" in payload:
        url = _nonempty(payload.get("rtmp_url"))
        if url is None:
            return "invalid fields: rtmp_url"
        try:
            join_rtmp_destination(url, key)
        except RestreamError:
            return "invalid fields: rtmp_url"
        parsed["rtmp_url"] = url
    else:
        try:
            join_rtmp_destination(DEFAULT_RTMP_URL, key)
        except RestreamError:
            return "invalid fields: rtmp_url"
    return parsed
