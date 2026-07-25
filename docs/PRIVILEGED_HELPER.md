# Privileged Helper Design (v1.5 target)

## Problem

Today NetMedic elevates with:

```text
IPC polkit (com.kayab.netmedic.*)  →  pkexec <arbitrary allowlisted argv>
```

The fine-grained polkit action IDs gate **IPC entry**, not the **actual root command**. `CommandRunner` prefixes any allowlisted binary with generic `org.freedesktop.policykit.exec` (`pkexec`). That is defense-in-depth for accidental misuse, but not least privilege:

| Property | Current | Desired |
|----------|---------|---------|
| Polkit subject | IPC action ID | Helper verb / fixed program |
| Root argv | Client-chosen within binary allowlist | Fixed map action → argv template |
| Audit | IPC audit log | IPC + helper audit (optional) |
| Attack surface | Any code path that reaches `CommandRunner.run(..., require_root=True)` | Only helper entrypoints |

## Goals

1. **One setuid-free helper** invoked only via `pkexec` / polkit with annotated path.
2. **Action → argv templates** owned by the helper (not the GUI/IPC worker).
3. **Re-hash / re-open** of operator scripts under elevation for VPN install.
4. **No shell**; argv-only execution.
5. **Backward-compatible IPC API** (action names unchanged).

## Non-goals (v1.5)

- Multi-user mutually untrusted operators
- Network-exposed helper
- Replacing NetworkManager with a custom daemon

## Architecture

```
┌─────────────┐     Unix IPC      ┌──────────────────┐
│ GUI / MCP / │ ────────────────► │ netmedic daemon  │
│ AI client   │   token+polkit    │ (user process)   │
└─────────────┘                   └────────┬─────────┘
                                           │
                                           │ spawn (no root yet)
                                           ▼
                                  ┌──────────────────┐
                                  │ netmedic-helper  │
                                  │ (pkexec / polkit │
                                  │  annotated path) │
                                  └────────┬─────────┘
                                           │ root
                                           ▼
                                  fixed argv templates
                                  (nmcli, resolvectl, ip, …)
```

### Components

| Piece | Role |
|-------|------|
| `netmedic-helper` | Small CLI installed to `/usr/libexec/netmedic/helper` (or `/usr/bin/netmedic-helper`) |
| Polkit policy | `annotate` each action with `org.freedesktop.policykit.exec.path` = helper path; optional `argv1` = verb |
| `CommandRunner` | For production: `pkexec /usr/libexec/netmedic/helper <verb> [args…]` instead of raw tool |
| Verb registry | Shared constants with `action_catalog` (or generated from it) |

### Helper CLI contract

```bash
netmedic-helper <verb> [json-args-or-flags]
```

Examples:

| Verb | Maps from IPC | Root work |
|------|---------------|-----------|
| `flush-dns` | `flush_dns` | `resolvectl flush-caches` |
| `renew-ip` | `renew_ip` | `nmcli device reapply <iface>` or dhclient |
| `change-dns` | `change_dns` | `nmcli con mod …` + `con up` |
| `restart-adapter` | `restart_adapter` | `ip link set <iface> down/up` |
| `reset-stack` | `reset_tcp_ip_stack` | `systemctl restart NetworkManager` |
| `toggle-firewall` | `toggle_firewall` | `ufw --force enable` / `disable` |
| `vpn-list` | `vpn_list_clients` | read EasyRSA index only |
| `vpn-run-script` | install/add/revoke | re-hash sealed script then exec |
| `iface-del` | cleanup | only `medic[0-9a-f]{6}` |

Output: single JSON line on stdout:

```json
{"ok": true, "message": "...", "details": null}
```

Exit codes: `0` success, `1` operational failure, `2` invalid args, `3` integrity/auth local check failed, `126` cancelled.

### Argument validation (helper-side)

- Interface names: `^[A-Za-z0-9._@+-]+$` (and medic allowlist for delete).
- DNS: IPv4 regex (same as `network.py`).
- VPN client names: `^[a-zA-Z0-9_-]+$`.
- Connection names: length cap + charset; prefer NM UUID when available later.

### Polkit policy sketch

```xml
<action id="com.kayab.netmedic.flush-dns">
  ...
  <annotate key="org.freedesktop.policykit.exec.path">/usr/libexec/netmedic/helper</annotate>
  <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
</action>
```

Invocation:

```bash
pkexec --disable-internal-agent /usr/libexec/netmedic/helper flush-dns
```

(Exact pkexec/polkit annotation semantics vary by distro; validate on Debian/Fedora/Arch in CI.)

## Migration plan

### Phase A — Design freeze (this doc)

- Verb list locked to current IPC privileged set.
- JSON I/O schema frozen.

### Phase B — Helper prototype (in-tree) ✅

1. ✅ `netmedic/helper_main.py` + `helper_verbs.py` — CLI with `--dry-run` / `--execute`
2. ✅ Unit tests (`tests/test_helper_verbs.py`) — validation + dispatch **without** root
3. ✅ `CommandRunner.run_elevated(verb, args)` feature-flagged:

   ```python
   if Config.use_privileged_helper():  # NETMEDIC_USE_HELPER=1
       return run helper via pkexec
   else:
       legacy pkexec + planned argv  # current path
   ```

   Entry point: `netmedic-helper` (setuptools console script).

### Phase C — Packaging

1. install.sh / deb/rpm install helper to libexec + system polkit policy with annotations.
2. AppImage note: helper still needs host install for elevation (AppImage cannot ship setuid).

### Phase D — Cutover

1. Default helper on for new installs.
2. Deprecate raw `pkexec nmcli …` path.
3. Remove binary-only allowlist elevation once verbs cover all call sites.

## Threat model impact

| Residual today | After helper |
|----------------|--------------|
| Same-UID drives IPC → polkit → generic pkexec | Same-UID still needs user polkit approval, but argv is fixed |
| VPN script TOCTOU on user path | Helper re-opens + re-hashes under root before exec |
| GUI/local cleanup `ip link del` | Verb `iface-del` with medic* only |

Unchanged: same-UID + user-approved polkit remains the primary residual (single-user desktop).

## Testing strategy

| Layer | Tests |
|-------|-------|
| Unit | Verb validation, medic* filter, JSON errors |
| Integration | Mock pkexec; assert helper argv construction |
| Manual | Live pkexec on one distro per release checklist |
| CI | Dry-run helper without root; policy XML well-formed |

## Open decisions

1. **Language of helper:** Python (share validators) vs Go/Rust (smaller attack surface, no user venv). Recommendation: **Python first** in `netmedic` package with `console_scripts` entry `netmedic-helper`, then optional native rewrite.
2. **Pass iface/conn as flags or JSON:** flags for simple verbs; JSON for multi-field (`change-dns`).
3. **Whether IPC polkit check remains** once helper is annotated: keep both initially (double prompt risk). Prefer **server-side polkit only** *or* **helper polkit only** after UX validation — not both interactive prompts.

## Acceptance criteria (v1.5)

- [ ] Every `require_root=True` production call site goes through a helper verb.
- [ ] No `pkexec nmcli|ip|ufw|systemctl|env …` direct construction outside helper.
- [ ] Polkit policy annotations point at helper path.
- [ ] VPN script execution re-hashes under elevated context.
- [ ] Tests cover invalid iface / DNS / client name at helper boundary.
- [ ] Threat model and ARCHITECTURE updated for single elevation path.

## Related

- [THREAT_MODEL.md](THREAT_MODEL.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [IPC_API.md](IPC_API.md)
- `action_catalog.py`, `system.py`, `polkit_auth.py`
