# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""zflash / west remote CLI.

Primary interface (as `west remote ...`):
    setup connect disconnect status builds fetch flash monitor
    doctor build publish serve boards

Compatibility aliases kept for existing scripts: init, list, pull, console.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from zflash import __version__
from zflash.artifact import Artifact
from zflash.boards import BoardProfile, get_board, load_boards
from zflash.config import EXAMPLE_CONFIG, USER_CONFIG, load_config
from zflash import session


def _size_str(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB"):
        if value < 1024 or unit == "MiB":
            return f"{value:.0f} {unit}"
        value /= 1024
    return f"{value:.0f} MiB"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)
    return answer or default


def _pick(items: List, prompt: str = "Select") -> Optional[object]:
    if not items:
        print("nothing to select from", file=sys.stderr)
        return None
    if len(items) == 1:
        return items[0]
    for i, item in enumerate(items):
        print(f"  [{i + 1:2d}] {item}")
    try:
        choice = input(f"{prompt} [1-{len(items)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    try:
        idx = int(choice) - 1
    except ValueError:
        print("invalid selection", file=sys.stderr)
        return None
    if not 0 <= idx < len(items):
        print("invalid selection", file=sys.stderr)
        return None
    return items[idx]


def _pick_artifact(artifacts: List[Artifact], prompt: str = "Select artifact"):
    if not artifacts:
        print("No artifacts found on the server.", file=sys.stderr)
        return None
    labels = [f"{a.display_name}  ({_size_str(a.size)}, {a.age()})" for a in artifacts]
    chosen = _pick(labels, prompt)
    if chosen is None:
        return None
    return artifacts[labels.index(chosen)]


def _filter(artifacts: List[Artifact], name: Optional[str]) -> List[Artifact]:
    if not name:
        return artifacts
    needle = name.lower()
    return [a for a in artifacts if needle in a.name.lower()]


def _load(args):
    cfg = load_config(getattr(args, "project_dir", None))
    if getattr(args, "host", None):
        cfg.server.host = args.host
    if getattr(args, "url", None):
        cfg.server.transport = "http"
        cfg.server.http_url = args.url
    if getattr(args, "board", None):
        cfg.flash.board = args.board
    if getattr(args, "runner", None):
        cfg.flash.runner = args.runner
    if getattr(args, "probe", None):
        cfg.flash.probe = args.probe
    return cfg


def _need_host(cfg) -> None:
    if cfg.server.transport == "http":
        if not cfg.server.http_url:
            raise ValueError("no server URL. Set server.http_url or use --url")
    elif not cfg.server.host:
        raise ValueError(
            "no server host configured. Run 'west remote setup' or set server.host"
        )


# ---------------------------------------------------------------- session


def cmd_connect(args):
    cfg = _load(args)
    _need_host(cfg)
    if cfg.server.transport != "ssh":
        print("connect is only meaningful for ssh transport")
        return 1
    ok, msg = session.connect(cfg)
    print(("connected: " if ok else "failed: ") + msg)
    return 0 if ok else 1


def cmd_disconnect(args):
    cfg = _load(args)
    ok, msg = session.disconnect(cfg)
    print(msg if ok else f"disconnect failed: {msg}")
    return 0 if ok else 1


def cmd_status(args):
    cfg = _load(args)
    _need_host(cfg)
    if cfg.server.transport == "ssh":
        print(f"server : {cfg.server.host}")
        print(f"session: {session.status(cfg)}")
    else:
        print(f"server : {cfg.server.http_url} (http, no session)")
    print(f"board  : {cfg.flash.board}")
    return 0


# ------------------------------------------------------------------ setup


def cmd_setup(args):
    cfg_path = USER_CONFIG
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    print("west remote setup — configuring your server machine\n")

    host = _ask("SSH host or alias (e.g. build@server or ~/.ssh/config alias)")
    if not host:
        print("host is required")
        return 1

    print("\ntesting ssh connection (you may be prompted once)...")
    probe = subprocess.run(["ssh", host, "true"], capture_output=False)
    if probe.returncode != 0:
        print("ssh test failed; check VPN/credentials and re-run setup")
        return 1

    boards = sorted(load_boards())
    board = _pick(boards, "Select board profile")
    if board is None:
        return 1

    ports = sorted(
        p.name
        for p in Path("/dev").glob("tty[A-Z]*")
        if "ttyS" not in p.name
    )
    console_port = _ask("Serial console port", ports[0] if ports else "")
    baud = _ask("Baud rate", "115200")

    roots = _ask("Remote dirs to scan for unverified builds", "zephyrproject")

    cfg_path.write_text(
        EXAMPLE_CONFIG.replace("build@build-server", host)
        .replace("zcore_ra8p1_cm85", board)
        .replace("/dev/ttyACM0", console_port or "/dev/ttyACM0")
        .replace("115200", baud or "115200")
        .replace("- zephyrproject/ra8p1_dual_core_app", f"- {roots}")
    )
    print(f"\nwrote {cfg_path}")
    print("next: 'west remote connect' once, then 'west remote builds'")
    return 0


# ------------------------------------------------------- bundles (new API)


def cmd_builds(args):
    cfg = _load(args)
    _need_host(cfg)
    from zflash import bundles

    try:
        items = bundles.list_bundles(cfg)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.filter:
        needle = args.filter.lower()
        items = [b for b in items if needle in (b.name + b.build_id).lower()]
    if not items:
        print("No published bundles found. Run 'west remote build' or "
              "'west remote publish' on the server first.")
        return 0
    for b in items:
        flag = "" if b.success_known and b.success else "  (unverified)"
        commit = f"  {b.commit}" if b.commit else ""
        print(f"  {b.build_id:<40} {b.name:<20} {b.board or '?':<28} "
              f"{len(b.images)} img{commit}{flag}")
    return 0


def cmd_fetch(args):
    cfg = _load(args)
    _need_host(cfg)
    from zflash import bundles

    try:
        manifest = bundles.find_bundle(cfg, args.selector)
        path = bundles.fetch_bundle(cfg, manifest.build_id)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"fetched {manifest.build_id} -> {path}")
    return 0


