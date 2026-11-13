# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Optional west extension: `west zflash` forwards to the zflash CLI."""

import argparse
import sys

try:
    from west.commands import WestCommand
except ImportError:  # west not installed; entry point is just unused
    WestCommand = object  # type: ignore


class ZflashCommand(WestCommand):
    def __init__(self):
        super().__init__(
            "zflash",
            "fetch binaries from a build server and flash a local devkit",
            "Pull Zephyr artifacts over SSH/HTTP and flash via J-Link/pyOCD/blhost.",
            accepts_unknown_args=True,
        )

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(
            self.name, help=self.help, description=self.description
        )
        parser.add_argument(
            "args", nargs=argparse.REMAINDER, help="arguments passed to zflash"
        )
        return parser

    def do_run(self, args, unknown_args):
        from zflash.cli import main

        rc = main(list(args.args or []) + list(unknown_args or []))
        sys.exit(rc)
