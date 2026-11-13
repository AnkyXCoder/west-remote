# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Versioned build-bundle manifests: metadata + per-file SHA-256 digests."""

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_NAME = "bundle.json"
SCHEMA_VERSION = 1


@dataclass
class BundleImage:
    file: str  # filename inside the bundle directory
    sha256: str
    size: int
    # Optional deployment hints; absent values stay unknown.
    load_addr: Optional[str] = None
    runner_hint: Optional[str] = None


@dataclass
class BundleManifest:
    build_id: str
    name: str  # short application/build label
    schema: int = SCHEMA_VERSION
    app: str = ""
    board: str = ""
    core: str = ""
    success: bool = False
    success_known: bool = False
    commit: Optional[str] = None
    dirty: Optional[bool] = None
    published_at: float = field(default_factory=time.time)
    runner: str = ""
    images: List[BundleImage] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "BundleManifest":
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unsupported bundle schema in {MANIFEST_NAME}")
        images = [BundleImage(**img) for img in data.get("images", [])]
        allowed = set(cls.__dataclass_fields__) - {"images"}
        kwargs = {k: v for k, v in data.items() if k in allowed}
        kwargs["images"] = images
        return cls(**kwargs)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def image_for(path: Path, **kwargs: Any) -> BundleImage:
    return BundleImage(
        file=path.name,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        **kwargs,
    )


def verify_file(path: Path, image: BundleImage) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == image.size
        and sha256_file(path) == image.sha256
    )