def _choose_image(bundle_dir: Path, profile: BoardProfile):
    """Pick the manifest image matching the board's preferred artifact."""
    import json

    manifest_file = bundle_dir / "bundle.json"
    manifest = json.loads(manifest_file.read_text())
    images = manifest.get("images", [])
    preferred = profile.artifact
    for img in images:
        if img["file"] == preferred:
            return bundle_dir / img["file"]
    # fall back: .hex over .bin over anything
    for suffix in (".hex", ".bin", ".elf", ".s19", ".img"):
        for img in images:
            if img["file"].endswith(suffix):
                return bundle_dir / img["file"]
    if images:
        return bundle_dir / images[0]["file"]
    raise FileNotFoundError("bundle declares no images")


def cmd_flash(args):
    cfg = _load(args)
    profile = get_board(cfg.flash.board)

    if args.local:
        artifact_path = Path(args.local).expanduser().resolve()
        if not artifact_path.is_file():
            print(f"no such file: {artifact_path}", file=sys.stderr)
            return 1
        manifest = None
    else:
        _need_host(cfg)
        from zflash import bundles

        try:
            manifest = bundles.find_bundle(cfg, args.selector)
            bundle_dir = bundles.fetch_bundle(cfg, manifest.build_id)
            artifact_path = _choose_image(bundle_dir, profile)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if manifest and not (manifest.success_known and manifest.success):
        if not args.force_unverified:
            print(
                f"warning: bundle '{manifest.build_id}' has no verified "
                "successful-build record. Re-run with --force-unverified to flash."
            )
            return 1

    from zflash.flash import flash

    runner = cfg.flash.runner or profile.runner
    print(f"flashing {artifact_path} -> {profile.name} ({runner})")
    rc = flash(profile, artifact_path, cfg.flash, dry_run=args.dry_run)
    if rc != 0:
        return rc
    if args.monitor and not args.dry_run:
        return cmd_monitor(args)
    if not args.dry_run:
        _record_flash(cfg, artifact_path, manifest)
        print("done.")
    return 0


def _record_flash(cfg, artifact_path: Path, manifest) -> None:
    state = cfg.storage_dir / "state"
    state.mkdir(parents=True, exist_ok=True)
    last = {
        "file": str(artifact_path),
        "build_id": getattr(manifest, "build_id", None),
        "board": cfg.flash.board,
    }
    import json

    (state / "last_flash.json").write_text(json.dumps(last, indent=2))


# ------------------------------------------------------------- remote build


