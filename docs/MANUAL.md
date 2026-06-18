# NetMedic Linux — User Manual

## Introduction

NetMedic diagnoses and repairs common Linux network issues. It provides safe automated repairs, privileged infrastructure controls, VPN server management, and an optional AI command palette.

## Launching

- **GUI:** Run `netmedic` from your application menu, or:
  ```bash
  ./venv/bin/python -m netmedic
  ```
- **AI Palette:** Press **Ctrl+Space** to open the command palette (requires AI module).

## Tab 1 — Basic Repair (Safe)

These operations are non-destructive and safe for most situations.

| Action | Description |
|--------|-------------|
| **Smart Repair** | Runs diagnostics → DNS flush → IP renewal in sequence |
| **Check Connectivity** | Pings gateway, tests DNS resolution and internet access |
| **Flush DNS** | Clears `systemd-resolved` cache |
| **Renew IP** | Renews DHCP lease on the active interface |
| **Scan Wi-Fi** | Analyzes nearby networks and recommends less congested channels |

## Tab 2 — Infrastructure (Privileged)

These require administrator authentication via `pkexec` and may cause brief disconnections.

| Action | Description |
|--------|-------------|
| **Reset TCP/IP Stack** | Restarts NetworkManager |
| **Cycle Network Adapter** | Brings default interface down and up |
| **Toggle Firewall** | Enables or disables UFW |
| **VPN Panel** | Install and manage OpenVPN server (Angristan script) |

### VPN Management

1. **Install OpenVPN** — Downloads and verifies the Angristan installer (SHA256 pinned).
2. **Add Client** — Creates a new VPN client certificate.
3. **Revoke Client** — Revokes access; verified against the PKI index.

## AI Command Palette (Optional)

With the AI module installed:

1. Press **Ctrl+Space** to open the palette.
2. Type a natural-language request (e.g., "check network status").
3. Review the AI proposal in the preview card.
4. Click **Autorizar y Ejecutar** to confirm, or **Ignorar** to dismiss.

The AI can only propose actions registered in its security whitelist.

## Security & Logs

**Log location:** `~/.local/state/netmedic/netmedic.log` (permissions: 600)

- Passwords and tokens in commands are automatically redacted.
- VPN install scripts are verified against a pinned SHA256 hash before execution.
- Virtual test interfaces (`medicXX`) are cleaned up on exit.

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| **pkexec error 126/127** | Authentication was cancelled. Retry the action. |
| **SHA256 mismatch (VPN)** | Script integrity check failed. Do not proceed; re-download. |
| **"Already running"** | Another NetMedic instance is active. Close it or remove stale lock at `~/.local/state/netmedic/netmedic.lock` if the process crashed. |
| **AI unavailable** | Install with `pip install -e "netmedic_ai[runtime]"` and place the GGUF model (see [DEVELOPMENT.md](DEVELOPMENT.md)). |

---

*NetMedic Team — 2026*