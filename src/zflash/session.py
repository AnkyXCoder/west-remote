# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Reusable SSH sessions via OpenSSH connection multiplexing.

`west remote connect` opens a ControlMaster; subsequent commands reuse it
through ControlPath so the user authenticates once. Credentials are always
entered by the real ssh(1) — this module never sees them.
"""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from zflash.config import Config

_DEFAULT_PERSIST_MINUTES = 30


class SessionError(RuntimeError):
    pass


def _run_dir() -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".cache" / "zflash"))
    path = base / "run"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def _connection_key(cfg: Config) -> str:
    material = "\0".join([cfg.server.host, *cfg.server.ssh_options])
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def socket_path(cfg: Config) -> Path:
    return _run_dir() / f"zflash-{os.getuid()}-{_connection_key(cfg)}.sock"


def persist_seconds(cfg: Config) -> int:
    minutes = getattr(cfg.server, "persist_minutes", _DEFAULT_PERSIST_MINUTES)
    return int(minutes) * 60


def _mux_options(cfg: Config, *, master: bool, batch: bool) -> List[str]:
    opts: List[str] = []
    if batch:
        opts += ["-o", "BatchMode=yes"]
    if master:
        opts += ["-o", "ControlMaster=yes"]
    else:
        opts += ["-o", "ControlMaster=no"]
    opts += [
        "-o",
        f"ControlPath={socket_path(cfg)}",
        "-o",
        f"ControlPersist={persist_seconds(cfg)}",
    ]
    return opts


def ssh_argv(cfg: Config, remote_cmd: Optional[str] = None, *, batch: bool = True):
    """Argument list for a remote command. No shell=True anywhere."""
    argv = ["ssh", *_mux_options(cfg, master=False, batch=batch)]
    if batch:
        argv.append("-o")
        argv.append("ControlPersist=no")
    argv += cfg.server.ssh_options
    argv.append(cfg.server.host)
    if remote_cmd is not None:
        argv.append(remote_cmd)
    return argv


def rsync_ssh_opts(cfg: Config) -> str:
    """-e string for rsync, reusing the session socket without prompting."""
    sock = str(socket_path(cfg))
    opts = " ".join(cfg.server.ssh_options)
    return (
        f"ssh -o BatchMode=yes -o ControlMaster=no -o ControlPath={sock} "
        f"-o ControlPersist=no {opts}".strip()
    )


def is_connected(cfg: Config) -> bool:
    rc = subprocess.run(
        ["ssh", "-O", "check", "-o", f"ControlPath={socket_path(cfg)}", cfg.server.host],
        capture_output=True,
    ).returncode
    return rc == 0


def connect(cfg: Config) -> Tuple[bool, str]:
    """Open the master connection. Returns (ok, message).

    Unlike slave commands this allows interactive auth: the password or key
    passphrase prompt goes straight to the user's tty.
    """
    if is_connected(cfg):
        return True, "already connected"

    stale = socket_path(cfg)
    if stale.exists():
        stale.unlink(missing_ok=True)

    # -f backgrounds ssh after authentication; -N runs no remote command.
    argv = [
        "ssh",
        "-f",
        "-N",
        *_mux_options(cfg, master=True, batch=False),
        *cfg.server.ssh_options,
        cfg.server.host,
    ]
    proc = subprocess.run(argv)
    if proc.returncode != 0:
        return False, f"ssh exited with status {proc.returncode}"

    if is_connected(cfg):
        minutes = persist_seconds(cfg) // 60
        return True, f"connected (session kept {minutes} min idle)"
    return False, "connection established but control socket not visible"


def disconnect(cfg: Config) -> Tuple[bool, str]:
    if not socket_path(cfg).exists():
        return True, "not connected"
    proc = subprocess.run(
        ["ssh", "-O", "exit", "-o", f"ControlPath={socket_path(cfg)}", cfg.server.host],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stderr.strip() or proc.stdout.strip())


def status(cfg: Config) -> str:
    return "connected" if is_connected(cfg) else "not connected"


def require_session(cfg: Config) -> None:
    """Raise a clear error if the caller asked for sessions and none exists."""
    if getattr(cfg.server, "require_session", True) and not is_connected(cfg):
        raise SessionError(
            f"no active SSH session for '{cfg.server.host}'. "
            "Run 'west remote connect' first (or disable server.require_session)."
        )
