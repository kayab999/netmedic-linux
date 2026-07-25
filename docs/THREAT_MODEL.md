# NetMedic Threat Model (v1.4)

## Scope

NetMedic is a single-user desktop privileged operations platform. This document describes trust boundaries for v1.5.0 (Phase D helper cutover).

## Actors

| Actor | Trust level |
|-------|-------------|
| GUI user | Trusted operator |
| NetMedic daemon (same user) | Trusted process |
| Same-UID local process | Untrusted |
| MCP / automation client | Untrusted unless explicitly enabled |
| Remote attacker | Out of scope (no network listener) |

## Assets

- NetworkManager configuration and connectivity
- DNS resolver settings
- UFW firewall state
- OpenVPN PKI and client certificates
- IPC session token file (`~/.local/state/netmedic/ipc.token`)
- Privileged action audit log (`~/.local/state/netmedic/audit.log`)

## Mitigations (v1.5 / Phase D)

1. **Single elevation path** — Production root work goes through `netmedic-helper` fixed verbs via `pkexec` (annotated `exec.path` = `/usr/libexec/netmedic/helper`). Direct `CommandRunner.run(..., require_root=True)` is blocked unless `NETMEDIC_ALLOW_LEGACY_ELEVATION=1` (tests only).
2. **One interactive polkit prompt** — With the helper installed, IPC validates peer + session token + `confirmed` only; interactive polkit is deferred to helper `pkexec` (avoids double prompts).
3. **Peer UID on all actions** — `SO_PEERCRED` peer UID must match the daemon owner for every IPC request.
4. **Session token before expensive work** — Invalid/missing tokens are rejected without elevation. Token is a secondary correlation channel (not sufficient alone against same-UID malware).
5. **Strict confirmation** — `confirmed` must be boolean `True`.
6. **MCP mutating gate** — `NETMEDIC_MCP_ALLOW_MUTATING=1` required for destructive MCP tools.
7. **AI guardrail + disruptive confirm** — Whitelist tools; high blast-radius AI actions require a second GUI confirmation.
8. **Filesystem permissions** — State/data dirs `0o700` with owner check; socket/token/audit `0o600`.
9. **Structured audit log** — Privileged IPC attempts append JSON lines; session tokens redacted.
10. **Production fail-closed** — `NETMEDIC_SKIP_POLKIT` ignored unless `NETMEDIC_TEST_MODE=1`.
11. **medic* interface allowlist** — Cleanup only deletes `medic[0-9a-f]{6}` via helper verb `iface-del`.
12. **VPN script integrity** — Sealed copy + SHA256 re-check inside helper before script exec.
13. **System-owned helper** — `/usr/lib/netmedic` + `/usr/libexec/netmedic/helper` installed by policy script (no user venv/PYTHONPATH).

## Residual risks

- A same-UID process with user-approved polkit may still complete helper elevation if the user accepts the prompt (`auth_admin_keep` may reduce friction).
- Session token + `confirmed` are not same-UID authentication; polkit on the helper remains the real elevation gate when helper mode is on.
- Headless MCP mutating operations require `pkttyagent` or fail with an explicit error.
- IPC worker pool is fixed size; privileged execution is serialized (one at a time).
- Helper package under `/usr/lib/netmedic` must be updated when helper code changes (re-run install script).

## Out of scope

- Multi-user systems with mutually untrusted local users
- Remote IPC exposure
- Kernel-level attack resistance