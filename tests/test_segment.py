from __future__ import annotations

import retrans.segment as segment
from retrans.segment import build_clip_cmd, clip_help_epilog


def test_module_docstring_says_debug_only_not_product():
    doc = segment.__doc__ or ""
    assert "DEBUG ONLY" in doc
    assert "Not the product" in doc


def test_clip_help_says_debug_aid():
    text = clip_help_epilog().lower()
    assert "debug aid" in text
    assert "not the product" in text


def test_build_clip_cmd_uses_ffmpeg():
    cmd = build_clip_cmd("https://in.example/s", "/tmp/out.mp4", "0", "10")
    assert cmd[0] == "ffmpeg"
    assert "/tmp/out.mp4" in cmd