def _app_profile(cfg, name: str):
    app = cfg.applications.get(name)
    if app is None:
        known = ", ".join(sorted(cfg.applications)) or "(none configured)"
        raise KeyError(
            f"unknown application '{name}'. Configured: {known}. "
            "Add it under 'applications:' in your config."
        )
    required = ("workspace", "source_dir", "build_dir", "board")
    missing = [k for k in required if not app.get(k)]
    if missing:
        raise ValueError(f"application '{name}' missing keys: {', '.join(missing)}")
    return app


def cmd_build(args):
    cfg = _load(args)
    _need_host(cfg)
    if cfg.server.transport != "ssh":
        print("remote build requires ssh transport", file=sys.stderr)
        return 1
    session.require_session(cfg)

    app = _app_profile(cfg, args.app)
    workspace = app["workspace"]
    source = app["source_dir"]
    # build_dir is relative to source_dir (e.g. "build" -> <app>/build)
    build_dir = f"{source}/{app['build_dir']}".replace("//", "/")
    board = args.remote_board or app["board"]
    extra = " ".join(app.get("extra_args", []))

    remote_cmd = (
        f"cd {shlex_quote(workspace)} && "
        f"west build -b {shlex_quote(board)} -d {shlex_quote(build_dir)} "
        f"{shlex_quote(source)} {extra}".strip()
    )
    print(f"building {args.app} on {cfg.server.host} ...")
    print(f"$ {remote_cmd}")
    rc = subprocess.call(session.ssh_argv(cfg, remote_cmd))
    if rc != 0:
        print(f"remote build failed (rc={rc}); nothing was published or flashed")
        return rc

    published = _remote_publish(cfg, app, args.name or args.app)
    if published:
        print(f"published bundle: {published}")

    if args.flash:
        flash_args = argparse.Namespace(
            local=None,
            selector=args.name or args.app,
            dry_run=False,
            monitor=args.monitor,
            force_unverified=False,
            host=args.host,
            url=args.url,
            board=cfg.flash.board,
            runner=getattr(args, "runner", None),
            probe=getattr(args, "probe", None),
            project_dir=getattr(args, "project_dir", None),
        )
        return cmd_flash(flash_args)
    if args.monitor:
        return cmd_monitor(args)
    return 0


def _remote_publish(cfg, app, name: str) -> Optional[str]:
    """Ask the server to publish the build we just produced."""
    remote_cmd = (
        f"zflash publish --build-dir {shlex_quote(app['build_dir'])} "
        f"--name {shlex_quote(name)} "
        f"--board {shlex_quote(app.get('board', ''))} "
        f"--publish-root {shlex_quote(cfg.server.publish_root)}"
    )
    probe = subprocess.run(
        session.ssh_argv(cfg, "command -v zflash"),
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        print(
            "note: 'zflash' not found on server — install it there "
            "(pip install zephyr-remote-flash) or run 'west remote publish' "
            "manually to create a bundle."
        )
        return None
    # run inside the app dir so build_dir (relative to source_dir) resolves
    remote_cmd = (
        f"cd {shlex_quote(app['workspace'] + '/' + app['source_dir'])} "
        f"&& {remote_cmd}"
    )
    proc = subprocess.run(session.ssh_argv(cfg, remote_cmd))
    return "ok" if proc.returncode == 0 else None


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(str(s))


def cmd_publish(args):
    """Runs on the server machine: snapshot a build dir into a bundle."""
    from zflash.publish import publish_local

    build_dir = Path(args.build_dir).expanduser().resolve()
    publish_root = Path(args.publish_root).expanduser()
    if not publish_root.is_absolute():
        publish_root = Path.home() / publish_root
    try:
        final = publish_local(
            build_dir,
            publish_root,
            name=args.name,
            board=args.board,
            runner=args.runner,
            success_known=not args.unverified,
        )
    except (FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"published {final}")
    return 0


# ------------------------------------------------------------- legacy (zflash)


def cmd_init(args):
    path = USER_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)")
        return 1
    path.write_text(EXAMPLE_CONFIG)
    print(f"wrote {path} — prefer 'west remote setup' for guided config")
    return 0


def cmd_boards(args):
    profiles = load_boards()
    for p in sorted(profiles.values(), key=lambda p: p.name):
        print(f"  {p.name:<24} {p.runner:<7} {p.description}")
    print(f"\nAdd your own in ~/.config/zflash/boards.d/*.yaml or ./zflash.boards.yaml")
    return 0


