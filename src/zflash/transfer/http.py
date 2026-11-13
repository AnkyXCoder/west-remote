# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""HTTP backend: talks to `zflash serve` running on the server machine."""

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List

from zflash.artifact import Artifact
from zflash.config import Config


class HttpBackend:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if not cfg.server.http_url:
            raise ValueError(
                "no server URL configured. Set server.http_url in "
                "~/.config/zflash/config.yaml or $ZFLASH_HTTP_URL"
            )
        self.base = cfg.server.http_url.rstrip("/")

    def _get(self, path: str, params: dict = None) -> bytes:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()

    def list_artifacts(self) -> List[Artifact]:
        data = json.loads(self._get("/api/artifacts"))
        return [
            Artifact(
                name=a["name"],
                remote_dir=a["remote_dir"],
                filename=a["filename"],
                size=a.get("size", 0),
                mtime=a.get("mtime", 0),
                siblings=a.get("siblings", []),
            )
            for a in data.get("artifacts", [])
        ]

    def pull(self, artifact: Artifact, dest_dir: Path) -> Path:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        files = [artifact.filename] + [s for s in artifact.siblings if s != artifact.filename]
        for filename in files:
            data = self._get(
                "/api/download",
                {"dir": artifact.remote_dir, "file": filename},
            )
            (dest_dir / filename).write_bytes(data)
        return dest_dir / artifact.filename
