# Release Notes — NetMedic v1.3.0

## Overview

NetMedic v1.3.0 closes the enterprise governance gap identified in the v1.2.0 audit cycle. The privileged IPC core is unchanged; this release adds **demonstrability**: structured audit evidence, release artifact integrity, and synchronized documentation.

## Highlights

### Governance & Audit
- Privileged IPC actions write structured JSON lines to `~/.local/state/netmedic/audit.log`
- Each record includes timestamp, action, peer UID/PID, outcome, duration, and redacted params
- Authorization denials (polkit, token, confirmation) are audited with `outcome: denied`

### Release Integrity
- Tag-triggered GitHub release workflow builds `dist/netmedic`
- `SHA256SUMS` manifest for binary and SBOM
- `sbom-python-<version>.txt` from `pip freeze` at build time
- Optional GPG detached signature when `RELEASE_GPG_PRIVATE_KEY` and `RELEASE_GPG_KEY_ID` secrets are configured

### Security (carried from v1.2)
- Polkit-backed privileged IPC with action catalog
- `SO_PEERCRED` peer identification, session tokens, strict `confirmed=True`
- Documented threat model (`docs/THREAT_MODEL.md`)

## Verify a Release

```bash
sha256sum -c SHA256SUMS
# If signed:
gpg --verify SHA256SUMS.asc SHA256SUMS
```

## Installation

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
git checkout v1.3.0
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