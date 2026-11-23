# Privileged Helper Design (v1.9.0 — typed verbs, installed contract)

## Status

This document describes the helper as shipped in **1.9.0** and keeps the
migration history for context. Production elevation is helper-only; the legacy
`pkexec <allowlisted argv>` path exists for tests and is disabled unless
`NETMEDIC_TEST_MODE=1` and `NETMEDIC_ALLOW_LEGACY_ELEVATION=1` are both set.

`HELPER_VERSION` is `1.9.0`. The daemon refuses privileged work unless the
installed helper reports the same version through `--version` with `ok=true`
(see “Version gate” below). Re-run `./scripts/install-polkit-policy.sh` after
updating the project.

## Background (pre-v1.6)

The original design elevated with:

```text
IPC polkit (com.kayab.netmedic.*)  →  pkexec <arbitrary allowlisted argv>
```

The fine-grained polkit action IDs gated **IPC entry**, not the **actual root
command**: `CommandRunner` prefixed any allowlisted binary with generic
`org.freedesktop.policykit.exec` (`pkexec`). That was defense-in-depth for
accidental misuse, but not least privilege.

| Property | Legacy (tests only) | Current 1.9.0 |
|----------|---------------------|---------------|
| Polkit subject | IPC action ID | Per-verb wrapper path `helper-<verb>` |
| Root argv | Client-chosen within binary allowlist | Fixed per-verb argv template |
| Audit | IPC audit log | IPC audit + root-side journal record |
| Attack surface | Any code path reaching `CommandRunner.run(..., require_root=True)` | Only helper entrypoints |

## Goals

1. **One setuid-free helper** invoked only via `pkexec` / polkit with annotated path.
2. **Action → argv templates** owned by the helper (not the GUI/IPC worker).
3. **Re-hash / re-open** of operator scripts under elevation for VPN install.
4. **No shell**; argv-only execution.
5. **Backward-compatible IPC API** (action names unchanged).

## Non-goals (v1.9.0)

- Multi-user mutually untrusted operators
- Network-exposed helper
- Replacing NetworkManager with a custom daemon
- Shipping a native `.deb`/`.rpm` in 1.9.0 (tracked separately)

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
| Polkit policy | `annotate` each action with a unique `org.freedesktop.policykit.exec.path` = `/usr/libexec/netmedic/helper-<verb>`; `exec.argv1` is not used because pkexec 0.105 matches on path only |
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
| `vpn-install` | install | resolve vendored pin, stage, run `install <flags>` |
| `vpn-add-client` | add | resolve vendored pin, stage, run `client add <name> --output`, deliver artifact |
| `vpn-revoke-client` | revoke | resolve vendored pin, stage, run `client revoke <name> --force` |
| `iface-del` | cleanup | only `medic[0-9a-f]{6}` |

**Deadline semantics:** `--timeout` is the total deadline for the whole verb,
not a per-command limit. Multi-command verbs (`change-dns`, `restart-adapter`)
share it and never start a command after the deadline. For `change-dns`,
`R = min(10s, total/3)` is reserved for rollback. The daemon waits
`timeout + CommandRunner._IPC_MARGIN` (see `netmedic/system.py`) so the
process-group kill cannot cut the rollback in half.

Output: single JSON line on stdout:

```json
{"ok": true, "message": "...", "details": null}
```

Exit codes: `0` success, `1` operational failure, `2` invalid args, `3` integrity/auth local check failed, `126` cancelled.

### Version gate (1.9.0)

Before any privileged operation, `CommandRunner._check_helper_version()` runs
the installed wrapper with `--version` and requires **all** of:

1. exit code `0`
2. a JSON object
3. `ok is True`
4. a non-empty `version`
5. an exact match with `HELPER_VERSION`

Missing helper, timeout, non-zero exit, invalid JSON, `ok=false`, an empty
version and a mismatch all block elevation with a reinstall hint. The explicit
development marker `python|-m|netmedic.helper_main` keeps its in-repo fallback;
production never takes that path.

### Policy retention (`keep_auth`)

`action_catalog.ACTIONS` sets `keep_auth` per action. It maps to polkit
`allow_active`:

- `keep_auth=True` → `auth_admin_keep` (5-minute window for low-impact,
  idempotent verbs such as `flush-dns` and `renew-ip`)
- `keep_auth=False` → `auth_admin` (re-prompt every time for disruptive or
  destructive verbs such as `change-dns`, firewall, VPN install/revoke)

`allow_any` and `allow_inactive` stay `auth_admin`.

### Installed layout and staging

`./scripts/install-polkit-policy.sh` writes:

| Path | Content |
|------|---------|
| `/usr/libexec/netmedic/helper` | `sh` wrapper: fixed `/usr/bin/python3 -I -s` + launcher |
| `/usr/lib/netmedic/_run_helper.py` | root-owned launcher with explicit `sys.path` |
| `/usr/lib/netmedic/netmedic/` | `helper_main.py`, `helper_verbs.py`, `validators.py`, `action_catalog.py`, root-owned `0644` |
| `/usr/lib/netmedic/scripts/openvpn-install.sh` | vendored installer, root-owned `0644` |
| `/usr/share/polkit-1/actions/com.kayab.netmedic.policy` | generated policy, root-owned `0644` |

