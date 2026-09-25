# Release Notes — NetMedic v1.6.0

Enterprise-grade hardening release (B+ → A+ across the engagement).

Security: audit redaction (all sensitive keys + truncation), `openvpn-server@*.service` allowlist, TLS 1.2+ VPN downloads, root-context env guards, no-shell allowlist — all mutation-validated (94% kill rate).
Quality: 438 tests (was 222), 83% coverage (gated at 75), Hypothesis property tests, mypy strict on 10 modules.
Supply: Python 3.10–3.12 matrix, lockfiles, CycloneDX SBOM, mandatory GPG, reproducible container build.
Breaking: Python `>=3.10,<3.13` (was `>=3.8`); Smart Repair `SKIPPED/PARTIAL` semantics; IPC 1.0→1.1 (`+code`).

Requirements: Ubuntu 22.04/24.04, Python 3.10–3.12, GTK3 + NetworkManager + PolicyKit. See CHANGELOG for RC1/RC2 fixes.

---

# Release Notes — NetMedic v1.6.0-rc2

Honest-repair release: `NetResult.code` is source of truth, TCP-only `internet_ok` (ICMP no longer counts), `VERBS.md` live contract + guardian tests, `probes.py` single-source, `netns-golden` harness (A WAN-drop + B TCP-block), `--status/--status-json` health CLI. Breaking: Smart Repair `SKIPPED/PARTIAL` semantics, IPC 1.0→1.1 (`+code`). See CHANGELOG for RC1/RC2 fixes.

Requirements (v1.6): Ubuntu 22.04/24.04, Python 3.10–3.12, GTK3 + NetworkManager + PolicyKit. Python 3.8/3.9 are not supported (see breaking note above; stay on v1.5.x).

---

# Release Notes — NetMedic v1.5.0

Phase D privileged helper cutover: production root work only via `netmedic-helper` fixed verbs (`pkexec /usr/libexec/netmedic/helper <verb>`), single interactive polkit prompt, `NETMEDIC_ALLOW_LEGACY_ELEVATION` tests-only, system-owned helper at `/usr/lib/netmedic`. See CHANGELOG.

---

# Release Notes — NetMedic v1.4.1

Security hardening release on the v1.4 platform: polkit subject fix, GUI→IPC
unified elevation, medic* iface allowlist, privileged concurrency limit, and
AI/UI safety fixes. See [CHANGELOG.md](../CHANGELOG.md) for the full list.

---

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