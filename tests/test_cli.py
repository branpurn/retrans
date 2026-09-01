from __future__ import annotations

import os
from argparse import Namespace

import pytest

from retrans import cli
from retrans.cli import main
from retrans.config import DEFAULT_RTMP_URL, load_env_file
from retrans.ingest import NotLiveError
from retrans.outputs.x import RestreamError, XLiveRestream
from retrans.serve import BindRefused

PLACEHOLDER_KEY = "placeholder-stream-key-not-a-secret"
VOD_URL = "https://www.youtube.com/watch?v=vodclip"
LIVE_URL = "https://www.youtube.com/watch?v=abc"


def _capture(capsys) -> tuple[str, str]:
    captured = capsys.readouterr()
    return captured.out, captured.err


def _assert_no_secret(out: str, err: str, secret: str = PLACEHOLDER_KEY) -> None:
    blob = out + err
    assert secret not in blob
    assert secret.lower() not in blob.lower()


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
    clip = None
    for action in parser._subparsers._group_actions:
        live = live or action.choices.get("live")
        clip = clip or action.choices.get("clip")
    assert live is not None
    help_text = parser.format_help().lower()
    assert "product" in help_text or "restream" in help_text
    assert clip is not None
    clip_text = clip.format_help().lower()
    assert "debug" in clip_text
    assert "not the product" in clip_text


def test_cmd_serve_maps_bind_refused(monkeypatch):
    def boom(**_kwargs):
        raise BindRefused("refusing to bind HOST=0.0.0.0")

    monkeypatch.setattr(cli, "serve_forever", boom)
    code = cli.cmd_serve(Namespace(host="0.0.0.0", port=8788))
    assert code == 2


def test_live_uses_env_key_and_default_rtmp(monkeypatch, capsys):
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.setenv("RETRANS_X_RTMP_KEY", PLACEHOLDER_KEY)
    received: dict[str, str] = {}

    class Fake:
        def run_foreground(self, source_url, rtmp_url, rtmp_key):
            received["source"] = source_url
            received["url"] = rtmp_url
            received["key"] = rtmp_key
            return 0

    monkeypatch.setattr(cli, "XLiveRestream", Fake)
    code = main(["live", LIVE_URL, "--title", "Press Conference"])
    out, err = _capture(capsys)
    assert code == 0
    assert received["source"] == LIVE_URL
    assert received["url"] == DEFAULT_RTMP_URL
    assert received["url"] == "rtmps://va.pscp.tv:443/x"
    assert received["key"] == PLACEHOLDER_KEY
    assert "Press Conference" in out
    _assert_no_secret(out, err)


