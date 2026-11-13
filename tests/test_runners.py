# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

from zflash.boards import BoardProfile
from zflash.config import FlashConfig
from zflash.flash.jlink import JlinkRunner, _detect_dev_id_type
from zflash.flash.pyocd import PyocdRunner


def _profile(**kw):
    return BoardProfile(
        name="test", runner="jlink", jlink_device="R7KA8P1KF_CPU0", **kw
    )


def test_jlink_dev_id_detection():
    assert _detect_dev_id_type("123456") == "serialno"
    assert _detect_dev_id_type("192.168.1.5") == "ip"
    assert _detect_dev_id_type("tunnel:mytunnel") == "tunnel"
    assert _detect_dev_id_type("/dev/ttyACM0") in ("tty", "unknown")


def test_jlink_probe_args_serial():
    r = JlinkRunner(_profile(), FlashConfig(jlink_dev_id="123456"))
    assert r._probe_args() == ["-USB", "123456"]


def test_jlink_probe_args_ip_and_tunnel():
    r = JlinkRunner(_profile(), FlashConfig(jlink_dev_id="10.0.0.5"))
    assert r._probe_args() == ["-IP", "10.0.0.5"]
    r = JlinkRunner(_profile(), FlashConfig(jlink_dev_id="tunnel:abc"))
    assert r._probe_args() == ["-IP", "tunnel:abc"]


def test_jlink_dry_run(capsys, tmp_path):
    art = tmp_path / "zephyr.hex"
    art.write_text("x")
    rc = JlinkRunner(_profile(), FlashConfig()).flash(art, dry_run=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "-device R7KA8P1KF_CPU0" in out
    assert "loadfile" in out


def test_jlink_bin_uses_addr(capsys, tmp_path):
    art = tmp_path / "zephyr.bin"
    art.write_bytes(b"x")
    r = JlinkRunner(_profile(bin_addr="0x02000000"), FlashConfig())
    r.flash(art, dry_run=True)
    assert "0x02000000" in capsys.readouterr().out


def test_pyocd_dry_run(capsys, tmp_path):
    art = tmp_path / "zephyr.hex"
    art.write_text("x")
    p = BoardProfile(name="p", runner="pyocd", pyocd_target="R7KA8P1KF")
    rc = PyocdRunner(p, FlashConfig(pyocd_uid="remote:10.0.0.1:5555")).flash(
        art, dry_run=True
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "pyocd" in out and "-t R7KA8P1KF" in out
    assert "remote:10.0.0.1:5555" in out
    assert "reset" in out
    # must NOT request full chip erase
    assert "-e chip" not in out and "--erase chip" not in out


def test_blhost_structured_args(capsys, tmp_path, monkeypatch):
    from zflash.flash.blhost import BlhostRunner

    art = tmp_path / "zephyr.bin"
    art.write_bytes(b"x")
    p = BoardProfile(
        name="rw",
        runner="blhost",
        blhost_port="/dev/ttyUSB0",
        blhost_cmds=["write-memory 0x08000000 {artifact}"],
    )
    rc = BlhostRunner(p, FlashConfig(confirm_erase=True)).flash(art, dry_run=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "blhost -p /dev/ttyUSB0 write-memory 0x08000000" in out