VPN verbs resolve the fixed installer path, read it with `O_NOFOLLOW`, reject
non-regular/foreign-owned/writable/oversized files, verify the pinned SHA-256,
copy it to a root-owned staging directory under `/run/netmedic` (`0700`) and
execute only that copy.

### Argument validation (helper-side)

- Interface names: `^[A-Za-z0-9._@+-]+$` (and medic allowlist for delete).
- DNS: IPv4 regex (same as `network.py`).
- VPN client names: `^[a-zA-Z0-9_-]+$`.
- Connection names: length cap + charset; prefer NM UUID when available later.

### Polkit policy sketch

```xml
<action id="com.kayab.netmedic.flush-dns">
  ...
  <!-- Unique per verb: pkexec 0.105 only compares exec.path. -->
  <annotate key="org.freedesktop.policykit.exec.path">/usr/libexec/netmedic/helper-flush-dns</annotate>
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

### Phase C — Packaging + call-site migration ✅

1. ✅ `scripts/install-polkit-policy.sh` installs `/usr/libexec/netmedic/helper` wrapper + annotated policy
2. ✅ Polkit actions annotate `org.freedesktop.policykit.exec.path` → helper
3. ✅ Production call sites in `network.py` / VPN operator use `CommandRunner.run_elevated`
4. ✅ Auto-enable helper when system wrapper exists (`NETMEDIC_USE_HELPER` unset)
5. AppImage note: helper still needs host install for elevation (AppImage cannot ship setuid)

### Phase D — Cutover ✅ (v1.6.1; extended through 1.9.0)

1. ✅ Production elevation only via helper; `require_root=True` blocked without `NETMEDIC_ALLOW_LEGACY_ELEVATION`
2. ✅ Single interactive polkit: IPC skips polkit when helper active; `pkexec helper` is the prompt
3. ✅ System install copies helper modules to `/usr/lib/netmedic` (no venv/repo path)
4. ✅ VPN typed verbs resolve the vendored installer pin, stage a root-owned copy and exec only that copy
5. ⏳ deb/rpm packaging still open (Phase packaging track)

## Threat model impact

| Residual | After Phase D |
|----------|---------------|
| Same-UID + user polkit approve | Still possible (desktop model) |
| Generic `pkexec nmcli…` | Blocked in production |
| Double polkit prompt | Avoided (helper-only interactive) |
| Helper tied to git checkout | Fixed via `/usr/lib/netmedic` |

## Testing strategy

| Layer | Tests |
|-------|-------|
| Unit | Verb validation, medic* filter, JSON errors |
| Integration (CI) | `helper-install-integration`: installs helper + policy, checks `--version`/`--list-verbs`, all 12 unique per-verb `pkaction` rows (`exec.path`, `allow_active`), every dry-run and invalid-input rejection |
| Integration (unit) | Mock pkexec; assert helper argv construction and the fail-closed version gate |
| Manual / VM | Live pkexec, interactive Polkit, destructive verbs, rollback and journal audit on a clean Ubuntu VM (`docs/VM_CHECKLIST.md`) |

## Resolved decisions

1. **Language:** Python first, sharing validators and `action_catalog`; a native
   rewrite remains a future option.
2. **Arguments:** JSON for multi-field verbs (`change-dns`, VPN), flags for
   simple verbs; `--dry-run` and `--execute` share the same planned argv.
3. **Polkit ownership:** helper-only interactive authorization in production;
   the IPC layer checks peer/token/confirmation and does not prompt again.
4. **Policy generation:** the XML is generated from `action_catalog.ACTIONS`;
   `scripts/generate_policy.py --check` gates drift.

## Acceptance criteria (v1.9.0)

- [x] Every `require_root=True` production call site goes through a helper verb.
  (`system.py` refuses direct elevation outside `TEST_MODE`-gated legacy.)
- [x] No `pkexec nmcli|ip|ufw|systemctl|env …` direct construction outside helper.
  (Production path is `pkexec helper <verb>` only; raw argv survives in tests.)
- [x] Polkit policy annotations point at a unique per-verb wrapper path.
  (Enforced by `test_policy_and_catalog_contract.py`: 12 distinct
  `/usr/libexec/netmedic/helper-<verb>` values, no `exec.argv1`.)
- [x] VPN script execution re-hashes under elevated context.
  (Root-owned staging in `/run/netmedic` + double hash; F1 pin in v1.6.1.)
- [x] Tests cover invalid iface / DNS / client name at helper boundary.
  (`test_helper_verbs.py`, `test_m4_validators.py`.)
- [x] Threat model and ARCHITECTURE updated for single elevation path.
  (Threat model now states 1.9.0; `VERBS.md` is the live verb contract.)
- [x] Installed wrapper and policy verified in CI.
  (`helper-install-integration`: root-owned layout, version, verbs, 12
  `pkaction` rows, dry-runs, invalid-input rejection.)
- [x] Version mismatch or an unreadable probe blocks elevation.
  (`tests/test_helper_version_gate.py`; rc, JSON, `ok`, version and timeout.)
- [x] IPC acceptance and message size are bounded.
  (`_MAX_CONNECTIONS` semaphore; exact 65,536-byte framing limit.)

## Related

- [THREAT_MODEL.md](THREAT_MODEL.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [IPC_API.md](IPC_API.md)
- `action_catalog.py`, `system.py`, `polkit_auth.py`
