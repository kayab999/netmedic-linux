# Changelog

All notable changes to NetMedic Linux are documented here.

## [Unreleased]

### Fixed
- Smart Repair crashed with `'dict' object has no attribute 'lower'` on failed diagnostics (WAN unplug): `payload_to_net_result` called `.lower()` on dict `details`.
- `scripts/netns-golden.sh` no longer treats vacuous skips as success: pytest logs must contain the expected `passed` counts.
- CI preflight no longer fails on GitHub-hosted runners: install `network-manager` (nmcli) with the other system packages.
- CI test job runs under Xvfb and installs Polkit GI typelib so GTK/polkit tests can run on hosted runners.

## [1.6.0] — 2026-09-10 — RC2 v1.6.0-rc2

### Fixed
- Dock / `.desktop` launch crashed with `ModuleNotFoundError: netmedic.constants` when the strict-editable snapshot lagged source (v1.6.0 modules `constants`/`probes`/`canary_shim_prod`). `gui.py` no longer imports `MainWindow` at module load so startup errors can show a GTK dialog instead of a silent `sys.exit(1)` (`Terminal=false`). Launch tests compare the strict snapshot to source and import the dock GUI stack with `PYTHONPATH` cleared — the path the gate/VM runbook never exercised.
- **R1 actually enforced:** `probes.check_internet_access` no longer treats ICMP success as `internet_ok` (TCP-only). TCP-blocked + ICMP-ok is `PARTIAL`, not healthy/SKIPPED. Captive-portal hint runs when gateway is up and TCP is down (not only when DNS also failed). Zombie `2/3 steps succeeded` simulator tests replaced by `ResultCode` icon contract. CI runs `sudo ./scripts/netns-golden.sh`. `NETMEDIC_POST_REPAIR_VERIFY=0` is debug-only (EXECUTED ⚠️, never OK/✅).
- **netns harness:** `pytest.mark.netns` + skipif as a list (rc1 skipif stomped the marker → `-m netns` collected 0). Wrapper aborts if collect-only `-m netns` < 2. Scenario A does not DROP udp/53 (blackhole hung `getent` 30s×2). `getent` timeout 5s. Executed: `test_golden_wan_drop` PASSED 18.98s, `test_golden_icmp_ok_tcp_blocked` PASSED 1.60s.

## [1.6.0] — 2026-09-08 — RC1 v1.6.0-rc1

> **SemVer:** breaking (Smart Repair contract, `NetResult.code`, IPC 1.1). Minor bump, not patch. Previous `v1.5.1-rc1` deleted — use `v1.6.0-rc1`.

## [Unreleased]

### Breaking
- **Smart Repair semantics reverted with cause (replaces 1.1.1 ratio):** pre-diag no longer counts in repairs ratio; repairs `2/2` + `pre/post` delta, `SKIPPED` when healthy, `PARTIAL` distinct (docs: VERBS.md §5). Update tests in same PR (contract change).
- **NetResult contract:** `code: ResultCode` is source of truth, `success` shim deprecated (`DeprecationWarning`, `filterwarnings=error`). Consumers in `tools/` + `netmedic_ai/` migrated to `code`. Bump `IPC_API_VERSION` 1.0→1.1 (additive `code` field).

### Added
- `VERBS.md` live contract + `tests/test_verbs_doc.py` + `tests/test_no_string_flow.py` + `tests/test_success_shim_guard.py` (guardian 1/2/3, ratchets)
- `netmedic/probes.py` shared DNS+TCP+https+captive portal probes (single source, parallel, TCP-only `internet_ok`, PARTIAL `TCP blocked ICMP ok`)
- `netmedic/constants.py` unified `VIRTUAL_IFACE_MARKERS`
- `tools/netmedic-sim/` + `scripts/netns-golden.sh` + `tests/test_golden_replay_ns.py` (`-m netns`, 2 scenarios, `nmsim-*` prefix, trap EXIT, state reap)
- `netmedic --status` / `--status-json` install health CLI
- GUI startup install-health log line
- `SECURITY.md` disclosure and hardening checklist
- Debian packaging skeleton under `packaging/debian/`

