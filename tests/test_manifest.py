# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from zflash.manifest import (
    MANIFEST_NAME,
    BundleImage,
    BundleManifest,
    image_for,
    verify_file,
)


def test_manifest_roundtrip(tmp_path):
    f = tmp_path / "zephyr.hex"
    f.write_bytes(b"\x01\x02\x03")
    m = BundleManifest(
        build_id="gpio_test-20261113-120000-abc123",
        name="gpio_test",
        board="zcore_ra8p1_cm85",
        success=True,
        success_known=True,
        commit="a1b2c3d",
        dirty=False,
        images=[image_for(f)],
    )
    m2 = BundleManifest.from_json(m.to_json())
    assert m2.build_id == m.build_id
    assert m2.images[0].sha256 == m.images[0].sha256
    assert m2.images[0].size == 3


def test_manifest_rejects_bad_schema():
    with pytest.raises(ValueError):
        BundleManifest.from_json(json.dumps({"schema": 99}))


def test_verify_file(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello")
    img = image_for(f)
    assert verify_file(f, img)
    f.write_bytes(b"hellp")
    assert not verify_file(f, img)
    f.unlink()
    assert not verify_file(f, img)


def test_bundle_image_kwargs():
    img = BundleImage(file="x.hex", sha256="0" * 64, size=1, load_addr="0x2000")
    assert img.load_addr == "0x2000"
    assert img.runner_hint is None
