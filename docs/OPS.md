# NetMedic Ops Runbook (Internal IT, v1.6)

Target: Ubuntu 22.04/24.04, Python 3.10–3.12, single-user desktop.

## 1. Install

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
./install.sh
./scripts/install-polkit-policy.sh
netmedic --status   # want production_ready:true, helper /usr/libexec/netmedic/helper
```

`install.sh` creates `venv/`, strict-editable `netmedic/`, desktop entry, `~/.config/systemd/user/netmedic-headless.service`.

## 2. Health

```bash
netmedic --status
netmedic --status-json | python3 -m json.tool
```

Gate: `production_ready:true` = helper present + policy (`pkaction com.kayab.netmedic.flush-dns`) + bins (`nmcli/ip/resolvectl`) + state dir `0700`.

## 3. Run modes

* GUI: `venv/bin/netmedic` (or dock `.desktop`)
* Headless: `venv/bin/netmedic --headless` or `systemctl --user enable --now netmedic-headless.service`

Single instance via `flock`. Stale lock reaped on PID death. Socket `ipc.sock 0600`, token `ipc.token 0600` removed on clean exit.

## 4. Logs

* `~/.local/state/netmedic/netmedic.log` (Rotating 1M×3, INFO)
* `~/.local/state/netmedic/audit.log` (JSONL, 1M×3, 0600) — every privileged granted/denied/busy with `peer_uid/pid,duration_ms,outcome`. `session_token` redacted; secrets in `user_request/params` truncated to 500ch.
* Soak: `grep settle|recheck netmedic.log` for p95; `SOAK_PLAN.md` gate `n>=5 broken+cancel+healthy, 0 fails`.

## 5. Env matrix (production)

| Var | Prod | Test only |
|---|---|---|
| `NETMEDIC_USE_HELPER` | unset (auto-on if helper installed) | `0/1` for matrix |
| `NETMEDIC_ALLOW_LEGACY_ELEVATION` | **unset** | `1` + `USE_HELPER=0` |
| `NETMEDIC_SKIP_POLKIT` | **unset** | `1` + `NETMEDIC_TEST_MODE=1` |
| `NETMEDIC_MCP_ALLOW_MUTATING` | unset unless intentional | — |
| `NETMEDIC_HELPER_PATH` | unset (use `/usr/libexec/...`) | dev override; ignored when `euid==0` |
| `NETMEDIC_POST_REPAIR_VERIFY` | unset (default ON) | `0` debug-only: repairs report `EXECUTED`, never `OK` |
| `NETMEDIC_TEST_MODE` | **unset** | `1` to honor `SKIP_POLKIT` in tests |

Overrides are ignored when running as root (fail-closed, warning logged).

## 6. Security ops

* Elevation: single path `pkexec /usr/libexec/netmedic/helper <verb> --execute --json`. No `shell=True`. Verbs fixed in `helper_verbs.py`, contract in `VERBS.md`.
* Services allowlisted to `openvpn-server@*.service` + `NetworkManager`. `vpn-run-script` requires absolute path + 64-hex SHA + `XDG_RUNTIME_DIR` staging.
* Permissions: state/data `0700` owner-checked, secrets `0600`, helper `root:root 644/755`, VPN script `0500`.
* Alert: rapid distinct-PID privileged bursts in `audit.log` → investigate same-UID abuse (`auth_admin_keep` reduces friction — prefer `auth_admin` for `vpn-install/run-script`).

## 7. Backup / update

* No daemon DB — state is `created_ifaces.*.json` + logs. Backup `~/.local/state/netmedic/` optional.
* Update helper after code change: re-run `./scripts/install-polkit-policy.sh` (`/usr/lib/netmedic` must match repo).
* Release verify: `sha256sum -c SHA256SUMS`, `SHA256SUMS.asc` (GPG required on `v*` tags), `sbom-python-*.txt` (freeze + CycloneDX).

See `docs/THREAT_MODEL.md`, `docs/PRIVILEGED_HELPER.md`, `VERBS.md`, `docs/IPC_API.md`.
