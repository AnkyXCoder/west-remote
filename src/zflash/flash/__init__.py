# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Flash runners: turn a local artifact + board profile into probe commands."""

from pathlib import Path

from zflash.boards import BoardProfile
from zflash.config import FlashConfig


def flash(profile: BoardProfile, artifact: Path, flash_cfg: FlashConfig, dry_run: bool = False):
    runner_name = flash_cfg.runner or profile.runner
    if runner_name == "jlink":
        from zflash.flash.jlink import JlinkRunner

        runner = JlinkRunner(profile, flash_cfg)
    elif runner_name == "pyocd":
        from zflash.flash.pyocd import PyocdRunner

        runner = PyocdRunner(profile, flash_cfg)
    elif runner_name == "blhost":
        from zflash.flash.blhost import BlhostRunner

        runner = BlhostRunner(profile, flash_cfg)
    else:
        raise ValueError(f"unknown runner '{runner_name}' (jlink|pyocd|blhost)")

    return runner.flash(Path(artifact), dry_run=dry_run)