def test_live_env_file_key_not_echoed(monkeypatch, capsys, tmp_path):
    secret = "envfile-placeholder-key-xyz"
    envf = tmp_path / "live.env"
    envf.write_text(
        "\n".join(
            [
                f"RETRANS_X_RTMP_KEY={secret}",
                f"SOURCE_URL={LIVE_URL}",
                "RETRANS_TITLE=Standup",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.delenv("SOURCE_URL", raising=False)
    monkeypatch.delenv("RETRANS_TITLE", raising=False)
    received: dict[str, str] = {}

    class Fake:
        def run_foreground(self, source_url, rtmp_url, rtmp_key):
            received["source"] = source_url
            received["url"] = rtmp_url
            received["key"] = rtmp_key
            return 0

    monkeypatch.setattr(cli, "XLiveRestream", Fake)
    code = main(["live", "--env-file", str(envf)])
    out, err = _capture(capsys)
    assert code == 0
    assert received["source"] == LIVE_URL
    assert received["url"] == DEFAULT_RTMP_URL
    assert received["key"] == secret
    assert "Standup" in out
    blob = out + err
    assert secret not in blob
    assert "envfile-placeholder" not in blob


def test_live_env_file_does_not_override_existing_env(monkeypatch, tmp_path):
    envf = tmp_path / "live.env"
    envf.write_text(f"RETRANS_X_RTMP_KEY={PLACEHOLDER_KEY}\n", encoding="utf-8")
    monkeypatch.setenv("RETRANS_X_RTMP_KEY", "already-set-placeholder")
    load_env_file(envf)
    assert os.environ["RETRANS_X_RTMP_KEY"] == "already-set-placeholder"


def test_live_accepts_title_from_flag_and_env(monkeypatch, capsys):
    monkeypatch.setenv("RETRANS_X_RTMP_KEY", PLACEHOLDER_KEY)
    monkeypatch.setenv("RETRANS_TITLE", "Env Title")

    class Fake:
        def run_foreground(self, *_a, **_k):
            return 0

    monkeypatch.setattr(cli, "XLiveRestream", Fake)
    code = main(["live", LIVE_URL, "--title", "Flag Title"])
    out, err = _capture(capsys)
    assert code == 0
    assert "Flag Title" in out
    assert "Env Title" not in out
    _assert_no_secret(out, err)

    monkeypatch.delenv("RETRANS_TITLE", raising=False)
    monkeypatch.setenv("TITLE", "Alias Title")
    code = main(["live", LIVE_URL])
    out, err = _capture(capsys)
    assert code == 0
    assert "Alias Title" in out
    _assert_no_secret(out, err)


def test_live_rejects_vod_before_ffmpeg(monkeypatch, capsys):
    monkeypatch.setenv("RETRANS_X_RTMP_KEY", PLACEHOLDER_KEY)
    spawned: list = []

    class Resolver:
        def require_live(self, page_url: str) -> None:
            raise NotLiveError(
                "source is not a live stream (not_live); VOD and clips are rejected"
            )

        def resolve(self, page_url: str) -> str:
            raise AssertionError("must not resolve stream URL for VOD")

    def popen(*_a, **_k):
        spawned.append(True)
        raise AssertionError("ffmpeg must not start for VOD")

    monkeypatch.setattr(
        cli,
        "XLiveRestream",
        lambda: XLiveRestream(resolver=Resolver(), popen=popen),
    )
    code = main(["live", VOD_URL, "--title", "VOD Attempt"])
    out, err = _capture(capsys)
    assert code == 1
    assert spawned == []
    assert "VOD" in err or "not a live stream" in err
    assert "VOD Attempt" in out
    _assert_no_secret(out, err)


def test_live_missing_key_does_not_echo_placeholder(monkeypatch, capsys):
    monkeypatch.delenv("RETRANS_X_RTMP_URL", raising=False)
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    code = main(["live", LIVE_URL, "--title", "No Key"])
    out, err = _capture(capsys)
    assert code == 2
    assert "RETRANS_X_RTMP_KEY" in err or "RETRANS_X_RTMP" in err
    _assert_no_secret(out, err)


def test_live_source_url_from_env(monkeypatch, capsys):
    monkeypatch.setenv("RETRANS_X_RTMP_KEY", PLACEHOLDER_KEY)
    monkeypatch.setenv("SOURCE_URL", LIVE_URL)
    received: dict[str, str] = {}

    class Fake:
        def run_foreground(self, source_url, rtmp_url, rtmp_key):
            received["source"] = source_url
            received["url"] = rtmp_url
            return 0

    monkeypatch.setattr(cli, "XLiveRestream", Fake)
    code = main(["live", "--title", "From Env"])
    out, err = _capture(capsys)
    assert code == 0
    assert received["source"] == LIVE_URL
    assert received["url"] == DEFAULT_RTMP_URL
    assert "From Env" in out
    _assert_no_secret(out, err)


def test_live_flag_key_not_echoed(monkeypatch, capsys):
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    received: dict[str, str] = {}

    class Fake:
        def run_foreground(self, source_url, rtmp_url, rtmp_key):
            received["key"] = rtmp_key
            received["url"] = rtmp_url
            return 0

    monkeypatch.setattr(cli, "XLiveRestream", Fake)
    code = main(
        ["live", LIVE_URL, "--rtmp-key", PLACEHOLDER_KEY, "--title", "Flag Key"]
    )
    out, err = _capture(capsys)
    assert code == 0
    assert received["key"] == PLACEHOLDER_KEY
    assert received["url"] == DEFAULT_RTMP_URL
    _assert_no_secret(out, err)


def test_live_error_redacts_key(monkeypatch, capsys):
    monkeypatch.setenv("RETRANS_X_RTMP_KEY", PLACEHOLDER_KEY)

    class Fake:
        def run_foreground(self, source_url, rtmp_url, rtmp_key):
            raise RestreamError(f"boom dest={rtmp_url}/{rtmp_key}")

    monkeypatch.setattr(cli, "XLiveRestream", Fake)
    code = main(["live", LIVE_URL, "--title", "Boom"])
    out, err = _capture(capsys)
    assert code == 1
    _assert_no_secret(out, err)
    assert PLACEHOLDER_KEY not in err


def test_load_env_file_ignores_comments_and_quotes(monkeypatch, tmp_path):
    envf = tmp_path / "quoted.env"
    envf.write_text(
        "# comment\n"
        f'export RETRANS_X_RTMP_KEY="{PLACEHOLDER_KEY}"\n'
        "SOURCE_URL='https://www.youtube.com/watch?v=abc'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("RETRANS_X_RTMP_KEY", raising=False)
    monkeypatch.delenv("SOURCE_URL", raising=False)
    load_env_file(envf)
    assert os.environ["RETRANS_X_RTMP_KEY"] == PLACEHOLDER_KEY
    assert os.environ["SOURCE_URL"] == LIVE_URL
