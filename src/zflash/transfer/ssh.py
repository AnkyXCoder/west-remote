# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""SSH/rsync backend for unverified workspace artifacts (compat mode).

Verified deployments go through zflash.bundles instead; this backend remains
for browsing raw build output that was never published.
"""

import shlex
import subprocess
from pathlib import Path
from typing import List

from zflash.artifact import Artifact, FLASHABLE_SUFFIXES
from zflash.config import Config
from zflash import session

_FIND_FMT = "%T@ %s %p"


def _name_filters() -> str:
    names = " -o ".join(f"-name '*{sfx}'" for sfx in FLASHABLE_SUFFIXES)
    return f"\\( {names} \\)"


class SshBackend:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if not cfg.server.host:
            raise ValueError(
                "no server host configured. Set server.host in "
                "~/.config/zflash/config.yaml or $ZFLASH_HOST"
            )
        session.require_session(cfg)

    def _ssh_cmd(self, remote_cmd: str) -> str:
        proc = subprocess.run(
            session.ssh_argv(self.cfg, remote_cmd),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"ssh command failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc.stdout

    def list_artifacts(self) -> List[Artifact]:
        roots = " ".join(shlex.quote(r) for r in self.cfg.server.artifact_roots)
        cmd = (
            f"find {roots} -type f {_name_filters()} "
            f"-not -path '*/modules/*' -printf '{_FIND_FMT}\\n' 2>/dev/null | sort -rn"
        )
        out = self._ssh_cmd(cmd)

        artifacts: List[Artifact] = []
        for line in out.splitlines():
            try:
                mtime, size, path = line.split(" ", 2)
            except ValueError:
                continue
            remote_dir, _, filename = path.rpartition("/")
            name = self._display_name(remote_dir, filename)
            artifacts.append(
                Artifact(
                    name=name,
                    remote_dir=remote_dir,
                    filename=filename,
                    size=int(size),
                    mtime=float(mtime),
                )
            )
        return artifacts

    def _display_name(self, remote_dir: str, filename: str) -> str:
        for root in self.cfg.server.artifact_roots:
            if remote_dir.startswith(root):
                remote_dir = remote_dir[len(root) :].lstrip("/")
                break
        return f"{remote_dir}/{filename}" if remote_dir else filename

    def pull(self, artifact: Artifact, dest_dir: Path) -> Path:
        """rsync every flashable sibling in the artifact's remote directory."""
        dest_dir = Path(dest_dir).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        includes = " ".join(f"--include='*{sfx}'" for sfx in FLASHABLE_SUFFIXES)
        remote = shlex.quote(f"{self.cfg.server.host}:{artifact.remote_dir}/")
        cmd = (
            f"rsync -az --info=progress2 -e {shlex.quote(session.rsync_ssh_opts(self.cfg))} "
            f"{includes} --exclude='*' {remote} {shlex.quote(str(dest_dir))}/"
        )
        proc = subprocess.run(cmd, shell=True)
        if proc.returncode != 0:
            raise RuntimeError(f"rsync failed ({proc.returncode})")
        return dest_dir / artifact.filename
