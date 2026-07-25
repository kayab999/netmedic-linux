# NetMedic Linux

Professional network diagnostics, repair, and infrastructure management for Linux. NetMedic combines a GTK3 interface with a hardened privileged IPC core, optional AI orchestration, and VPN lifecycle management.

**Version:** 1.5.0 · **License:** [MIT](LICENSE)

---

## Features

| Area | Capabilities |
|------|-------------|
| **Smart Repair** | Automated diagnostics, DNS flush, DHCP renewal |
| **Infrastructure** | Firewall toggle (UFW), TCP/IP stack reset, adapter cycling |
| **VPN Operator** | OpenVPN (Angristan) install with SHA256 integrity verification |
| **AI Pilot** *(optional)* | Natural-language commands via Ctrl+Space palette (Nandi model) |
| **Security** | Polkit IPC, action catalog, audit log, session tokens, singleton locking |
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

---

## Project Structure

```
netmedic-linux/
├── netmedic/          # Core application package
├── netmedic_ai/       # Optional AI pilot module
├── tests/             # Test suite (160+ tests)
├── docs/              # User & developer documentation
├── scripts/           # Build & packaging scripts
├── assets/            # Icon and desktop entry template
├── tools/             # Optional integrations (MCP server)
├── install.sh         # Source installer
└── netmedic.spec      # PyInstaller specification
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
| [Privileged Helper](docs/PRIVILEGED_HELPER.md) | v1.5 design: fixed-argv elevation |
| [Contributing](CONTRIBUTING.md) | Contribution guidelines |
| [Changelog](CHANGELOG.md) | Version history |
| [Roadmap](docs/ROADMAP.md) | Future plans |

---

## Development

```bash
./install.sh                              # Full setup + test run
venv/bin/python -m pytest tests/ -v
venv/bin/ruff check netmedic/ netmedic_ai/ tests/
./scripts/build_binary.sh                 # PyInstaller build
./scripts/prepare_release_assets.sh       # Binary + SHA256SUMS + SBOM
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for details.

---

## System Requirements

- **OS:** Linux (Debian/Ubuntu, Fedora, Arch tested)
- **Python:** 3.8+
- **System packages:** GTK3, GObject introspection, NetworkManager (`nmcli`), PolicyKit
- **Optional AI:** `llama-cpp-python`, ~950 MB GGUF model (not bundled in repo)

---

## Security

- Privileged IPC actions require PolicyKit authorization, session token, and `confirmed=true`
- Single action catalog maps GUI, MCP, and AI to the same policy surface
- Structured audit log at `~/.local/state/netmedic/audit.log` (mode 600)
- Commands requiring root use `pkexec` (no setuid)
- Sensitive arguments are redacted in application logs and audit records
- Release binaries ship with `SHA256SUMS` and Python SBOM; optional GPG signature

---

## Support

Developed by [Kayab Software](https://buymeacoffee.com/kayabsoftware).