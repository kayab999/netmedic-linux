# NetMedic Threat Model (v1.4)

## Scope

NetMedic is a single-user desktop privileged operations platform. This document describes trust boundaries for v1.4.0.

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

## Mitigations (v1.4 / hardening sweep)

1. **Polkit authorization** — Each privileged IPC action maps to a polkit action ID. Subject construction uses `UnixProcess.new_for_owner(pid, start_time, uid)` and `pkcheck --process pid,start_time,uid` when GI is unavailable.
2. **Peer UID on all actions** — `SO_PEERCRED` peer UID must match the daemon owner for every IPC request (not only privileged).
3. **Session token before polkit** — Invalid/missing tokens are rejected without triggering interactive polkit prompts. Token is a secondary correlation channel (not sufficient alone against same-UID malware).
4. **Strict confirmation** — `confirmed` must be boolean `True`.
5. **MCP mutating gate** — `NETMEDIC_MCP_ALLOW_MUTATING=1` required for destructive MCP tools (including `vpn_list_clients`).
6. **AI guardrail + disruptive confirm** — Whitelist tools; high blast-radius AI actions require a second GUI confirmation.
7. **Filesystem permissions** — State/data dirs `0o700` with owner check; socket/token/audit created with restrictive umask/`O_CREAT` mode `0o600`.
8. **Structured audit log** — Privileged IPC attempts (granted and denied) append JSON lines with peer UID/PID, action, outcome, and redacted params. Session tokens are never written to the audit log.
9. **Production fail-closed** — `NETMEDIC_SKIP_POLKIT` is ignored unless `NETMEDIC_TEST_MODE=1` (test/CI only).
10. **medic* interface allowlist** — Orphan/state cleanup only deletes `medic[0-9a-f]{6}` names.
11. **VPN script staging** — Installer is re-hashed via FD, copied exclusively under `XDG_RUNTIME_DIR`, re-hashed, then elevated; source script mode `0500` after download.
12. **CommandRunner root allowlist** — Elevated argv must use an allowlisted binary basename.

## Residual risks

- A same-UID process with an active polkit agent session may still authorize actions if the user approves prompts (`auth_admin_keep`) or if generic `pkexec` auth is cached.
- GUI catalog actions (repair, stack, DNS, firewall, full VPN surface) go through IPC and are audit-logged. Residual direct elevation: local virtual-iface cleanup on exit.
- After IPC authorization, `CommandRunner` still uses generic `pkexec` for the actual root command (fine-grained polkit action IDs gate the IPC action, not the argv).
- Headless MCP mutating operations require `pkttyagent` or fail with an explicit error.
- IPC thread pool exhaustion under concurrent long `pkexec` operations.
- VPN script staging narrows TOCTOU but cannot fully eliminate same-UID races without a root-owned helper.
- Session token + `confirmed` are not same-UID authentication; polkit/pkexec remain the real elevation gates.

## Out of scope

- Multi-user systems with mutually untrusted local users
- Remote IPC exposure
- Kernel-level attack resistance