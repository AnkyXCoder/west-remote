# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

import pytest

from zflash import session
from zflash.config import Config, ServerConfig


def _cfg(**kw):
    return Config(server=ServerConfig(host="build@server", **kw))


def test_socket_path_is_private_and_stable():
    cfg = _cfg()
    p = session.socket_path(cfg)
    assert p.name.startswith("zflash-")
    assert p.suffix == ".sock"
    assert session.socket_path(cfg) == p
    # different host -> different socket
    cfg2 = _cfg()
    cfg2.server.host = "other@server"
    assert session.socket_path(cfg2) != p


def test_ssh_argv_uses_mux_and_batch():
    argv = session.ssh_argv(_cfg(), "echo hi")
    assert argv[0] == "ssh"
    assert "-o" in argv and "BatchMode=yes" in argv
    assert "ControlMaster=no" in argv
    assert "ControlPersist=no" in argv
    assert any("ControlPath=" in a for a in argv)
    assert argv[-2:] == ["build@server", "echo hi"]


def test_connect_argv_allows_interactive_auth():
    # connect() builds its argv inline; verify the option helper instead
    opts = session._mux_options(_cfg(), master=True, batch=False)
    assert "BatchMode=yes" not in opts
    assert "ControlMaster=yes" in opts
    assert any("ControlPersist=" in o for o in opts)


def test_rsync_opts_share_socket():
    cfg = _cfg()
    opts = session.rsync_ssh_opts(cfg)
    assert f"ControlPath={session.socket_path(cfg)}" in opts
    assert "BatchMode=yes" in opts
    assert "ControlMaster=no" in opts


def test_require_session_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    cfg = _cfg()
    with pytest.raises(session.SessionError, match="west remote connect"):
        session.require_session(cfg)


def test_require_session_disabled():
    cfg = _cfg(require_session=False)
    session.require_session(cfg)  # no raise even without a master
