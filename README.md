# zflash — remote Zephyr artifact fetch & flash

`zflash` solves a common remote-development problem: **Zephyr builds happen on a
powerful server, but the devkit is plugged into your laptop.** It pulls build
artifacts from the server (over SSH/rsync or a small HTTP service) and flashes
the locally attached probe — J-Link, pyOCD, or NXP `blhost`.

```
laptop (devkit)                        build server
──────────────                         ─────────────
zflash flash gpio_test  ── SSH/rsync ──>  ~/zephyrproject/**/build/zephyr/zephyr.hex
  ├─ rsync artifact                    or  zflash serve ~/zephyrproject (HTTP)
  └─ JLinkExe / pyocd / blhost  ->  devkit
```

## Install

```bash
pip install zephyr-remote-flash        # from PyPI, once published
pip install -e .                       # or from this source tree
pip install -e '.[uart]'               # + serial console support
```

## Quick start

```bash
zflash init                            # writes ~/.config/zflash/config.yaml
# edit server.host and flash.board, then:
zflash doctor                          # sanity-check tools & config
zflash list                            # what can I flash?
zflash flash gpio_test                 # pick, pull, flash — done
```

No `name` argument? You get an interactive numbered menu. `--local file.hex`
flashes a file without touching the server; `-n/--dry-run` prints the probe
commands without executing.

## Two ways to reach the server

| Transport | Server side | Client config | Best for |
|-----------|-------------|---------------|----------|
| `ssh` (default) | nothing — just sshd + rsync | `server.host` | personal use, any SSH setup incl. bastions |
| `http` | `zflash serve <roots>` | `server.http_url` | teammates without SSH accounts, browsing builds |

Run the artifact service on the build server:

```bash
zflash serve ~/zephyrproject/ra8p1_dual_core_app --port 8765
# browse http://server:8765/ or: zflash --url http://server:8765 list
```

## Commands

```
zflash init [--force]          write example config
zflash boards                  list board profiles
zflash list [filter]           list remote artifacts (name, size, age)
zflash pull [name]             download artifact (+ flashable siblings)
zflash flash [name] [-l file] [-r runner] [-n]
zflash serve <roots> [--port]  artifact service (run on the build server)
zflash console [--port --baud] serial console after flashing
zflash doctor                  check ssh/rsync/JLinkExe/pyocd/blhost & config
```

Global flags: `--host`, `--url`, `-b/--board` override config per invocation.
Env vars: `ZFLASH_HOST`, `ZFLASH_TRANSPORT`, `ZFLASH_HTTP_URL`, `ZFLASH_BOARD`.

## Configuration

Config is layered: built-in defaults → `~/.config/zflash/config.yaml` →
nearest `zflash.yaml` walking up from the project directory → env vars → CLI.

```yaml
server:
  transport: ssh                 # ssh | http
  host: build@build-server       # ~/.ssh/config aliases work
  artifact_roots:                # remote dirs scanned for *.hex/*.bin/*.elf
    - zephyrproject/ra8p1_dual_core_app
  # http_url: http://build-server:8765

flash:
  board: zcore_ra8p1_cm85
  # jlink_dev_id: tunnel:123456  # remote J-Link probe (see below)
  # pyocd_uid: remote:laptop-ip:5555

console:
  port: /dev/ttyACM0
  baud: 115200
```

## Board profiles

Profiles live in `src/zflash/boards_builtin.yaml` (ships with the package) and
can be extended/overridden via `~/.config/zflash/boards.d/*.yaml` or a
project-level `zflash.boards.yaml`:

```yaml
boards:
  - name: my_board
    runner: jlink                # jlink | pyocd | blhost
    artifact: zephyr.hex
    jlink_device: R7KA8P1KF_CPU0
    bin_addr: "0x02000000"       # load addr for raw .bin
    pyocd_target: R7KA8P1KF
```

`blhost` profiles take a `blhost_port` and a `blhost_cmds` template list where
`{port}` and `{artifact}` are substituted — see the bundled `rw612_blhost`
profile for a full erase/program sequence.

## Remote probes (flash *from* the server instead)

If you'd rather keep `west flash` on the server, you don't need `zflash` at
all — both runners support remote probes:

```bash
# Laptop: JLinkRemoteServer -UseTunnel (or plain TCP on the LAN)
# Server:
west flash -r jlink --dev-id <laptop-ip>          # J-Link over LAN/VPN
west flash -r jlink --dev-id tunnel:<serial>      # SEGGER tunnel, works over WAN/NAT

# Laptop: pyocd server
# Server:
west flash -r pyocd --dev-id remote:<laptop-ip>:5555
```

`zflash` also honors `flash.jlink_dev_id` / `flash.pyocd_uid` if you want one
tool that can flash *through* a remote probe as well.

## Optional: `west zflash`

West discovers extension commands via a manifest project's `west-commands.yml`
(the file must live inside that project). To register, drop a one-line shim at
`zephyr/scripts/west_commands/zflash.py`:

```python
from zflash.west_command import ZflashCommand  # noqa: F401
```

and append to `zephyr/scripts/west-commands.yml`:

```yaml
  - file: scripts/west_commands/zflash.py
    commands:
      - name: zflash
        class: ZflashCommand
        help: fetch binaries from a build server and flash a local devkit
```

## License

Apache-2.0
