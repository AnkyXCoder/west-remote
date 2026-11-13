# zephyr-remote-flash — `west remote`

Build Zephyr applications on a remote server and flash a devkit attached to
your laptop. Primary interface is the **`west remote`** extension command;
`zflash` remains as a standalone/compatibility entry point.

```
laptop (devkit)                        build server
──────────────                         ─────────────
west remote build gpio_test  ──SSH──>  west build ... → publish bundle
west remote flash gpio_test  <──rsync/HTTP──  verified, checksummed bundle
  └─ JLinkExe / pyocd / blhost  ->  devkit
```

## Install

```bash
pip install zephyr-remote-flash        # laptop
pip install -e '.[uart]'               # + serial monitor support
```

On the **build server**, install it too if you want `west remote build` to
auto-publish bundles (`pip install zephyr-remote-flash`); publishing also
works manually via `west remote publish`.

## West registration

This repo is a west extension project (`west-commands.yml` at the root).
Add it to your workspace manifest:

```yaml
manifest:
  projects:
    - name: zephyr-remote-flash
      url: <repo-url>
      revision: <tag-or-commit>
      west-commands: west-commands.yml
```

Then `west remote ...` works inside the workspace. `zflash ...` works
anywhere the package is installed.

## Quick start

```bash
west remote setup        # guided: SSH alias, board, serial port
west remote connect      # authenticate once (password prompt OK)
west remote builds       # list published bundles
west remote flash gpio_test --monitor
west remote disconnect
```

No subcommand arguments? `flash`/`fetch` accept a build id, name substring,
or `latest` (default). Unverified bundles require `--force-unverified`.

## Commands

| Command | Where | Purpose |
|---|---|---|
| `setup` | laptop | interactive config wizard |
| `connect` / `disconnect` / `status` | laptop | reusable OpenSSH session |
| `builds` | laptop | list published bundles |
| `fetch <sel>` | laptop | download verified bundle to cache |
| `flash <sel> [--local f] [--monitor] [-n]` | laptop | fetch + program the devkit |
| `monitor [--port --baud]` | laptop | serial console |
| `doctor` | laptop | tools, config, session check |
| `build <app> [--flash] [--monitor]` | laptop | remote `west build` + publish |
| `publish --build-dir D --name N` | server | snapshot build dir as bundle |
| `serve <roots> [--port]` | server | bundle HTTP service (loopback default) |
| `boards`, `init`, `list`, `pull`, `console` | both | legacy/compat commands |

## SSH sessions (no repeated passwords)

`west remote connect` opens an OpenSSH `ControlMaster`; every later command
and rsync reuses it via `ControlPath`. Authenticate once — password,
passphrase, or agent all work because the real `ssh(1)` does the prompting.
The session idles out after `server.persist_minutes` (default 30).

Set `server.require_session: true` (default) so commands fail with a clear
"run connect first" instead of silently prompting. Set it `false` if your
setup uses non-interactive keys only.

## Remote builds

Configure applications in `~/.config/zflash/config.yaml` or a project
`zflash.yaml`:

```yaml
server:
  transport: ssh
  host: build@build-server
  publish_root: .zflash/published
  persist_minutes: 30

applications:
  gpio_test:
    workspace: zephyrproject              # remote west workspace root
    source_dir: ra8p1_dual_core_app/board_bringup_tests/gpio_test
    build_dir: build                      # relative to source_dir
    board: zcore_ra8p1_r7ka8p1kflcac_cm85
    extra_args: []

flash:
  board: zcore_ra8p1_cm85
  # probe: 123456          # J-Link serial / pyocd UID / blhost port override
```

Then:

```bash
west remote build gpio_test --flash --monitor
```

Build output streams to your terminal; only a **successful** build is
published and flashed — failures never flash stale output.

## Published bundles

`publish` copies `zephyr.{hex,bin,elf,...}` from a build dir into
`<publish_root>/<build_id>/` with a `bundle.json` manifest (SHA-256 per
file, board, commit, success flag). Clients download to staging, verify
hashes, and only then promote to `~/.cache/zflash/bundles/` — corrupted or
truncated transfers can never reach the flasher.

The HTTP service (`west remote serve <publish_root>`) binds **loopback by
default**; reach it from the laptop via SSH forwarding or run it only on
the VPN. It serves declared bundle files only — no arbitrary workspace
paths.

## Board profiles & runners

Built-in profiles: `zcore_ra8p1_cm85`, `zcore_ra8p1_cm33`, `ek_ra8p1_cm85`,
`rw612_blhost`, plus generic jlink/pyocd. Extend via
`~/.config/zflash/boards.d/*.yaml` or `./zflash.boards.yaml`.

Runners: **jlink** (serial/IP/tunnel auto-detected), **pyocd** (incl.
`remote:<host>:<port>` probe servers), **blhost** (structured args, erase
confirmation required).

## Platform support

Linux first: SSH multiplexing, serial monitor, and probe tooling are
validated on Linux. The pure-Python parts (bundles, publish, serve) are
portable; Windows/macOS SSH-mux behavior is not yet covered by CI.

## License

Apache-2.0
