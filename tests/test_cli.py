# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from zflash.cli import _filter, _pick
from zflash.artifact import Artifact


def test_pick_rejects_out_of_range():
    arts = [Artifact(name=f"a{i}", remote_dir="d", filename="f.hex") for i in range(3)]
    # simulate user entering 0 and 99 via monkeypatched input
    import builtins

    for bad in ("0", "99", "-1", "x"):
        builtins.input = lambda *a, **k: bad
        assert _pick(arts) is None


def test_pick_valid_selection(monkeypatch):
    arts = [Artifact(name=f"a{i}", remote_dir="d", filename="f.hex") for i in range(3)]
    import builtins

    builtins.input = lambda *a, **k: "2"
    assert _pick(arts) == arts[1]


def test_filter_substring():
    arts = [
        Artifact(name="gpio_test/build/zephyr.hex", remote_dir="d", filename="z.hex"),
        Artifact(name="uart/build/zephyr.hex", remote_dir="d", filename="z.hex"),
    ]
    assert len(_filter(arts, "gpio")) == 1
    assert len(_filter(arts, None)) == 2
    assert _filter(arts, "nomatch") == []


def test_cli_help_runs():
    from zflash.cli import build_parser

    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0
