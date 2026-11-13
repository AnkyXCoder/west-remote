# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""J-Link runner: drives JLinkExe/JLinkExeCommander with a commander script.

Probe selection mirrors west's jlink runner:
  numeric serial        -> -USB <serial>
  existing file (tty)   -> -USB <path>
  IPv4 or tunnel:<name> -> -IP <value>
"""

import ipaddress
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from zflash.boards import BoardProfile
from zflash.config import FlashConfig


def _detect_dev_id_type(dev_id: str) -> str:
    if re.match(r"^[0-9]+$", dev_id):
        return "serialno"
    if os.path.exists(dev_id):
        return "tty"
    candidate = dev_id[len("tunnel:") :] if dev_id.startswith("tunnel:") else dev_id
    try:
        ipaddress.ip_address(candidate)
        return "ip"
    except ValueError:
        pass
    if dev_id.startswith("tunnel:"):
        return "tunnel"
    return "unknown"


class JlinkRunner:
    def __init__(self, profile: BoardProfile, cfg: FlashConfig):
        self.profile = profile
        self.cfg = cfg

    def _commander_script(self, artifact: Path) -> str:
        if artifact.suffix.lower() == ".bin":
            load = f"loadfile {artifact} {self.profile.bin_addr}"
        else:
            load = f"loadfile {artifact}"
        return f"{load}\nr\ng\nexit\n"

    def _exe(self) -> str:
        for name in ("JLinkExeCommander", "JLinkExe"):
            path = shutil.which(name)
            if path:
                return path
        raise FileNotFoundError(
            "JLinkExeCommander/JLinkExe not found on PATH. "
            "Install SEGGER J-Link tools or use -r pyocd."
        )

    def _probe_args(self) -> List[str]:
        dev_id = self.cfg.jlink_dev_id or self.cfg.probe
        if not dev_id:
            return []
        kind = _detect_dev_id_type(dev_id)
        if kind in ("serialno", "tty", "unknown"):
            return ["-USB", dev_id]
        return ["-IP", dev_id]

    def flash(self, artifact: Path, dry_run: bool = False):
        if not self.profile.jlink_device:
            raise ValueError(
                f"board profile '{self.profile.name}' has no jlink_device; "
                "set one in your board YAML"
            )

        script = self._commander_script(artifact)
        cmd = [
            self._exe() if not dry_run else "JLinkExe",
            "-device",
            self.profile.jlink_device,
            "-if",
            self.profile.jlink_if,
            "-speed",
            str(self.profile.jlink_speed),
            *self._probe_args(),
        ]

        if dry_run:
            print(f"[dry-run] {' '.join(cmd)} -CommanderScript <script>")
            print(f"[dry-run] script:\n{script}")
            return 0

        with tempfile.NamedTemporaryFile(
            "w", suffix=".jlink", delete=False
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            rc = subprocess.call(cmd + ["-CommanderScript", script_path])
            return rc
        finally:
            Path(script_path).unlink(missing_ok=True)
