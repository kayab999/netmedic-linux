# NetMedic Threat Model (v1.9.0)

## Scope

NetMedic is a single-user desktop privileged operations platform. This document describes trust boundaries as shipped in v1.9.0: helper-only production elevation, typed fixed verbs, generated Polkit policy, bounded IPC, a fail-closed helper version gate and honest recovery results (`DBUS_DESIGN.md` covers the future v2.0 D-Bus direction). Earlier headings referred to v1.5/v1.6/v1.8; the controls below are the current 1.9.0 set.

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

## Mitigations (v1.9.0)

1. **Single elevation path** — Production root work goes through `netmedic-helper` fixed verbs via `pkexec` (annotated `exec.path` = `/usr/libexec/netmedic/helper`). Direct `CommandRunner.run(..., require_root=True)` is blocked unless `NETMEDIC_ALLOW_LEGACY_ELEVATION=1` (tests only).
2. **One interactive polkit prompt** — With the helper installed, IPC validates peer + session token + `confirmed` only; interactive polkit is deferred to helper `pkexec` (avoids double prompts).
3. **Peer UID on all actions** — `SO_PEERCRED` peer UID must match the daemon owner for every IPC request.
4. **Session token before expensive work** — Invalid/missing tokens are rejected without elevation. Token is a secondary correlation channel (not sufficient alone against same-UID malware).
5. **Strict confirmation** — `confirmed` must be boolean `True`.
6. **MCP mutating gate** — `NETMEDIC_MCP_ALLOW_MUTATING=1` required for destructive MCP tools.
7. **AI guardrail + disruptive confirm** — Whitelist tools; high blast-radius AI actions require a second GUI confirmation.
8. **Filesystem permissions** — State/data dirs `0o700` with owner check; socket/token/audit `0o600`.
9. **Structured audit log** — Privileged IPC attempts append JSON lines; session tokens redacted. The helper also emits one root-side journal record per verb (`journalctl -t netmedic-helper`) with `verb`, `ok`, a validated `pkexec_uid` and a control-character-flattened message, giving an independent root-owned record that same-UID tampering of `audit.log` cannot rewrite.
10. **Production fail-closed** — `NETMEDIC_SKIP_POLKIT` ignored unless `NETMEDIC_TEST_MODE=1`.
11. **medic* interface allowlist** — Cleanup only deletes `medic[0-9a-f]{6}` via helper verb `iface-del`.
12. **VPN script integrity (F2/F3)** — The Angristan installer is vendored in the repository and installed root-owned at `/usr/lib/netmedic/scripts/openvpn-install.sh`. The daemon sends only a typed verb + validated params; the helper resolves that to the fixed path, reads it with `O_NOFOLLOW`, rejects non-regular/foreign-owned/writable/oversized files, verifies the pinned SHA256, stages a root-owned copy under `/run/netmedic` (0700) and executes only that copy. No runtime download exists.
13. **System-owned helper** — `/usr/lib/netmedic` + `/usr/libexec/netmedic/helper` installed by policy script (no user venv/PYTHONPATH).
14. **Recoverability (Fase 6.1)** — `change-dns` snapshots both `ipv4.dns` and `ipv4.ignore-auto-dns` (fail-closed), applies the exact dry-run argv, and on failure restores the config first under a reserved rollback slice of one shared deadline (`R = min(10s, total/3)`), then attempts `con up` best-effort. The result distinguishes unchanged / reverted / not-restored and does not claim reactivation when it is unconfirmed. `restart-adapter` retries `up` once, then reports IFF_UP and carrier from sysfs (`unknown` carrier is not a failure). The daemon does not re-check operstate: it propagates the helper's `ok`, message and details verbatim (F6.2).
15. **Bounded IPC acceptance (1.9.0)** — A `BoundedSemaphore` caps active plus pending connections (`_MAX_CONNECTIONS = _MAX_WORKERS * 8`, 32 by default). At the limit the new connection is closed immediately and the accept loop keeps running; slots are released in `finally`. The listen backlog matches the same bound. Framing accepts at most exactly 64 KiB before the newline and rejects longer lines without over-reading.
16. **Fail-closed helper version gate (1.9.0)** — `CommandRunner._check_helper_version()` allows elevation only when the probe exits 0, returns a JSON object with `ok is True`, a non-empty version and an exact `HELPER_VERSION` match. Missing helper, timeout, non-zero exit, invalid JSON, `ok=false` and empty version all block privileged operations. Only the explicit `python -m` development marker keeps an in-repo fallback.
17. **Installed-contract CI (1.9.0)** — A dedicated job installs the helper and policy, restarts polkit and verifies the wrapper `--version`/`--list-verbs`, all 12 privileged `pkaction` registrations with `exec.path`/`exec.argv1`/`allow_active`, dry-runs and invalid-input rejection. Interactive authorization, destructive execution and rollback remain VM checks.

## Residual risks

- A same-UID process with user-approved polkit may still complete helper elevation if the user accepts the prompt (`auth_admin_keep` may reduce friction).
- Session token + `confirmed` are not same-UID authentication; polkit on the helper remains the real elevation gate when helper mode is on.
- Headless MCP mutating operations require `pkttyagent` or fail with an explicit error.
- IPC worker pool is fixed size; privileged execution is serialized (one at a time).
- Helper package under `/usr/lib/netmedic` must be updated when helper code changes (re-run install script).
- Onefile distribution: the PyInstaller binary extracts to a random `_MEIxxxx` dir at each start (latency cost) — accepted; rebuilding from tag in a clean container yields a functionally identical artifact, not a hash-identical one (embedded timestamps): verify via behavior + SBOM, not hash equality.
- Audit is fail-closed: if `audit.log` is unwritable (disk full), privileged actions are refused. Availability is intentionally traded for no-action-without-audit; see `docs/OPS.md`.
- The helper version gate blocks elevation when the probe cannot prove compatibility, so a broken or half-updated system install fails closed until `./scripts/install-polkit-policy.sh` is re-run.
- The IPC connection bound protects availability, not confidentiality: a same-UID peer can still occupy all 32 slots and delay new requests for up to the 30 s receive timeout.

## Deferred / out of release chain

- **AI supply chain (Fase 7, issue #62):** `netmedic_ai` stays outside the 1.9.0 release supply chain until `netmedic_ai/requirements.lock` (with hashes) lands. Its two acceptance criteria — reproducible dependencies and model-load integrity — are tracked separately. The GGUF hash is hardcoded in `netmedic_ai/pilot.py` and verified before load; the verify-then-reopen window remains a documented residual risk for the optional module.

## Out of scope

- Multi-user systems with mutually untrusted local users
- Remote IPC exposure
- Kernel-level attack resistance

