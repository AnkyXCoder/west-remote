# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""`zflash serve`: published-bundle service for the server machine.

Each served root is a publish root containing <build_id>/bundle.json + files.
Endpoints:
  GET /                  -> HTML index of published builds
  GET /api/bundles       -> JSON list of bundle manifests
  GET /api/manifest?build=<id>            -> bundle.json
  GET /api/bundle?build=<id>&file=<name>  -> artifact bytes
"""

import html
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from zflash.manifest import MANIFEST_NAME, BundleManifest

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_INDEX = """<!doctype html><meta charset=utf-8><title>zflash builds</title>
<style>body{font-family:system-ui,sans-serif;max-width:70em;margin:2em auto}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;
padding:.4em .6em;text-align:left}th{position:sticky;top:0;background:#fff}
td.time{color:#666;white-space:nowrap}</style>
<h1>zflash published builds</h1><table>
<tr><th>Build</th><th>Name</th><th>Board</th><th>Images</th><th>Published</th></tr>
{rows}</table><p>{count} builds. Use <code>west remote builds</code> /
<code>west remote flash</code> on your local machine.</p>
"""


def _iter_bundle_dirs(roots: List[Path]):
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / MANIFEST_NAME).is_file():
                yield child


def _load_manifest(path: Path) -> Optional[BundleManifest]:
    try:
        return BundleManifest.from_json((path / MANIFEST_NAME).read_text())
    except (ValueError, OSError):
        return None


def _all_bundles(roots: List[Path]) -> List[Dict]:
    out = []
    for bdir in _iter_bundle_dirs(roots):
        manifest = _load_manifest(bdir)
        if manifest is None:
            continue
        out.append({"dir": bdir, "manifest": manifest})
    out.sort(key=lambda e: e["manifest"].published_at, reverse=True)
    return out


class _Handler(BaseHTTPRequestHandler):
    roots: List[Path] = []

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve(self, build_id: str) -> Optional[Path]:
        if not _SAFE_ID.match(build_id or "") or ".." in build_id:
            return None
        for root in self.roots:
            candidate = root / build_id
            if candidate.is_dir() and candidate.resolve().is_relative_to(root.resolve()):
                return candidate
        return None

    def do_GET(self):  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/bundles":
            bundles = [
                json.loads(e["manifest"].to_json())
                for e in _all_bundles(self.roots)
            ]
            return self._json({"bundles": bundles})

        if parsed.path == "/api/manifest":
            bdir = self._resolve(qs.get("build", [""])[0])
            if bdir is None:
                return self._json({"error": "not found"}, 404)
            return self._json(json.loads(_load_manifest(bdir).to_json()))

        if parsed.path == "/api/bundle":
            return self._download(
                qs.get("build", [""])[0], qs.get("file", [""])[0]
            )

        if parsed.path in ("/", "/index.html"):
            return self._index()

        self._json({"error": "not found"}, 404)

    def _download(self, build_id: str, filename: str):
        if Path(filename).name != filename or filename == MANIFEST_NAME:
            return self._json({"error": "bad filename"}, 400)
        bdir = self._resolve(build_id)
        if bdir is None:
            return self._json({"error": "not found"}, 404)
        manifest = _load_manifest(bdir)
        allowed = {img.file for img in manifest.images} if manifest else set()
        if filename not in allowed:
            return self._json({"error": "not declared in manifest"}, 403)
        path = bdir / filename
        if not path.is_file():
            return self._json({"error": "not found"}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _index(self):
        rows = ""
        for e in _all_bundles(self.roots):
            m = e["manifest"]
            imgs = ", ".join(i.file for i in m.images)
            rows += (
                "<tr><td>{bid}</td><td>{name}</td><td>{board}</td>"
                "<td>{imgs}</td><td class=time>{pub}</td></tr>".format(
                    bid=html.escape(m.build_id),
                    name=html.escape(m.name),
                    board=html.escape(m.board or "?"),
                    imgs=html.escape(imgs),
                    pub=time.strftime("%Y-%m-%d %H:%M", time.localtime(m.published_at)),
                )
            )
        count = rows.count("<tr>") - 1 if rows else 0
        body = _INDEX.format(rows=rows, count=count).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(roots: List[Path], host: str = "127.0.0.1", port: int = 8765):
    """Run the bundle service. Blocking. Binds loopback by default."""
    resolved = [Path(r).expanduser().resolve() for r in roots]
    for r in resolved:
        if not r.is_dir():
            print(f"warning: {r} is not a directory")
    handler = type("Handler", (_Handler,), {"roots": resolved})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"zflash bundle service on http://{host}:{port} (loopback only unless --bind 0.0.0.0)")
    print("serving:", ", ".join(str(r) for r in resolved))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
