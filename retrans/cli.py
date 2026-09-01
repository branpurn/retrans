"""RETRANS operator CLI.

Product command: `retrans live` (page URL → ffmpeg RTMP to Media Studio).
`retrans serve` exposes the loopback live control API for the operator UI.
`retrans clip` is a debug aid — not the product.
"""

from __future__ import annotations

import argparse
import os
import sys

from retrans.config import RTMP_KEY_ENV, RTMP_URL_ENV, X_BEARER_ENV
from retrans.outputs.x import XLiveRestream, debug_chunked_upload_and_post
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
        help="Resolve a page URL and restream live to X Media Studio RTMP (product command)",
    )
    live.add_argument("page_url", help="Page URL that contains the live video (YouTube first)")
    live.add_argument(
        "--rtmp-url",
        default=None,
        help=f"Media Studio RTMP(S) URL (else {RTMP_URL_ENV})",
    )
    live.add_argument(
        "--rtmp-key",
        default=None,
        help=f"Media Studio stream key (else {RTMP_KEY_ENV})",
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


def _rtmp_from(args: argparse.Namespace) -> tuple[str, str] | str:
    url = args.rtmp_url or os.environ.get(RTMP_URL_ENV, "")
    key = args.rtmp_key or os.environ.get(RTMP_KEY_ENV, "")
    if not url or not key:
        return (
            f"RTMP URL and key required via --rtmp-url/--rtmp-key or "
            f"{RTMP_URL_ENV}/{RTMP_KEY_ENV}"
        )
    return url, key


def cmd_live(args: argparse.Namespace) -> int:
    creds = _rtmp_from(args)
    if isinstance(creds, str):
        print(creds, file=sys.stderr)
        return 2
    rtmp_url, rtmp_key = creds
    print("retrans live: resolving and restreaming (H.264+AAC/FLV → Media Studio)", flush=True)
    print("Sending RTMP is not enough — Create Broadcast and Go Live in studio.x.com.", flush=True)
    return XLiveRestream().run_foreground(args.page_url, rtmp_url, rtmp_key)


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
        print(str(exc), file=sys.stderr)
        return 1
