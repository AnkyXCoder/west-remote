# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from zflash import bundles
from zflash.config import Config, ServerConfig
from zflash.manifest import MANIFEST_NAME, BundleManifest, image_for
from zflash.publish import publish_local
from zflash.server import _Handler


def _make_build_tree(tmp_path):
    """Create <app>/build/zephyr with a flashable file."""
    zdir = tmp_path / "app" / "build" / "zephyr"
    zdir.mkdir(parents=True)
    (zdir / "zephyr.hex").write_bytes(b":020000040000FA\n")
    (zdir / "zephyr.bin").write_bytes(b"\x00" * 16)
    return tmp_path / "app" / "build"


def test_publish_creates_verified_bundle(tmp_path):
    build_dir = _make_build_tree(tmp_path)
    pub = tmp_path / "published"
    final = publish_local(build_dir, pub, name="gpio_test", board="b1")
    assert final.is_dir()
    manifest = BundleManifest.from_json((final / MANIFEST_NAME).read_text())
    assert manifest.name == "gpio_test"
    assert {i.file for i in manifest.images} == {"zephyr.hex", "zephyr.bin"}
    # idempotent-ish: second publish gets a different id
    final2 = publish_local(build_dir, pub, name="gpio_test")
    assert final2 != final


def test_fetch_bundle_http_roundtrip(tmp_path, monkeypatch):
    build_dir = _make_build_tree(tmp_path)
    pub = tmp_path / "published"
    publish_local(build_dir, pub, name="gpio_test", board="b1")

    # serve it
    handler = type("H", (_Handler,), {"roots": [pub.resolve()]})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        cfg = Config(
            server=ServerConfig(transport="http", http_url=f"http://127.0.0.1:{port}")
        )
        cfg.storage_dir = tmp_path / "cache"
        found = bundles.find_bundle(cfg, "gpio")
        dest = bundles.fetch_bundle(cfg, found.build_id)
        assert (dest / "zephyr.hex").is_file()
        assert (dest / "zephyr.bin").is_file()
        assert (dest / MANIFEST_NAME).is_file()
        # second fetch uses cache
        assert bundles.fetch_bundle(cfg, found.build_id) == dest
    finally:
        server.shutdown()


def test_fetch_detects_corruption(tmp_path, monkeypatch):
    build_dir = _make_build_tree(tmp_path)
    pub = tmp_path / "published"
    final = publish_local(build_dir, pub, name="gpio_test")

    # corrupt a published file, then fetch via a fake store that serves it
    (final / "zephyr.hex").write_bytes(b"corrupted")

    class FakeStore:
        def __init__(self, cfg):
            pass

        def read_manifest(self, bid):
            return BundleManifest.from_json(
                (final / MANIFEST_NAME).read_text()
            )

        def download_file(self, bid, filename, dest):
            dest.write_bytes((final / filename).read_bytes())

    monkey_cfg = Config()
    monkey_cfg.storage_dir = tmp_path / "cache"
    monkeypatch.setattr(bundles, "_store", lambda cfg: FakeStore(cfg))
    with pytest.raises(bundles.BundleError, match="checksum"):
        bundles.fetch_bundle(monkey_cfg, final.name)


def test_server_rejects_undeclared_and_traversal(tmp_path):
    build_dir = _make_build_tree(tmp_path)
    pub = tmp_path / "published"
    final = publish_local(build_dir, pub, name="gpio_test")
    bid = final.name

    handler = type("H", (_Handler,), {"roots": [pub.resolve()]})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        # undeclared file
        (final / "secret.txt").write_text("nope")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(
                f"{base}/api/bundle?build={bid}&file=secret.txt"
            )
        assert e.value.code == 403
        # traversal in build id
        with pytest.raises(urllib.error.HTTPError) as e2:
            urllib.request.urlopen(
                f"{base}/api/bundle?build=..&file=x"
            )
        assert e2.value.code in (400, 404)
        # declared file downloads fine
        data = urllib.request.urlopen(
            f"{base}/api/bundle?build={bid}&file=zephyr.hex"
        ).read()
        assert data
    finally:
        server.shutdown()
