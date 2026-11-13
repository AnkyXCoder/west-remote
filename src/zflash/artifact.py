# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Artifact model: a flashable file found in a remote build directory."""

import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class Artifact:
    """A single flashable artifact on the server."""

    name: str  # human key, e.g. "gpio_test/build/zephyr.hex"
    remote_dir: str  # directory containing it (rsync/HTTP path key)
    filename: str  # e.g. "zephyr.hex"
    size: int = 0
    mtime: float = 0.0
    siblings: List[str] = field(default_factory=list)  # other flashables in dir

    @property
    def remote_path(self) -> str:
        return f"{self.remote_dir}/{self.filename}"

    @property
    def display_name(self) -> str:
        return self.name

    def age(self) -> str:
        if not self.mtime:
            return "?"
        delta = int(time.time() - self.mtime)
        if delta < 60:
            return f"{delta}s ago"
        if delta < 3600:
            return f"{delta // 60}m ago"
        if delta < 86400:
            return f"{delta // 3600}h ago"
        return f"{delta // 86400}d ago"


FLASHABLE_SUFFIXES = (".hex", ".bin", ".elf", ".s19", ".img")