def cmd_list(args):
    """Legacy: list raw files in workspace build dirs (unverified)."""
    cfg = _load(args)
    _need_host(cfg)
    from zflash.transfer import list_artifacts

    try:
        artifacts = _filter(list_artifacts(cfg), args.filter)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not artifacts:
        print("No artifacts found.")
        return 0
    width = max(len(a.display_name) for a in artifacts)
    for a in artifacts:
        print(f"  {a.display_name:<{width}}  {_size_str(a.size):>9}  {a.age()}")
    print("\n(unverified workspace scan — prefer 'west remote builds' for "
          "published, checksummed bundles)")
    return 0


def _resolve_artifact(cfg, name: Optional[str], artifact: Optional[str]) -> Optional[Artifact]:
    from zflash.transfer import list_artifacts

    artifacts = _filter(list_artifacts(cfg), name)
    if artifact:
        artifacts = [a for a in artifacts if a.filename == artifact]
        if not artifacts:
            print(f"no artifact named '{artifact}'", file=sys.stderr)
            return None
    if not artifacts:
        print("No artifacts found.", file=sys.stderr)
        return None
    return _pick_artifact(artifacts)


def cmd_pull(args):
    """Legacy: download raw artifact files (unverified)."""
    cfg = _load(args)
    _need_host(cfg)
    from zflash.transfer import pull

    artifact = _resolve_artifact(cfg, args.name, args.artifact)
    if artifact is None:
        return 1
    try:
        path = pull(cfg, artifact, cfg.storage_dir / "artifacts" / artifact.remote_dir)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"pulled {path} (unverified — prefer 'west remote fetch')")
    return 0


# --------------------------------------------------------------- monitor/etc


def cmd_monitor(args):
    cfg = _load(args)
    port = getattr(args, "port", None) or cfg.console.port
    baud = getattr(args, "baud", None) or cfg.console.baud
    if not port:
        print("no serial port. Use --port or set console.port in config.",
              file=sys.stderr)
        return 1
    try:
        import serial
    except ImportError:
        print("pyserial not installed: pip install zephyr-remote-flash[uart]",
              file=sys.stderr)
        return 1

    print(f"{port} @ {baud} (Ctrl-C to exit)")
    with serial.Serial(port, baud, timeout=0.5) as ser:
        try:
            while True:
                data = ser.read(4096)
                if data:
                    sys.stdout.write(data.decode("utf-8", "replace"))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            pass
    return 0


def cmd_console(args):
    return cmd_monitor(args)


def cmd_serve(args):
    from zflash.server import serve

    roots = [Path(r).expanduser() for r in args.roots]
    return serve(roots, host=args.bind, port=args.port)


def cmd_doctor(args):
    checks = {
        "ssh": shutil.which("ssh"),
        "rsync": shutil.which("rsync"),
        "JLinkExe": shutil.which("JLinkExe") or shutil.which("JLinkExeCommander"),
        "JLinkRemoteServer": shutil.which("JLinkRemoteServer"),
        "pyocd": shutil.which("pyocd"),
        "blhost": shutil.which("blhost"),
    }
    for tool, path in checks.items():
        print(f"  {tool:<18} {'ok: ' + path if path else 'MISSING'}")

    cfg = _load(args)
    _need_host(cfg)
    print(f"\n  transport : {cfg.server.transport}")
    print(f"  server    : {cfg.server.host or cfg.server.http_url}")
    if cfg.server.transport == "ssh":
        print(f"  session   : {session.status(cfg)}")
    print(f"  board     : {cfg.flash.board}")
    print(f"  publish   : {cfg.server.publish_root}")
    print(f"  apps      : {', '.join(sorted(cfg.applications)) or '(none)'}")
    return 0


# -------------------------------------------------------------------- parser


