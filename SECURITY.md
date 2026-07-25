# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.5.x   | Yes |
| 1.4.x   | Security fixes only (upgrade recommended) |
| < 1.4   | No |

## Threat model

NetMedic is a **single-user desktop** privileged network tool. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

Primary residual risk: a **same-UID** local process can talk to the IPC socket and may trigger polkit prompts; authorization still depends on the user (or `auth_admin_keep`).

## Hardening checklist (operators)

1. Install the system helper + polkit policy:
   ```bash
   ./scripts/install-polkit-policy.sh
   netmedic --status
   ```
2. Confirm `production_ready: true` and helper path `/usr/libexec/netmedic/helper`.
3. Do **not** set `NETMEDIC_ALLOW_LEGACY_ELEVATION=1` in production.
4. Do **not** set `NETMEDIC_SKIP_POLKIT=1` outside tests (`NETMEDIC_TEST_MODE=1` only).
5. Keep state dir private (`~/.local/state/netmedic` mode `0700`).
6. MCP mutating tools: leave `NETMEDIC_MCP_ALLOW_MUTATING` unset unless intentional.

## Reporting a vulnerability

Email **support@kayabsoftware.com** (or open a private security advisory on GitHub if available).

Please include:

- NetMedic version (`netmedic --status`)
- Distro and desktop environment
- Steps to reproduce
- Impact assessment (privilege, data exposure, DoS)

We aim to acknowledge within 7 days and ship fixes for supported versions as soon as practical.

## Disclosure

We prefer coordinated disclosure. Public issues for non-sensitive bugs are fine; do not post exploit details for elevation bypasses until a fix is released.
