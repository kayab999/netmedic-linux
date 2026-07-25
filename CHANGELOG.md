# Changelog

All notable changes to NetMedic Linux are documented here.

## [Unreleased]

### Added
- Phase B privileged helper prototype: `netmedic-helper` CLI, verb registry, dry-run planning
- `CommandRunner.run_elevated(verb, args)` with opt-in / auto helper mode
- Phase C: polkit `exec.path` annotations + `/usr/libexec/netmedic/helper` install wrapper
- Network/VPN elevated operations migrate to fixed helper verbs (legacy argv if helper off)

### Docs
- Privileged helper design for v1.5 (`docs/PRIVILEGED_HELPER.md`); Phase B/C progress

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