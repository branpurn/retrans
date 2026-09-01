"""Bind lock: serve is 127.0.0.1 only. HOST=0.0.0.0 is a hard refuse."""

from __future__ import annotations

import pytest

from retrans.cli import main
from retrans.serve import BindRefused, normalize_bind_host, serve_forever


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "*", "192.168.0.1", "10.1.2.3", "172.16.0.8"],
)
def test_off_loopback_hosts_refused(host: str):
    with pytest.raises(BindRefused, match="loopback-only"):
        normalize_bind_host(host)


def test_env_wildcard_refused(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    with pytest.raises(BindRefused, match="0.0.0.0"):
        normalize_bind_host(None)


def test_serve_forever_does_not_bind_wildcard():
    with pytest.raises(BindRefused, match="0.0.0.0"):
        serve_forever(host="0.0.0.0", port=8788)


def test_cli_serve_env_wildcard_nonzero(monkeypatch, capsys):
    monkeypatch.setenv("HOST", "0.0.0.0")
    assert main(["serve"]) == 2
    assert capsys.readouterr().err
