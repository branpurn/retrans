"""Bind lock: host 127.0.0.1; container veth 0.0.0.0; LAN refused.

Host publish is -p 127.0.0.1:8788:8788. Never a host 0.0.0.0 publish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import retrans.serve as serve_mod
from retrans.cli import main
from retrans.serve import (
    BindRefused,
    CONTAINER_BIND_HOST,
    ensure_loopback_bind,
    normalize_bind_host,
    serve_forever,
)

HOST_LOOPBACK = "127.0.0.1"
LAN_HOSTS = ("192.168.0.1", "10.1.2.3", "172.16.0.8")


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "*", *LAN_HOSTS],
)
def test_off_loopback_hosts_refused(host: str):
    with pytest.raises(BindRefused, match="loopback-only"):
        normalize_bind_host(host)


def test_host_bind_is_loopback(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: False)
    assert normalize_bind_host(None) == HOST_LOOPBACK
    assert normalize_bind_host(HOST_LOOPBACK) == HOST_LOOPBACK
    assert normalize_bind_host("localhost") == HOST_LOOPBACK
    ensure_loopback_bind(HOST_LOOPBACK, 8788)


def test_env_wildcard_refused(monkeypatch):
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: False)
    monkeypatch.setenv("HOST", "0.0.0.0")
    with pytest.raises(BindRefused, match="0.0.0.0"):
        normalize_bind_host(None)


def test_serve_forever_does_not_bind_wildcard_on_host(monkeypatch):
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: False)
    with pytest.raises(BindRefused, match="0.0.0.0"):
        serve_forever(host="0.0.0.0", port=8788)


def test_cli_serve_env_wildcard_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: False)
    monkeypatch.setenv("HOST", "0.0.0.0")
    assert main(["serve"]) == 2
    assert capsys.readouterr().err


def test_container_bind_is_veth_wildcard(monkeypatch):
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: True)
    monkeypatch.delenv("HOST", raising=False)
    assert normalize_bind_host(None) == CONTAINER_BIND_HOST
    assert normalize_bind_host(HOST_LOOPBACK) == CONTAINER_BIND_HOST
    assert normalize_bind_host("localhost") == CONTAINER_BIND_HOST
    assert normalize_bind_host("0.0.0.0") == CONTAINER_BIND_HOST
    ensure_loopback_bind(CONTAINER_BIND_HOST, 8788)


@pytest.mark.parametrize("host", LAN_HOSTS)
def test_container_still_refuses_lan(monkeypatch, host: str):
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: True)
    with pytest.raises(BindRefused, match="loopback-only"):
        normalize_bind_host(host)


def test_container_serve_listens_on_veth_not_host_lan(monkeypatch):
    monkeypatch.setattr(serve_mod, "running_in_container", lambda: True)
    monkeypatch.delenv("HOST", raising=False)
    seen: dict[str, tuple[str, int]] = {}

    class _FakeServer:
        def __init__(self, addr, _handler):
            seen["addr"] = addr

        def serve_forever(self):
            return None

        def server_close(self):
            return None

    monkeypatch.setattr(serve_mod, "ThreadingHTTPServer", _FakeServer)
    serve_forever(host=None, port=8788)
    assert seen["addr"] == (CONTAINER_BIND_HOST, 8788)
    assert seen["addr"][0] != HOST_LOOPBACK


def test_readme_does_not_claim_host_wildcard_publish():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "-p 0.0.0.0:8788" not in readme
    assert "0.0.0.0:8788:8788" not in readme
    assert "-p 127.0.0.1:8788:8788" in readme
    assert "--name retrans" in readme
    assert "retrans serve" in readme
    assert "NOT `--network host`" in readme
    run_line = next(line for line in readme.splitlines() if "docker run --rm --init" in line)
    assert "--name retrans" in run_line
    assert "retrans serve" in run_line
    assert "--network host" not in run_line
    assert "0.0.0.0" not in run_line


def test_readme_headless_has_no_host_wildcard_or_publish():
    readme = Path("README.md").read_text(encoding="utf-8")
    live_line = next(
        line for line in readme.splitlines() if "docker run" in line and "retrans live" in line
    )
    assert "-p" not in live_line
    assert "0.0.0.0" not in live_line
    assert "--network host" not in live_line
    assert "RETRANS_X_RTMP_KEY" in readme