## [1.5.0] — 2026-07-25

### Added
- Phase D privileged helper cutover: production root work only via `netmedic-helper`
- System-owned helper package at `/usr/lib/netmedic` (install script; no venv/repo path)
- Single interactive polkit prompt when helper is active (IPC skips duplicate polkit)
- `NETMEDIC_ALLOW_LEGACY_ELEVATION` for tests/emergency only
- Phase B/C helper verbs, `run_elevated`, polkit annotations, catalog contract tests
- `scripts/smoke_release.sh`, CI helper matrix

### Changed
- Direct `CommandRunner.run(..., require_root=True)` fails closed in production
- Version 1.5.0

### Docs
- Threat model / architecture / PRIVILEGED_HELPER updated for Phase D

## [1.4.1] — 2026-07-24

### Security
- Fix polkit GI subject construction: `new_for_owner(pid, start_time, uid)` (was miswired as uid/starttime)
- Pass process start_time to `pkcheck --process`; enable `--allow-user-interaction`
- Auth order: peer → confirmed → **session token** → polkit (blocks prompt spam)
- Peer UID required for **all** IPC actions, not only privileged
- Atomic restrictive create for IPC socket (umask) and session token (`O_CREAT|0600`)
- State/data directory ownership verification
- `medic[0-9a-f]{6}` allowlist before any privileged `ip link del` (orphan/state poison)
- VPN installer: FD re-hash, sealed runtime staging, mode `0500` after download
- `CommandRunner` elevated binary allowlist
- `vpn_list_clients` reclassified privileged (`com.kayab.netmedic.vpn-list`)
- AI disruptive actions require second confirmation; execute single-flight
- Smart Repair correctly skips IP renew on `Gateway Not Found`
- Installer installs polkit policy system-wide (sudo); safer desktop temp file
- Serialize privileged IPC execution (one at a time) to avoid worker-pool exhaustion
- `process_event` refuses unconfirmed tool execution (preview-only without `confirmed=True`)

### Fixed
- AI palette overlay no longer steals content clicks when hidden (pass-through + alignment)
- GUI repair/infrastructure/VPN catalog actions route through IPC (`GuiActionBridge`) for shared polkit + audit
- VPN install and start service exposed as privileged IPC (`vpn_install`, `vpn_start_service`)
- Synchronous virtual-iface cleanup on window destroy

### Ops
- `scripts/install-polkit-policy.sh` for system-wide polkit actions
- Installer prefers system-wide polkit policy; if install was skipped, run the script above

## [1.4.0] — 2026-07-16

### Added
- Peer UID enforcement for privileged IPC and session token issuance (`ipc_peer.py`)
- Versioned IPC API schema (`ipc_schema.py`) and integration guide (`docs/IPC_API.md`)
- systemd user unit for headless daemon (`netmedic-headless.service`)

### Changed
- `NETMEDIC_SKIP_POLKIT` honored only when `NETMEDIC_TEST_MODE=1` (production fail-closed)
- Polkit GI authorization uses `UnixProcess.new_for_owner` when available

## [1.3.0] — 2026-07-16

### Added
- Structured JSON audit log for privileged IPC (`audit.log` in state dir)
- Release integrity pipeline: `SHA256SUMS`, Python SBOM, GitHub release workflow
- Optional GPG detached signature for checksums via `RELEASE_GPG_*` CI secrets

### Fixed
- Documentation version alignment (README, RELEASE_NOTES, ROADMAP, desktop entry, netmedic_ai)

## [1.2.0] — 2026-07-16

### Added
- Polkit-backed privileged IPC (`polkit_auth.py`, `action_catalog.py`, policy XML)
- `docs/THREAT_MODEL.md` and CI PyInstaller build-smoke job
- Guardrail parameter validation (`param_validation.py`)
- Minimal operator plugin registration API
- Smart Repair skips IP renewal when no default gateway is detected
- 16+ new tests (polkit, MCP, guardrail params, action catalog, sensors)

