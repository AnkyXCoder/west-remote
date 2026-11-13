# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Verified build-bundle store: list, fetch, hash-check, atomically cache.

Both transports expose the same three operations; every downloaded file is
verified against the manifest's SHA-256 before it is promoted into the cache.
"""

import json
import shlex
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

from zflash.config import Config
from zflash.manifest import MANIFEST_NAME, BundleManifest, verify_file
from zflash import session


class BundleError(RuntimeError):
    pass


class _Base:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def list_bundles(self) -> List[BundleManifest]:
        raise NotImplementedError

    def read_manifest(self, build_id: str) -> BundleManifest:
        raise NotImplementedError

    def download_file(self, build_id: str, filename: str, dest: Path) -> None:
        raise NotImplementedError


class _SshBundles(_Base):
    def _root(self) -> str:
        return self.cfg.server.publish_root.strip("/") or "."

    def list_bundles(self) -> List[BundleManifest]:
        root = shlex.quote(self._root())
        remote = (
            f'for f in {root}/*/{MANIFEST_NAME}; do '
            f'echo "@@@$(basename $(dirname "$f"))"; cat "$f"; done 2>/dev/null'
        )
        out = subprocess.run(
            session.ssh_argv(self.cfg, remote),
            capture_output=True,
            text=True,
        )
        if out.returncode != 0:
            raise BundleError(
                f"cannot list bundles on '{self.cfg.server.host}': "
                f"{out.stderr.strip() or out.returncode}"
            )
        manifests = []
        current_id, buf = None, []
        for line in out.stdout.splitlines():
            if line.startswith("@@@"):
                if current_id is not None:
                    manifests.append(self._parse(current_id, "".join(buf)))
                current_id, buf = line[3:].strip(), []
            else:
                buf.append(line + "\n")
        if current_id is not None:
            manifests.append(self._parse(current_id, "".join(buf)))
        manifests.sort(key=lambda m: m.published_at, reverse=True)
        return manifests

    @staticmethod
    def _parse(build_id: str, text: str) -> BundleManifest:
        try:
            return BundleManifest.from_json(text)
        except (ValueError, KeyError, TypeError) as exc:
            raise BundleError(f"invalid manifest for build '{build_id}': {exc}")

    def read_manifest(self, build_id: str) -> BundleManifest:
        path = f"{self._root()}/{build_id}/{MANIFEST_NAME}"
        out = subprocess.run(
            session.ssh_argv(self.cfg, f"cat {shlex.quote(path)}"),
            capture_output=True,
            text=True,
        )
        if out.returncode != 0:
            raise BundleError(f"bundle '{build_id}' not found or unreadable")
        return self._parse(build_id, out.stdout)

    def download_file(self, build_id: str, filename: str, dest: Path) -> None:
        if Path(filename).name != filename:
            raise BundleError(f"unsafe filename '{filename}'")
        remote = f"cat {shlex.quote(f'{self._root()}/{build_id}/{filename}')}"
        with open(dest, "wb") as f:
            rc = subprocess.run(session.ssh_argv(self.cfg, remote), stdout=f).returncode
        if rc != 0:
            raise BundleError(f"failed to download '{filename}' (ssh rc={rc})")


class _HttpBundles(_Base):
    def _get(self, path: str, params: dict = None) -> bytes:
        url = self.cfg.server.http_url.rstrip("/") + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()

    def list_bundles(self) -> List[BundleManifest]:
        data = json.loads(self._get("/api/bundles"))
        out = []
        for m in data.get("bundles", []):
            try:
                out.append(BundleManifest.from_json(json.dumps(m)))
            except (ValueError, KeyError, TypeError):
                continue
        return out

    def read_manifest(self, build_id: str) -> BundleManifest:
        return BundleManifest.from_json(
            self._get("/api/manifest", {"build": build_id}).decode()
        )

    def download_file(self, build_id: str, filename: str, dest: Path) -> None:
        if Path(filename).name != filename:
            raise BundleError(f"unsafe filename '{filename}'")
        dest.write_bytes(
            self._get("/api/bundle", {"build": build_id, "file": filename})
        )


def _store(cfg: Config) -> _Base:
    if cfg.server.transport == "http":
        return _HttpBundles(cfg)
    return _SshBundles(cfg)


def _cache_root(cfg: Config) -> Path:
    return cfg.storage_dir / "bundles"


def list_bundles(cfg: Config) -> List[BundleManifest]:
    return _store(cfg).list_bundles()


def fetch_bundle(cfg: Config, build_id: str, *, force: bool = False) -> Path:
    """Download + verify a bundle into the cache. Returns the bundle dir."""
    store = _store(cfg)
    final = _cache_root(cfg) / build_id
    if final.is_dir() and not force:
        manifest = store.read_manifest(build_id)
        if all(verify_file(final / img.file, img) for img in manifest.images):
            return final

    manifest = store.read_manifest(build_id)
    if not manifest.images:
        raise BundleError(f"bundle '{build_id}' declares no images")

    staging = _cache_root(cfg) / f".{build_id}.staging"
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        for img in manifest.images:
            store.download_file(build_id, img.file, staging / img.file)
        for img in manifest.images:
            if not verify_file(staging / img.file, img):
                raise BundleError(
                    f"checksum mismatch for '{img.file}' in bundle '{build_id}'"
                )
        (staging / MANIFEST_NAME).write_text(manifest.to_json())
        if final.exists():
            import shutil

            shutil.rmtree(final)
        staging.rename(final)
    except Exception:
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def find_bundle(cfg: Config, selector: Optional[str]) -> BundleManifest:
    """Resolve a build_id / name prefix / 'latest' to a manifest."""
    bundles = list_bundles(cfg)
    if not bundles:
        raise BundleError("no published bundles found on the server")
    if selector is None:
        selector = "latest"
    if selector == "latest":
        return bundles[0]
    exact = [b for b in bundles if b.build_id == selector]
    if exact:
        return exact[0]
    matches = [b for b in bundles if selector.lower() in (b.name + " " + b.build_id).lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise BundleError(
            "ambiguous bundle '"
            + selector
            + "': "
            + ", ".join(b.build_id for b in matches[:8])
        )
    raise BundleError(f"no bundle matching '{selector}'")
