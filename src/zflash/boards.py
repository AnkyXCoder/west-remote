# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Board profiles: built-ins plus user-supplied YAML in boards.d directories."""

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional

import yaml

USER_BOARDS_DIR = Path.home() / ".config" / "zflash" / "boards.d"
PROJECT_BOARDS_FILE = "zflash.boards.yaml"


@dataclass
class BoardProfile:
    name: str
    description: str = ""
    runner: str = "jlink"  # jlink | pyocd | blhost
    artifact: str = "zephyr.hex"
    jlink_device: str = ""
    jlink_speed: int = 4000
    jlink_if: str = "SWD"
    bin_addr: str = "0x0"  # only used for raw .bin artifacts on jlink
    pyocd_target: str = ""
    blhost_port: str = "/dev/ttyUSB0"
    blhost_cmds: List[str] = field(default_factory=list)


def _load_profiles_file(path: Path) -> List[BoardProfile]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [BoardProfile(**b) for b in data.get("boards", [])]


def load_boards(project_dir: Optional[Path] = None) -> Dict[str, BoardProfile]:
    """Return all known profiles; later sources override earlier ones."""
    profiles: Dict[str, BoardProfile] = {}

    builtin = resources.files("zflash").joinpath("boards_builtin.yaml")
    for profile in _load_profiles_file(Path(str(builtin))):
        profiles[profile.name] = profile

    if USER_BOARDS_DIR.is_dir():
        for path in sorted(USER_BOARDS_DIR.glob("*.yaml")):
            for profile in _load_profiles_file(path):
                profiles[profile.name] = profile

    start = (project_dir or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        candidate = directory / PROJECT_BOARDS_FILE
        if candidate.is_file():
            for profile in _load_profiles_file(candidate):
                profiles[profile.name] = profile
            break

    return profiles


def get_board(name: str, project_dir: Optional[Path] = None) -> BoardProfile:
    profiles = load_boards(project_dir)
    if name not in profiles:
        known = ", ".join(sorted(profiles))
        raise KeyError(f"unknown board profile '{name}'. Known profiles: {known}")
    return profiles[name]