### Fixed
- IPC server passes peer UID/PID for polkit checks via `SO_PEERCRED`
- Sensors firewall snapshot avoids `NetworkMedic()` singleton side effects
- VPN panel retries status on tab re-entry after failure
- AppImage `AppRun` sets GDK backend env vars
- Non-blocking GTK shutdown and `quit_gui_if_running()` on signals

## [1.1.1] — prior unreleased batch

### Added
- IPC thread pool, socket timeouts, bounded client queue, `SyncIPCClient` for MCP
- Enriched `sensors.get_network_snapshot()` (VPN, NM profile, rfkill, resolvectl DNS)
- AI toolkit actions: `restart_adapter`, `reset_tcp_ip_stack`, `toggle_firewall`
- `scripts/check-deps.sh`, installer flags (`--skip-tests`, `--keep-venv`, `--with-ai`)
- Socket E2E, sync client, sensors, and connection-targeting tests
- Signal teardown registry via `teardown.py`

### Fixed
- MCP network tools route through IPC with session tokens (requires running instance)
- Lifecycle lock no longer truncates PID before `flock` acquire fails
- PID-scoped virtual adapter state with orphan reap across dead processes
- `change_dns` targets NM connection on default-route interface
- Smart Repair reports step success ratio instead of always succeeding
- Infrastructure/VPN controls disabled during busy state
- Subprocess kill-on-timeout in `CommandRunner`
- AppImage packaging uses canonical `build_binary.sh`
- Menu launcher crash (`ImportError: __version__`) via strict editable install and relative imports
- IPC client now uses per-request sockets matching server lifecycle
- `renew_ip` no longer auto-restarts NetworkManager; firewall aborts on unknown UFW state
- Wi-Fi scan JSON parsing with channel-only fallback; safe DNS line parsing in sensors
- PyInstaller/AppImage bundle paths for icon and manual; desktop entry uses `netmedic` console script
- MCP mutating tools gated behind `NETMEDIC_MCP_ALLOW_MUTATING=1`

### Added
- GitHub Actions CI workflow, `pytest.ini`, `tests/conftest.py`, launch import tests
- AI palette focus styling; keyboard focus rings in theme

## [1.1.0] — 2026-06-18

### Added
- IPC session token authorization for privileged operations
- `change_dns()` via NetworkManager (`nmcli`)
- AI command palette (Ctrl+Space) integrated in main window
- `netmedic_ai` package restored with guardrail whitelist
- Headless mode without GTK import (`runtime.py` / `gui.py` split)
- Stale lock recovery after crash (SIGKILL)
- Comprehensive test suite (45+ tests)
- GitHub-ready project structure (`scripts/`, `assets/`, `docs/`, `tools/`)

### Fixed
- Duplicate `main()` definition in `app.py`
- Missing `import os` in About dialog
- VPN operator no longer stops system OpenVPN on app exit
- IPC server now starts on application launch
- Revoke client post-operation PKI verification
- Resilience test uses isolated `XDG_STATE_HOME`
- `vpn_reconnect` restarts OpenVPN instead of resetting NetworkManager
- IPC newline framing and full-request socket locking
- About manual link, version display, icon/desktop install paths
- VPN start service control; client revoke/add validation feedback
- Headless shutdown cleanup, signal reentrancy guard, bootstrap lock rollback
- AI console markup escaping, English labels, loading indicator
- AppImage desktop entry Exec/Icon paths; `donate` IPC handler
- Sensor and firewall command timeout/exit-status handling

### Security
- Command log redaction for passwords/tokens
- SHA256 pinning for Angristan VPN installer
- GGUF model integrity verification via `.sum` file
- State files written with `0o600` permissions

## [1.0.0-rc1] — 2026-05-08

- Foundational Sovereign Runtime Core
- Native network diagnostics
- AI Pilot (Nandi Mini) with IPC orchestration
- GTK interface with hardened lifecycle management