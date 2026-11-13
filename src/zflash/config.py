# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Configuration loading: defaults < user config < project config < env < CLI."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

USER_CONFIG = Path.home() / ".config" / "zflash" / "config.yaml"
PROJECT_CONFIG = "zflash.yaml"


@dataclass
class ServerConfig:
    """How to reach the build server."""

    transport: str = "ssh"  # ssh | http
    host: str = ""  # e.g. "build@server.local" (SSH config aliases work)
    ssh_options: List[str] = field(default_factory=list)
    # Remote directories scanned for unverified workspace builds (legacy mode).
    artifact_roots: List[str] = field(default_factory=lambda: ["zephyrproject"])
    http_url: str = ""  # e.g. "http://server.local:8765" (zflash serve)
    # SSH session behaviour.
    persist_minutes: int = 30
    # When true, commands require `west remote connect` first (BatchMode on).
    require_session: bool = True
    # Remote directory (relative to the SSH home) holding published bundles.
    publish_root: str = ".zflash/published"


@dataclass
class FlashConfig:
    board: str = "zcore_ra8p1_cm85"
    runner: Optional[str] = None  # override the profile's runner
    jlink_dev_id: str = ""  # serial, IP, or "tunnel:<sn>" for remote probes
    pyocd_uid: str = ""  # probe uid or "remote:<host>:<port>"
    blhost_port: str = ""  # override profile blhost_port
    probe: str = ""  # explicit probe selection for multi-probe setups
    confirm_erase: bool = False  # one-shot approval for destructive ops


@dataclass
class ConsoleConfig:
    port: str = ""
    baud: int = 115200


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    flash: FlashConfig = field(default_factory=FlashConfig)
    console: ConsoleConfig = field(default_factory=ConsoleConfig)
    # name -> remote application profile (workspace/app/build dirs etc.)
    applications: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    storage_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "zflash")


def _merge(dataclass_obj, data: Dict[str, Any]) -> None:
    """Shallow-merge a mapping into a dataclass instance, ignoring unknown keys."""
    fields = set(dataclass_obj.__dataclass_fields__)
    for key, value in (data or {}).items():
        if key in fields and value is not None:
            setattr(dataclass_obj, key, value)


def _load_yaml(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(project_dir: Optional[Path] = None) -> Config:
    """Layer config files and environment overrides into a Config object."""
    cfg = Config()

    for source in (_load_yaml(USER_CONFIG), _load_yaml(_find_project_file(project_dir))):
        _merge(cfg.server, source.get("server"))
        _merge(cfg.flash, source.get("flash"))
        _merge(cfg.console, source.get("console"))
        if source.get("storage_dir"):
            cfg.storage_dir = Path(source["storage_dir"]).expanduser()
        if source.get("applications"):
            cfg.applications.update(source["applications"])

    env = os.environ
    if env.get("ZFLASH_HOST"):
        cfg.server.host = env["ZFLASH_HOST"]
    if env.get("ZFLASH_TRANSPORT"):
        cfg.server.transport = env["ZFLASH_TRANSPORT"]
    if env.get("ZFLASH_HTTP_URL"):
        cfg.server.http_url = env["ZFLASH_HTTP_URL"]
    if env.get("ZFLASH_BOARD"):
        cfg.flash.board = env["ZFLASH_BOARD"]

    cfg.storage_dir = cfg.storage_dir.expanduser()
    return cfg


def _find_project_file(project_dir: Optional[Path]) -> Optional[Path]:
    """Walk up from project_dir (or cwd) looking for zflash.yaml."""
    start = (project_dir or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        candidate = directory / PROJECT_CONFIG
        if candidate.is_file():
            return candidate
    return None


EXAMPLE_CONFIG = """\
# zflash configuration. Copy to ~/.config/zflash/config.yaml
# or drop a zflash.yaml at the root of a project.

server:
  transport: ssh                # ssh | http
  host: build@build-server      # anything ~/.ssh/config understands
  # persist_minutes: 30          # idle lifetime of `west remote connect`
  # require_session: true        # commands reuse the connect() session
  # publish_root: .zflash/published   # remote bundle store
  artifact_roots:               # unverified workspace scan (compat mode)
    - zephyrproject/ra8p1_dual_core_app
  # http_url: http://build-server:8765

# applications:                  # profiles for `west remote build`
#   gpio_test:
#     workspace: zephyrproject  # remote west workspace root
#     source_dir: ra8p1_dual_core_app/board_bringup_tests/gpio_test
#     build_dir: build          # relative to source_dir
#     board: zcore_ra8p1_r7ka8p1kflcac_cm85
#     extra_args: []

flash:
  board: zcore_ra8p1_cm85       # `zflash boards` lists profiles
  # probe:                      # pick when several probes are attached
  # jlink_dev_id: tunnel:123456 # remote probe instead of a local one
  # pyocd_uid: remote:192.0.2.10:5555

console:
  port: /dev/ttyACM0
  baud: 115200
"""
