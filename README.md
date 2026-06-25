# NetMedic Linux

Professional network diagnostics, repair, and infrastructure management for Linux. NetMedic combines a GTK3 interface with a hardened execution engine, optional AI orchestration, and VPN lifecycle management.

**Version:** 1.1.0 · **License:** [MIT](LICENSE)

---

## Features

| Area | Capabilities |
|------|-------------|
| **Smart Repair** | Automated diagnostics, DNS flush, DHCP renewal |
| **Infrastructure** | Firewall toggle (UFW), TCP/IP stack reset, adapter cycling |
| **VPN Operator** | OpenVPN (Angristan) install with SHA256 integrity verification |
| **AI Pilot** *(optional)* | Natural-language commands via Ctrl+Space palette (Nandi model) |
| **Security** | Log redaction, pkexec elevation, IPC session tokens, singleton locking |

---

## Quick Start

### Option A — Pre-built binary (Releases)

```bash
chmod +x NetMedic-x86_64.AppImage
./NetMedic-x86_64.AppImage
```

Download from the [Releases](https://github.com/kayab999/netmedic-linux/releases) page.

### Option B — Install from source

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
chmod +x install.sh
./install.sh
./venv/bin/python -m netmedic
```

### Headless mode (IPC daemon, no GUI)

```bash
./venv/bin/python -m netmedic --headless
```

---

## Project Structure

```
netmedic-linux/
├── netmedic/          # Core application package
├── netmedic_ai/       # Optional AI pilot module
├── tests/             # Test suite (46 tests)
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
| [Contributing](CONTRIBUTING.md) | Contribution guidelines |
| [Changelog](CHANGELOG.md) | Version history |
| [Roadmap](docs/ROADMAP.md) | Future plans |

---

## Development

```bash
./install.sh                              # Full setup + test run
PYTHONPATH="netmedic:." venv/bin/python -m pytest tests/ -v
venv/bin/ruff check netmedic/ netmedic_ai/ tests/
./scripts/build_binary.sh                 # PyInstaller build
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for details.

---

## System Requirements

- **OS:** Linux (Debian/Ubuntu, Fedora, Arch tested)
- **Python:** 3.8+
- **System packages:** GTK3, GObject introspection, NetworkManager (`nmcli`)
- **Optional AI:** `llama-cpp-python`, ~950 MB GGUF model (not bundled in repo)

---

## Security

- Commands requiring root use `pkexec` (no setuid)
- Sensitive arguments are redacted in logs
- IPC privileged actions require per-session confirmation tokens
- Third-party scripts are SHA256-pinned before execution

---

## Support

Developed by [Kayab Software](https://buymeacoffee.com/kayabsoftware).