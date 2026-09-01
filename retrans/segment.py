"""DEBUG ONLY clip cutter (ffmpeg). Not the product.

Wave 1 success is continuous live RTMP restream to the operator's X Media
Studio ingest — not clip-segment VOD posts. This module exists only as a
clearly labeled debug aid so an operator can cut a local sample. Do not
treat clip upload or clip posts as the product path.
"""

from __future__ import annotations

import subprocess
class ClipError(RuntimeError):
    """Debug clip cut failed."""


def build_clip_cmd(
    input_url: str,
    output_path: str,
    start: str,
    end: str,
) -> list[str]:
    """Return the ffmpeg argv for a debug-only clip cut."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        start,
        "-to",
        end,
        "-i",
        input_url,
        "-c",
        "copy",
        output_path,
    ]


def cut_clip(
    input_url: str,
    output_path: str,
    start: str,
    end: str,
    run: subprocess.run = subprocess.run,
) -> str:
    """Cut [start, end] from input_url into output_path. DEBUG ONLY."""
    cmd = build_clip_cmd(input_url, output_path, start, end)
    try:
        run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ClipError("ffmpeg is not installed") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ClipError(f"ffmpeg clip failed: {stderr}") from exc
    return output_path


def clip_help_epilog() -> str:
    return (
        "DEBUG AID only — not the product. Clip-segment VOD posts are not "
        "Wave 1 success. The product command is `retrans live`."
    )


__all__ = ["ClipError", "build_clip_cmd", "cut_clip", "clip_help_epilog"]
