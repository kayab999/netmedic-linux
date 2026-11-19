# NetMedic Linux

Professional network diagnostics, repair, and infrastructure management for Linux. NetMedic combines a GTK3 interface with a hardened privileged IPC core, optional AI orchestration, and VPN lifecycle management.

**Version:** 1.9.0 · **License:** [MIT](LICENSE)

---

## Features

| Area | Capabilities |
|------|-------------|
| **Smart Repair** | Automated diagnostics, DNS flush, DHCP renewal |
| **Infrastructure** | Firewall toggle (UFW), TCP/IP stack reset, adapter cycling |
| **VPN Operator** | OpenVPN (Angristan) install with a vendored, root-pinned installer |
| **AI Pilot** *(optional, experimental)* | Natural-language commands via Ctrl+Space palette (Nandi model); outside the supported 1.9.0 surface |
| **Security** | Polkit IPC, action catalog, audit log, singleton locking |
| **Automation** | MCP server and headless IPC daemon for scripting and agents |

---

## Quick Start

### Option A — Pre-built binary (Releases)

```bash
sha256sum -c SHA256SUMS   # verify after download
chmod +x netmedic
./netmedic
```

Download from the [Releases](https://github.com/kayab999/netmedic-linux/releases) page.

> **Privileged actions need the system helper.** The pre-built binary does not
> bundle the helper or the polkit policy. Install them from a source checkout
> with `sudo ./scripts/install-polkit-policy.sh`; without them privileged
> actions fail with `helper-missing`. There are no `.deb`/`.rpm` packages that
> include the helper yet.

### Option B — Install from source

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
chmod +x install.sh
./install.sh
./venv/bin/netmedic
```

### Headless mode (IPC daemon, no GUI)

```bash
./venv/bin/netmedic --headless
# Or after install.sh:
systemctl --user enable --now netmedic-headless.service
```

### Health check

```bash
netmedic --status          # human-readable
netmedic --status-json     # machine-readable
```

### Polkit policy + privileged helper

System-wide policy and helper wrapper are required for least-privilege elevation:

```bash
./scripts/install-polkit-policy.sh
# installs:
#   /usr/share/polkit-1/actions/com.kayab.netmedic.policy
#   /usr/libexec/netmedic/helper  → netmedic-helper console script
pkaction --action-id com.kayab.netmedic.flush-dns
# helper is auto-used when the libexec path exists; force off with NETMEDIC_USE_HELPER=0
```

### Updating to 1.9.0

The daemon refuses a privileged helper whose `HELPER_VERSION` does not match
its own (1.9.0). After updating the application, reinstall the helper/policy
and restart the daemon:

```bash
sudo ./scripts/install-polkit-policy.sh
/usr/libexec/netmedic/helper --version   # expect {"ok":true,"version":"1.9.0"}
# GUI: close and reopen `netmedic`
```

If you use headless/MCP, the user unit is installed by `install.sh` (not by
`install-polkit-policy.sh`). If it is missing (`Unit
netmedic-headless.service not found`), create/refresh it first:

```bash
./install.sh --keep-venv --skip-tests
systemctl --user daemon-reload
systemctl --user enable --now netmedic-headless.service
# If it was already installed:
systemctl --user restart netmedic-headless.service
```

---

## Project Structure

```
netmedic-linux/
├── netmedic/          # Core application package
├── netmedic_ai/       # Optional AI pilot module
├── tests/             # Test suite (546 tests, 69 files; 2 root-only netns skips)
├── docs/              # User & developer documentation
├── scripts/           # Build & packaging scripts
├── assets/            # Icon and desktop entry template
├── tools/             # Optional integrations (MCP server)
├── install.sh         # Source installer
├── netmedic.spec      # PyInstaller specification
├── packaging/         # Debian skeleton (deb/rpm P1 backlog)
└── Dockerfile.build   # Reproducible container build
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [User Manual](docs/MANUAL.md) | Feature guide and troubleshooting |
| [Development Guide](docs/DEVELOPMENT.md) | Setup, testing, building |
| [Architecture](docs/ARCHITECTURE.md) | System design overview |
| [IPC API](docs/IPC_API.md) | Integration guide for automation clients |
| [Threat Model](docs/THREAT_MODEL.md) | Trust boundaries and residual risks |
| [Privileged Helper](docs/PRIVILEGED_HELPER.md) | Fixed-argv elevation (v1.5 design, as built v1.6.1+) |
| [Ops Runbook](docs/OPS.md) | Install, health, headless, audit, env matrix (internal IT) |
| [Contributing](CONTRIBUTING.md) | Contribution guidelines |
| [Changelog](CHANGELOG.md) | Version history |
| [Roadmap](docs/ROADMAP.md) | Future plans |

---

## Development

```bash
./install.sh                              # Full setup + test run
venv/bin/python -m pytest tests/ -v
venv/bin/ruff check netmedic/ netmedic_ai/ tools/ tests/
venv/bin/mypy --config-file mypy.ini netmedic/netmedic/ipc_security.py netmedic/netmedic/helper_verbs.py netmedic/netmedic/action_catalog.py netmedic/netmedic/models.py netmedic/netmedic/ipc_bridge.py netmedic/netmedic/ipc_actions.py netmedic/netmedic/runtime.py netmedic/netmedic/lifecycle.py netmedic/netmedic/config.py netmedic/netmedic/polkit_auth.py netmedic/netmedic/helper_main.py netmedic/netmedic/system.py netmedic/netmedic/validators.py
./scripts/build_binary.sh                 # PyInstaller build
./scripts/prepare_release_assets.sh       # Binary + SHA256SUMS + SBOM
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for details.

---

## System Requirements

- **OS:** Ubuntu 22.04/24.04 (primary; Debian/Fedora/Arch best-effort)
- **Python:** 3.10–3.13 (tested in CI; see `requirements.lock`)
- **System packages:** GTK3, GObject introspection, NetworkManager (`nmcli`), PolicyKit
- **Optional AI:** `llama-cpp-python`, ~950 MB GGUF model (not bundled in repo).
  The AI pilot is **experimental and outside the supported 1.9.0 surface**; it
  requires its own hash-pinned dependency lock and a model file plus directory
  that are admin-owned and not writable by the user (see
  `docs/AI_SUPPLY_CHAIN.md`).

---

## Security

- Root access is gated by the polkit helper (`auth_admin`/`auth_admin_keep`). The IPC same-UID peer check, `confirmed=true` and the MCP mutating gate are UX/defense-in-depth controls for the user-facing API; they are **not** an authentication boundary against same-UID processes
- Single action catalog maps GUI, MCP, and AI to the same policy surface
- Structured audit log at `~/.local/state/netmedic/audit.log` (mode 600)
- Commands requiring root use `pkexec` (no setuid)
- Sensitive arguments are redacted in application logs and audit records
- Release binaries ship with `SHA256SUMS` and Python SBOM (freeze + CycloneDX); GPG signature required on `v*` tags

---

## Support

Developed by [Kayab Software](https://buymeacoffee.com/kayabsoftware).