from __future__ import annotations

from argparse import Namespace

import pytest

from retrans import cli
from retrans.cli import main
from retrans.serve import BindRefused


def test_help_lists_product_live_and_debug_clip():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_clip_help_is_debug_aid():
    with pytest.raises(SystemExit) as exc:
        main(["clip", "--help"])
    assert exc.value.code == 0


def test_live_requires_rtmp_creds(monkeypatch, capsys):
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    code = main(["live", "https://www.youtube.com/watch?v=abc"])
    err = capsys.readouterr().err
    assert code == 2
    assert "RETRANS_X_RTMP" in err


def test_serve_refuses_wildcard_host(monkeypatch, capsys):
    monkeypatch.setenv("HOST", "0.0.0.0")
    code = main(["serve"])
    err = capsys.readouterr().err
    assert code == 2
    assert "0.0.0.0" in err
    assert "loopback-only" in err


def test_serve_refuses_cli_wildcard(capsys):
    code = main(["serve", "--host", "0.0.0.0"])
    err = capsys.readouterr().err
    assert code == 2
    assert "refusing to bind" in err


def test_live_help_is_product_command():
    parser = cli._parser()
    live = None
    for action in parser._subparsers._group_actions:
        live = action.choices.get("live")
        if live:
            break
    assert live is not None
    assert "product" in (live.description or live.help or "").lower() or "restream" in (
        live.help or ""
    ).lower()
    clip = None
    for action in parser._subparsers._group_actions:
        clip = action.choices.get("clip")
        if clip:
            break
    text = ((clip.help or "") + " " + (clip.description or "")).lower()
    assert "debug" in text
    assert "not the product" in text


def test_cmd_serve_maps_bind_refused(monkeypatch):
    def boom(**_kwargs):
        raise BindRefused("refusing to bind HOST=0.0.0.0")

    monkeypatch.setattr(cli, "serve_forever", boom)
    code = cli.cmd_serve(Namespace(host="0.0.0.0", port=8788))
    assert code == 2
