# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""West command classes: `west remote` (primary) and `west zflash` (legacy)."""

import argparse
import sys

try:
    from west.commands import WestCommand
except ImportError:  # west not installed; entry point is just unused
    WestCommand = object  # type: ignore


class _Forwarder(WestCommand):
    accepts_unknown_args = True
    _prog = "zflash"
    _remote = False

    def __init__(self, name, help_text, description):
        super().__init__(name, help_text, description, accepts_unknown_args=True)

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(
            self.name, help=self.help, description=self.description
        )
        parser.add_argument(
            "args", nargs=argparse.REMAINDER, help="arguments passed through"
        )
        return parser

    def do_run(self, args, unknown_args):
        from zflash.cli import main, remote_main

        argv = list(args.args or []) + list(unknown_args or [])
        rc = remote_main(argv) if self._remote else main(argv, prog=self._prog)
        sys.exit(rc)


class RemoteCommand(_Forwarder):
    _prog = "west remote"
    _remote = True

    def __init__(self):
        super().__init__(
            "remote",
            "build on a remote server and flash a local devkit",
            "west remote connect|status|disconnect|setup|builds|fetch|flash|"
            "monitor|doctor|build|publish|serve",
        )


class ZflashCommand(_Forwarder):
    def __init__(self):
        super().__init__(
            "zflash",
            "fetch binaries from a build server and flash a local devkit",
            "Compatibility alias for 'west remote'.",
        )
