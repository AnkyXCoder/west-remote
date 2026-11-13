# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""blhost runner: NXP UART/SPI bootloader command sequences (e.g. RW612).

Commands are built as argument lists — no shell interpolation. Templates may
use {port} and {artifact}; erase operations require explicit confirmation
via flash.confirm_erase or an interactive prompt.
"""

import shlex
import shutil
import subprocess
from pathlib import Path

from zflash.boards import BoardProfile
from zflash.config import FlashConfig

_DESTRUCTIVE = ("erase", "fill-memory")


def _is_destructive(template: str) -> bool:
    lowered = template.lower()
    return any(word in lowered for word in _DESTRUCTIVE)


class BlhostRunner:
    def __init__(self, profile: BoardProfile, cfg: FlashConfig):
        self.profile = profile
        self.cfg = cfg

    def _confirmed(self) -> bool:
        if self.cfg.confirm_erase:
            return True
        try:
            answer = input(
                "This sequence erases device memory. Type 'erase' to continue: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        return answer == "erase"

    def flash(self, artifact: Path, dry_run: bool = False):
        port = self.cfg.blhost_port or self.profile.blhost_port
        if not self.profile.blhost_cmds:
            raise ValueError(f"board profile '{self.profile.name}' has no blhost_cmds")

        destructive = any(_is_destructive(t) for t in self.profile.blhost_cmds)
        if destructive and not dry_run and not self._confirmed():
            print("aborted: erase not confirmed")
            return 2

        if not dry_run and shutil.which("blhost") is None:
            raise FileNotFoundError("blhost not found on PATH")

        for template in self.profile.blhost_cmds:
            rendered = template.format(port=port, artifact=artifact)
            cmd = ["blhost", "-p", port] + shlex.split(rendered)
            if dry_run:
                print(f"[dry-run] {' '.join(shlex.quote(c) for c in cmd)}")
                continue
            rc = subprocess.call(cmd)
            if rc != 0:
                return rc
        return 0
