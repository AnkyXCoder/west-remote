# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""West command entry point for the zephyr-remote-flash project.

Registered through this repository's west-commands.yml when the project is
a manifest project; west imports the named classes from zflash.west_command.
"""

from zflash.west_command import RemoteCommand, ZflashCommand  # noqa: F401
