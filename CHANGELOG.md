# Changelog

All notable changes to NetMedic Linux are documented here.

## [1.1.0] — 2026-06-18

### Added
- IPC session token authorization for privileged operations
- `change_dns()` via NetworkManager (`nmcli`)
- AI command palette (Ctrl+Space) integrated in main window
- `netmedic_ai` package restored with guardrail whitelist
- Headless mode without GTK import (`runtime.py` / `gui.py` split)
- Stale lock recovery after crash (SIGKILL)
- Comprehensive test suite (39 tests)
- GitHub-ready project structure (`scripts/`, `assets/`, `docs/`, `tools/`)

### Fixed
- Duplicate `main()` definition in `app.py`
- Missing `import os` in About dialog
- VPN operator no longer stops system OpenVPN on app exit
- IPC server now starts on application launch
- Revoke client post-operation PKI verification
- Resilience test uses isolated `XDG_STATE_HOME`

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