# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Publish completed builds as immutable, checksummed bundles.

Layout on the server (relative to server.publish_root):

    <publish_root>/<build_id>/bundle.json
    <publish_root>/<build_id>/<artifact files...>

Publishing copies the declared files into a staging directory, writes the
manifest, then atomically renames it into place — clients never see a
half-published bundle.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from zflash.artifact import FLASHABLE_SUFFIXES
from zflash.manifest import (
    MANIFEST_NAME,
    BundleImage,
    BundleManifest,
    image_for,
)

_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def make_build_id(name: str) -> str:
    slug = _SAFE_ID.sub("-", name).strip("-.") or "build"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    short = format(int(time.time() * 1000) % 0xFFFFFF, "06x")
    return f"{slug}-{stamp}-{short}"


def _git_info(source_dir: Path) -> tuple:
    def _git(*args):
        return subprocess.run(
            ["git", "-C", str(source_dir), *args],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()

    commit = _git("rev-parse", "--short", "HEAD")
    dirty = _git("status", "--porcelain")
    return (commit or None), bool(dirty)


def collect_files(build_dir: Path) -> List[Path]:
    """Flashable files inside <build_dir>/zephyr, newest-relevant set."""
    zephyr_dir = build_dir / "zephyr"
    if not zephyr_dir.is_dir():
        raise FileNotFoundError(f"no zephyr build dir at {zephyr_dir}")
    files = [
        p
        for p in zephyr_dir.iterdir()
        if p.is_file() and p.suffix.lower() in FLASHABLE_SUFFIXES
    ]
    if not files:
        raise FileNotFoundError(f"no flashable artifacts in {zephyr_dir}")
    return sorted(files, key=lambda p: p.name)


def publish_local(
    build_dir: Path,
    publish_root: Path,
    *,
    name: str,
    board: str = "",
    runner: str = "",
    success_known: bool = True,
    load_addr: Optional[str] = None,
) -> Path:
    """Snapshot a local build dir into publish_root/<build_id>/. Returns path."""
    build_dir = Path(build_dir)
    source_dir = build_dir.parent  # app dir for git info when build_dir=<app>/build
    files = collect_files(build_dir)

    build_id = make_build_id(name)
    staging = publish_root / f".{build_id}.tmp"
    final = publish_root / build_id
    staging.mkdir(parents=True, exist_ok=False)

    try:
        images: List[BundleImage] = []
        for src in files:
            dst = staging / src.name
            shutil.copy2(src, dst)
            images.append(image_for(dst, load_addr=load_addr))

        commit, dirty = (None, None)
        if (source_dir / ".git").exists():
            commit, dirty = _git_info(source_dir)

        manifest = BundleManifest(
            build_id=build_id,
            name=name,
            app=name,
            board=board,
            success=success_known,
            success_known=success_known,
            commit=commit,
            dirty=dirty,
            images=images,
            runner=runner,
        )
        (staging / MANIFEST_NAME).write_text(manifest.to_json())
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final
