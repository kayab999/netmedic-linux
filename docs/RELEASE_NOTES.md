# Release Notes — NetMedic v1.4.0

## Overview

NetMedic v1.4.0 positions the IPC core as an integration platform. The GUI remains one client; automation, MCP, and third-party tools integrate via a documented, versioned API with hardened peer identity checks.

## Highlights

### Platform API
- `docs/IPC_API.md` — integration guide for external clients
- `ipc_schema.export_schema()` — machine-readable action contract (API v1.0)
- `SyncIPCClient` — reference Python client for scripts and agents

### Security Hardening
- Peer UID must match the daemon owner for privileged actions and `get_session_token`
- `NETMEDIC_SKIP_POLKIT` ignored in production (requires `NETMEDIC_TEST_MODE=1`)
- Polkit GI path uses `UnixProcess.new_for_owner` when available

### Operations
- systemd user unit: `netmedic-headless.service` (installed by `install.sh`)
- Structured audit log (`audit.log`) from v1.3
- Release integrity pipeline (SHA256SUMS, SBOM) from v1.3

## Headless daemon

```bash
systemctl --user enable --now netmedic-headless.service
```

## Installation

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
git checkout v1.4.0
./install.sh
./venv/bin/netmedic
```

## Requirements

- Linux with GTK3 and NetworkManager
- Python 3.8+
- PolicyKit for privileged IPC actions
- Optional: `llama-cpp-python` + GGUF model for AI features

---

*Kayab Software — 2026*