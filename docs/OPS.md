# NetMedic Ops Runbook (Internal IT, v1.6)

Target: Ubuntu 22.04/24.04, Python 3.10–3.12, single-user desktop.

## 1. Install

```bash
git clone https://github.com/kayab999/netmedic-linux.git
cd netmedic-linux
./install.sh
./scripts/install-polkit-policy.sh
netmedic --status   # want core_ready:true; privileged_ready is separate
```

`install.sh` creates `venv/`, strict-editable `netmedic/`, desktop entry, `~/.config/systemd/user/netmedic-headless.service`.

## 2. Health

```bash
netmedic --status   # core diagnostics gate; privileged readiness is separate
netmedic --status --require-privileged   # automation that needs L2
netmedic --status-json | python3 -m json.tool
```

Gate:

- `core_ready:true` = supported Python runtime + state dir `0700` owned by the
  current user. It does **not** require `nmcli`, `ip`, `curl`, the helper or
  Polkit.
- `privileged_ready:true` = installed helper + library, `pkexec` and all 12
  Kayab Polkit actions registered.
- `production_ready` is a deprecated alias of `core_ready`.
- `--require-privileged` exits 1 when `privileged_ready` is false.

The JSON also carries `schema_version`, `scope` (current network namespace,
with a conservative container hint) and `capabilities` (L0/L1/L2 with separate
`availability` and `outcome`).

## 3. Run modes

* GUI: `venv/bin/netmedic` (or dock `.desktop`)
* Headless: `venv/bin/netmedic --headless` or `systemctl --user enable --now netmedic-headless.service`

Single instance via `flock`. Stale lock reaped on PID death. Socket `ipc.sock 0600`, token `ipc.token 0600` removed on clean exit.

## 4. Logs

* `~/.local/state/netmedic/netmedic.log` (Rotating 1M×3, INFO)
* `~/.local/state/netmedic/audit.log` (JSONL, 1M×3, 0600) — two records per privileged action: `privileged_intent` (before execution) + `privileged_ipc` (completion with `peer_uid/pid,duration_ms,outcome`). `session_token` redacted; secrets in `user_request/params` truncated to 500ch.
* **Fail-closed audit:** if `audit.log` is unwritable (disk full), privileged actions are **refused** with "Audit unavailable" — no action without an audit record. If you see this: free space/quota/inodes under `$HOME`, then retry. This trades availability for auditability on purpose.
* Soak: `grep settle|recheck netmedic.log` for p95; `SOAK_PLAN.md` gate `n>=5 broken+cancel+healthy, 0 fails`.
* Long soak: `scripts/soak_sample.sh` hourly via cron appends `soak.csv` (RSS/FDs/threads/log sizes) — flat slopes on non-log resources required.

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
| `NETMEDIC_HELPER_EXECUTE` | **unset** | `1` + `TEST_MODE=1` to force helper execution in tests; ignored otherwise |
| `NETMEDIC_PORTAL_URL` | unset (default `http://connectivity-check.ubuntu.com`) | Override the captive-portal 204 endpoint (privacy: the default phones Ubuntu on every all-green diagnosis) |

Overrides are ignored when running as root (fail-closed, warning logged).

## 6. Security ops

* Elevation: single path `pkexec /usr/libexec/netmedic/helper <verb> --execute --json`. No `shell=True`. Verbs fixed in `helper_verbs.py`, contract in `VERBS.md`.
* Services allowlisted to `openvpn-server@*.service` + `NetworkManager`. `vpn-install`/`vpn-add-client`/`vpn-revoke-client` accept only typed, validated params; the helper resolves it to `/usr/lib/netmedic/scripts/openvpn-install.sh`, verifies the vendored pin, stages a root-owned copy in `/run/netmedic` (0700, unique per invocation), re-hashes there and execs — no downloads, no execution from user-writable paths.
* Permissions: state/data `0700` owner-checked, secrets `0600`, helper `root:root 644/755`, vendored VPN script `root:root 0644` under `/usr/lib/netmedic/scripts`.
* Alert: rapid distinct-PID privileged bursts in `audit.log` → investigate same-UID abuse (`auth_admin_keep` reduces friction — prefer `auth_admin` for `vpn-install/run-script`).

## 7. Backup / update

* No daemon DB — state is `created_ifaces.*.json` + logs. Backup `~/.local/state/netmedic/` optional.
* Update helper after code change: re-run `./scripts/install-polkit-policy.sh` (`/usr/lib/netmedic` must match repo).
* Release verify: `sha256sum -c SHA256SUMS`, `SHA256SUMS.asc` (GPG required on `v*` tags), `sbom-python-*.txt` (freeze + CycloneDX).
* Reproducibility: rebuilding from tag in a clean container (`Dockerfile.build`) yields a functionally identical binary, not necessarily a hash-identical one (PyInstaller embeds timestamps). Verify via behavior + SBOM, not hash equality.

See `docs/THREAT_MODEL.md`, `docs/PRIVILEGED_HELPER.md`, `VERBS.md`, `docs/IPC_API.md`.
