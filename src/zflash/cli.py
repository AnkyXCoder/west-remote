# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""zflash CLI: list, pull, flash, serve, console, doctor."""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from zflash import __version__
from zflash.artifact import Artifact
from zflash.boards import BoardProfile, get_board, load_boards
from zflash.config import EXAMPLE_CONFIG, USER_CONFIG, load_config


def _size_str(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB"):
        if value < 1024 or unit == "MiB":
            return f"{value:.0f} {unit}"
        value /= 1024
    return f"{value:.0f} MiB"


def _pick(artifacts: List[Artifact], prompt: str = "Select artifact") -> Optional[Artifact]:
    if not artifacts:
        print("No artifacts found on the server.", file=sys.stderr)
        return None
    if len(artifacts) == 1:
        return artifacts[0]
    for i, a in enumerate(artifacts):
        print(f"  [{i + 1:2d}] {a.display_name}  ({_size_str(a.size)}, {a.age()})")
    try:
        choice = input(f"{prompt} [1-{len(artifacts)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    try:
        return artifacts[int(choice) - 1]
    except (ValueError, IndexError):
        print("invalid selection", file=sys.stderr)
        return None


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
    return cfg


def _dest_dir(cfg, artifact: Artifact) -> Path:
    return cfg.storage_dir / "artifacts" / artifact.remote_dir


def cmd_init(args):
    path = USER_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)")
        return 1
    path.write_text(EXAMPLE_CONFIG)
    print(f"wrote {path} — edit server.host and flash.board for your setup")
    return 0


def cmd_boards(args):
    profiles = load_boards()
    for p in sorted(profiles.values(), key=lambda p: p.name):
        print(f"  {p.name:<24} {p.runner:<7} {p.description}")
    print(f"\nAdd your own in ~/.config/zflash/boards.d/*.yaml or ./zflash.boards.yaml")
    return 0


def cmd_list(args):
    cfg = _load(args)
    from zflash.transfer import list_artifacts

    artifacts = _filter(list_artifacts(cfg), args.filter)
    if not artifacts:
        print("No artifacts found.", file=sys.stderr)
        return 1
    width = max(len(a.display_name) for a in artifacts)
    for a in artifacts:
        print(f"  {a.display_name:<{width}}  {_size_str(a.size):>9}  {a.age()}")
    return 0


def _resolve_artifact(cfg, name: Optional[str], artifact: Optional[str]) -> Optional[Artifact]:
    from zflash.transfer import list_artifacts

    artifacts = _filter(list_artifacts(cfg), name)
    if artifact:
        artifacts = [a for a in artifacts if a.filename == artifact] or artifacts
    return _pick(artifacts)


def cmd_pull(args):
    cfg = _load(args)
    from zflash.transfer import pull

    artifact = _resolve_artifact(cfg, args.name, args.artifact)
    if artifact is None:
        return 1
    path = pull(cfg, artifact, _dest_dir(cfg, artifact))
    print(f"pulled {path}")
    return 0


def cmd_flash(args):
    cfg = _load(args)
    profile = get_board(cfg.flash.board)
    _apply_runner_overrides(profile, cfg)

    if args.local:
        artifact_path = Path(args.local).expanduser().resolve()
        if not artifact_path.is_file():
            print(f"no such file: {artifact_path}", file=sys.stderr)
            return 1
    else:
        from zflash.transfer import pull

        artifact = _resolve_artifact(cfg, args.name, args.artifact or profile.artifact)
        if artifact is None:
            return 1
        print(f"pulling {artifact.display_name} ...")
        artifact_path = pull(cfg, artifact, _dest_dir(cfg, artifact))

    from zflash.flash import flash

    runner = cfg.flash.runner or profile.runner
    print(f"flashing {artifact_path} -> {profile.name} ({runner})")
    rc = flash(profile, artifact_path, cfg.flash, dry_run=args.dry_run)
    if rc == 0 and not args.dry_run:
        print("done.")
    return rc


def _apply_runner_overrides(profile: BoardProfile, cfg):
    f = cfg.flash
    if f.jlink_dev_id:
        pass  # consumed by the jlink runner
    if f.blhost_port:
        profile.blhost_port = f.blhost_port


def cmd_serve(args):
    from zflash.server import serve

    roots = [Path(r).expanduser() for r in args.roots]
    return serve(roots, host=args.bind, port=args.port)


def cmd_console(args):
    cfg = _load(args)
    port = args.port or cfg.console.port
    baud = args.baud or cfg.console.baud
    if not port:
        print("no serial port. Use --port or set console.port in config.", file=sys.stderr)
        return 1
    try:
        import serial
    except ImportError:
        print("pyserial not installed: pip install zephyr-remote-flash[uart]", file=sys.stderr)
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


def cmd_doctor(args):
    checks = {
        "ssh": shutil.which("ssh"),
        "rsync": shutil.which("rsync"),
        "JLinkExe": shutil.which("JLinkExe"),
        "JLinkRemoteServer": shutil.which("JLinkRemoteServer"),
        "pyocd": shutil.which("pyocd"),
        "blhost": shutil.which("blhost"),
    }
    for tool, path in checks.items():
        print(f"  {tool:<18} {'ok: ' + path if path else 'MISSING'}")
    cfg = _load(args)
    print(f"\n  transport : {cfg.server.transport}")
    print(f"  host      : {cfg.server.host or cfg.server.http_url or '(not set)'}")
    print(f"  board     : {cfg.flash.board}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zflash",
        description="Fetch Zephyr binaries from a remote build server and flash "
        "a locally attached devkit.",
    )
    p.add_argument("--version", action="version", version=f"zflash {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    def common(sp):
        sp.add_argument("--host", help="SSH host (overrides config)")
        sp.add_argument("--url", help="HTTP artifact service URL (overrides config)")
        sp.add_argument("-b", "--board", help="board profile (overrides config)")

    sp = sub.add_parser("init", help="write an example config file")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("boards", help="list board profiles")
    sp.set_defaults(func=cmd_boards)

    sp = sub.add_parser("list", help="list artifacts on the server")
    common(sp)
    sp.add_argument("filter", nargs="?", help="substring filter")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("pull", help="download an artifact")
    common(sp)
    sp.add_argument("name", nargs="?", help="artifact name substring")
    sp.add_argument("-a", "--artifact", help="required filename, e.g. zephyr.hex")
    sp.set_defaults(func=cmd_pull)

    sp = sub.add_parser("flash", help="pull (if needed) and flash the devkit")
    common(sp)
    sp.add_argument("name", nargs="?", help="artifact name substring")
    sp.add_argument("-a", "--artifact", help="required filename, e.g. zephyr.hex")
    sp.add_argument("-l", "--local", help="flash a local file, skip the server")
    sp.add_argument("-r", "--runner", choices=["jlink", "pyocd", "blhost"],
                    help="override the board's runner")
    sp.add_argument("-n", "--dry-run", action="store_true",
                    help="print probe commands without executing")
    sp.set_defaults(func=cmd_flash)

    sp = sub.add_parser("serve", help="run the artifact service (on the build server)")
    sp.add_argument("roots", nargs="+", help="directories to scan for artifacts")
    sp.add_argument("--bind", default="0.0.0.0")
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("console", help="open the board's serial console")
    sp.add_argument("--port", help="serial device")
    sp.add_argument("--baud", type=int, default=None, help="baud rate")
    sp.set_defaults(func=cmd_console)

    sp = sub.add_parser("doctor", help="check local tool availability")
    common(sp)
    sp.set_defaults(func=cmd_doctor)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
