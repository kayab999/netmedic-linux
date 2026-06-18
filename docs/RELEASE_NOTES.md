# Release Notes — NetMedic v1.1.0

## Overview

NetMedic v1.1.0 is a major hardening and restructuring release following v1.0.0. It delivers a production-ready network diagnostic and repair tool with optional AI orchestration, VPN management, and hardened security controls.

## Highlights

### Network Repair
- Smart Repair sequence (diagnostics → DNS → DHCP)
- Wi-Fi congestion analysis
- DNS server configuration via NetworkManager
- Firewall and adapter management

### Security
- IPC session tokens for privileged operations
- Log redaction for sensitive command arguments
- SHA256 integrity verification for VPN installer scripts
- Singleton instance locking with crash recovery

### AI Pilot (Optional)
- Natural-language command palette (Ctrl+Space)
- GBNF-constrained LLM output
- Guardrail whitelist — only registered actions permitted
- User confirmation required before execution

### Infrastructure
- OpenVPN server install and client management (Angristan)
- Headless IPC daemon mode
- MCP server integration (`tools/netmedic_mcp.py`)

## Installation

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
./install.sh
./venv/bin/python -m netmedic
```

## Requirements

- Linux with GTK3 and NetworkManager
- Python 3.8+
- Optional: `llama-cpp-python` + GGUF model for AI features

---

*Kayab Software — 2026*