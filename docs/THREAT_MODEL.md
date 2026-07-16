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

## Mitigations (v1.4)

1. **Polkit authorization** — Each privileged IPC action maps to a polkit action ID. The IPC server validates peer UID/PID via `SO_PEERCRED` and rejects peers whose UID does not match the daemon owner.
2. **Session token** — Secondary correlation channel between GUI clients and the daemon (not sufficient alone).
3. **Strict confirmation** — `confirmed` must be boolean `True`.
4. **MCP mutating gate** — `NETMEDIC_MCP_ALLOW_MUTATING=1` required for destructive MCP tools.
5. **AI guardrail** — Whitelist-only tool execution; fail-closed when daemon unavailable.
6. **Filesystem permissions** — State dir `0o700`, socket/token/audit log `0o600`.
7. **Structured audit log** — Privileged IPC attempts (granted and denied) append JSON lines with peer UID/PID, action, outcome, and redacted params. Session tokens are never written to the audit log.
8. **Production fail-closed** — `NETMEDIC_SKIP_POLKIT` is ignored unless `NETMEDIC_TEST_MODE=1` (test/CI only).

## Residual risks

- A same-UID process with an active polkit agent session may still authorize actions if the user approves prompts.
- Headless MCP mutating operations require `pkttyagent` or fail with an explicit error.
- IPC thread pool exhaustion under concurrent long `pkexec` operations.

## Out of scope

- Multi-user systems with mutually untrusted local users
- Remote IPC exposure
- Kernel-level attack resistance