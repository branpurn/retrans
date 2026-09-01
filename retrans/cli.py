"""RETRANS operator CLI.

Product commands:
  `retrans live`  — headless true-live ffmpeg worker (no HTTP UI).
  `retrans serve` — loopback live control API for the operator UI (8788).

`retrans clip` is a debug aid — not the product.
"""

from __future__ import annotations

import argparse
import os
import sys

from retrans.config import (
    DEFAULT_RTMP_URL,
    RTMP_KEY_ENV,
    RTMP_URL_ENV,
    SOURCE_URL_ENV,
    TITLE_ENV,
    TITLE_ENV_ALIAS,
    X_BEARER_ENV,
    env_value,
    load_env_file,
    redact,
)
from retrans.outputs.x import RestreamError, XLiveRestream, debug_chunked_upload_and_post
from retrans.segment import clip_help_epilog, cut_clip
from retrans.serve import BindRefused, serve_forever
from retrans.sources import resolve_page


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retrans",
        description=(
            "RETRANS: operator-run live restream. Resolve a page URL "
            "(YouTube first) and ffmpeg-restream H.264+AAC/FLV to the "
            "operator's X Media Studio RTMP source. There is no public X "
            "API to create a broadcast or mint an RTMP key."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    live = sub.add_parser(
        "live",
        help="Headless true-live ffmpeg restream (no HTTP UI; product command)",
    )
    live.add_argument(
        "page_url",
        nargs="?",
        default=None,
        help=f"Live page URL (YouTube first). Else {SOURCE_URL_ENV} / --source.",
    )
    live.add_argument(
        "--source",
        dest="source_url",
        default=None,
        help=f"Live source URL (else positional / {SOURCE_URL_ENV})",
    )
    live.add_argument(
        "--title",
        default=None,
        help=f"Operator label for this restream (else {TITLE_ENV} / {TITLE_ENV_ALIAS})",
    )
    live.add_argument(
        "--env-file",
        dest="env_file",
        default=None,
        help=f"Load KEY=VALUE file (prefer {RTMP_KEY_ENV}; values are never printed)",
    )
    live.add_argument(
        "--rtmp-url",
        default=None,
        help=f"Override ingest URL (default {DEFAULT_RTMP_URL}; else {RTMP_URL_ENV})",
    )
    live.add_argument(
        "--rtmp-key",
        default=None,
        help=f"Stream key (prefer {RTMP_KEY_ENV} / --env-file so the key is not in ps)",
    )

    resolve = sub.add_parser(
        "resolve",
        help="Print the resolved stream URL (input plugin sketch; YouTube first)",
    )
    resolve.add_argument("page_url")

    clip = sub.add_parser(
        "clip",
        help="DEBUG AID only — not the product. Optional ffmpeg clip cutter.",
        description=clip_help_epilog(),
    )
    clip.add_argument("page_url")
    clip.add_argument("--start", required=True, help="Clip start (ffmpeg -ss)")
    clip.add_argument("--end", required=True, help="Clip end (ffmpeg -to)")
    clip.add_argument("-o", "--output", required=True, help="Output media path")

    serve = sub.add_parser(
        "serve",
        help="HTTP control API (operator URL http://127.0.0.1:8788)",
    )
    serve.add_argument(
        "--host",
        default=None,
        help="Bind host (host: 127.0.0.1 only; container: 0.0.0.0; LAN refused)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default 8788)",
    )

    debug = sub.add_parser(
        "debug-upload",
        help="DEBUG AID only — chunked X media upload + create post (not live)",
    )
    debug.add_argument("media_file")
    debug.add_argument(
        "--text",
        default="",
        help="Post text. Do not include a URL. Requires " + X_BEARER_ENV,
    )
    return parser


def _apply_env_file(path: str | None) -> str | None:
    """Load --env-file. Return an error string or None. Never logs values."""
    if not path:
        return None
    try:
        load_env_file(path)
    except OSError:
        return "could not read --env-file"
    return None


def _source_from(args: argparse.Namespace) -> str:
    return (
        (args.page_url or "").strip()
        or (getattr(args, "source_url", None) or "").strip()
        or env_value(SOURCE_URL_ENV)
    )


def _title_from(args: argparse.Namespace) -> str:
    return (getattr(args, "title", None) or "").strip() or env_value(
        TITLE_ENV, TITLE_ENV_ALIAS
    )


def _rtmp_from(args: argparse.Namespace) -> tuple[str, str] | str:
    url = (
        (args.rtmp_url or "").strip()
        or env_value(RTMP_URL_ENV)
        or DEFAULT_RTMP_URL
    )
    key = (args.rtmp_key or "").strip() or env_value(RTMP_KEY_ENV)
    if not key:
        return (
            f"stream key required via {RTMP_KEY_ENV} or --env-file "
            f"(or --rtmp-key)"
        )
    return url, key


def _secrets(*extra: str | None) -> tuple[str, ...]:
    found = [env_value(RTMP_KEY_ENV)]
    found.extend(extra)
    return tuple(s for s in found if s)


def _print(msg: str, *secrets: str | None, file=None) -> None:
    text = redact(msg, *_secrets(*secrets))
    print(text, file=file, flush=True)


def cmd_live(args: argparse.Namespace) -> int:
    err = _apply_env_file(getattr(args, "env_file", None))
    if err:
        _print(err, file=sys.stderr)
        return 2
    source = _source_from(args)
    if not source:
        _print(
            f"source URL required via page_url / --source / {SOURCE_URL_ENV}",
            file=sys.stderr,
        )
        return 2
    creds = _rtmp_from(args)
    if isinstance(creds, str):
        _print(creds, file=sys.stderr)
        return 2
    rtmp_url, rtmp_key = creds
    title = _title_from(args)
    if title:
        _print(f"retrans live: {title}", rtmp_key)
    _print(
        "retrans live: resolving and restreaming (H.264+AAC/FLV → Media Studio)",
        rtmp_key,
    )
    _print(
        "Sending RTMP is not enough — Create Broadcast and Go Live in studio.x.com.",
        rtmp_key,
    )
    try:
        return XLiveRestream().run_foreground(source, rtmp_url, rtmp_key)
    except RestreamError as exc:
        _print(str(exc), rtmp_key, file=sys.stderr)
        return 1


def cmd_resolve(args: argparse.Namespace) -> int:
    resolved = resolve_page(args.page_url)
    print(resolved.stream_url)
    return 0


def cmd_clip(args: argparse.Namespace) -> int:
    print(clip_help_epilog(), file=sys.stderr)
    resolved = resolve_page(args.page_url)
    cut_clip(resolved.stream_url, args.output, args.start, args.end)
    print(args.output)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        print(
            "retrans serve: loopback UI + /api on http://127.0.0.1:8788 (no /api/clip)",
            flush=True,
        )
        print(
            "  GET /  GET/PUT /api/live/keys  DELETE /api/live/keys/<id>  "
            "PUT/GET/DELETE /api/live/credentials  "
            "POST /api/live/start  GET /api/live/status  POST /api/live/stop",
            flush=True,
        )
        serve_forever(host=args.host, port=args.port)
    except BindRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def cmd_debug_upload(args: argparse.Namespace) -> int:
    print(
        "DEBUG AID only — not the product. This is not a live broadcast.",
        file=sys.stderr,
    )
    result = debug_chunked_upload_and_post(args.media_file, text=args.text)
    print(result.get("data", result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    handlers = {
        "live": cmd_live,
        "resolve": cmd_resolve,
        "clip": cmd_clip,
        "serve": cmd_serve,
        "debug-upload": cmd_debug_upload,
    }
    try:
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        extra = getattr(args, "rtmp_key", None)
        _print(str(exc), extra, file=sys.stderr)
        return 1
