# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""pyOCD runner: local probe or remote probe server (remote:<host>:<port>).

Uses pyocd's default sector erase — never a full chip erase unless the user
explicitly asks for one via profile/CLI.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List

from zflash.boards import BoardProfile
from zflash.config import FlashConfig


class PyocdRunner:
    def __init__(self, profile: BoardProfile, cfg: FlashConfig):
        self.profile = profile
        self.cfg = cfg

    def _base(self) -> List[str]:
        cmd = ["pyocd"]
        target = self.profile.pyocd_target
        if target:
            cmd += ["-t", target]
        uid = self.cfg.pyocd_uid or self.cfg.probe
        if uid:
            # Also serves "remote:<host>:<port>" probes from `pyocd server`.
            cmd += ["-u", uid]
        return cmd

    def flash(self, artifact: Path, dry_run: bool = False):
        cmd = self._base() + ["load"]
        if artifact.suffix.lower() == ".bin":
            cmd += ["--base-address", self.profile.bin_addr]
        cmd.append(str(artifact))

        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
            print(f"[dry-run] {' '.join(self._base() + ['reset'])}")
            return 0

        if shutil.which("pyocd") is None:
            raise FileNotFoundError("pyocd not found on PATH. pip install pyocd")

        rc = subprocess.call(cmd)
        if rc != 0:
            return rc
        return subprocess.call(self._base() + ["reset"])