def build_parser(prog: str = "zflash") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description="Build on a remote server machine and flash a locally attached devkit.",
    )
    p.add_argument("--version", action="version", version=f"{prog} {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    def common(sp):
        sp.add_argument("--host", help="SSH host (overrides config)")
        sp.add_argument("--url", help="HTTP bundle service URL (overrides config)")
        sp.add_argument("-b", "--board", help="board profile (overrides config)")
        sp.add_argument("--probe", help="probe serial/UID/ip override")

    # --- session ---
    sp = sub.add_parser("connect", help="open a reusable SSH session")
    common(sp)
    sp.set_defaults(func=cmd_connect)

    sp = sub.add_parser("disconnect", help="close the SSH session")
    common(sp)
    sp.set_defaults(func=cmd_disconnect)

    sp = sub.add_parser("status", help="show connection/session status")
    common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("setup", help="interactive configuration wizard")
    sp.set_defaults(func=cmd_setup)

    # --- bundles ---
    sp = sub.add_parser("builds", help="list published build bundles")
    common(sp)
    sp.add_argument("filter", nargs="?", help="substring filter")
    sp.set_defaults(func=cmd_builds)

    sp = sub.add_parser("fetch", help="download a verified build bundle")
    common(sp)
    sp.add_argument("selector", nargs="?", default="latest",
                    help="build id, name substring, or 'latest'")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("flash", help="fetch a bundle (or --local) and flash")
    common(sp)
    sp.add_argument("selector", nargs="?", default=None,
                    help="build id/name; default 'latest'")
    sp.add_argument("-l", "--local", help="flash a local file, skip the server")
    sp.add_argument("-r", "--runner", choices=["jlink", "pyocd", "blhost"],
                    help="override the board's runner")
    sp.add_argument("-n", "--dry-run", action="store_true",
                    help="print probe commands without executing")
    sp.add_argument("--monitor", action="store_true",
                    help="open serial console after flashing")
    sp.add_argument("--force-unverified", action="store_true",
                    help="flash a bundle without a verified success record")
    sp.set_defaults(func=cmd_flash)

    # --- remote build / server ---
    sp = sub.add_parser("build", help="run a configured remote west build")
    common(sp)
    sp.add_argument("app", help="application profile name")
    sp.add_argument("-n", "--name", help="bundle name (default: app name)")
    sp.add_argument("--remote-board", dest="remote_board",
                    help="override remote build board")
    sp.add_argument("--flash", action="store_true",
                    help="flash the published bundle afterwards")
    sp.add_argument("--monitor", action="store_true",
                    help="open serial console afterwards")
    sp.add_argument("-r", "--runner", choices=["jlink", "pyocd", "blhost"])
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("publish", help="snapshot a build dir as a bundle "
                                       "(run on the server machine)")
    sp.add_argument("--build-dir", required=True)
    sp.add_argument("--publish-root", default=".zflash/published")
    sp.add_argument("--name", required=True)
    sp.add_argument("--board", default="")
    sp.add_argument("--runner", default="")
    sp.add_argument("--unverified", action="store_true",
                    help="mark success as unknown")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("serve", help="run the bundle service (server machine)")
    sp.add_argument("roots", nargs="+", help="publish roots to serve")
    sp.add_argument("--bind", default="127.0.0.1",
                    help="bind address (default loopback; use SSH forwarding)")
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(func=cmd_serve)

    # --- misc ---
    sp = sub.add_parser("monitor", help="open the board's serial console")
    sp.add_argument("--port")
    sp.add_argument("--baud", type=int, default=None)
    sp.set_defaults(func=cmd_monitor)

    sp = sub.add_parser("doctor", help="check tools, config, and session")
    common(sp)
    sp.set_defaults(func=cmd_doctor)

    # --- legacy aliases ---
    sp = sub.add_parser("init", help="write an example config file (legacy)")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("boards", help="list board profiles")
    sp.set_defaults(func=cmd_boards)

    sp = sub.add_parser("list", help="legacy: scan raw build files (unverified)")
    common(sp)
    sp.add_argument("filter", nargs="?")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("pull", help="legacy: download raw files (unverified)")
    common(sp)
    sp.add_argument("name", nargs="?")
    sp.add_argument("-a", "--artifact")
    sp.set_defaults(func=cmd_pull)

    sp = sub.add_parser("console", help="alias for 'monitor'")
    sp.add_argument("--port")
    sp.add_argument("--baud", type=int, default=None)
    sp.set_defaults(func=cmd_console)

    return p


def main(argv: Optional[List[str]] = None, prog: str = "zflash") -> int:
    args = build_parser(prog).parse_args(argv)
    if not getattr(args, "func", None):
        build_parser(prog).print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except (ValueError, KeyError, FileNotFoundError, RuntimeError,
            session.SessionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def remote_main(argv: Optional[List[str]] = None) -> int:
    """Entry point used by `west remote ...`."""
    return main(argv, prog="west remote")


if __name__ == "__main__":
    raise SystemExit(main())
