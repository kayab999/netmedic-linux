# NetMedic Roadmap

## Vision

NetMedic aims to be a sovereign, open-source network management tool for Linux — transparent, verifiable, and resilient.

## v1.0.0 — Released

- [x] Core network diagnostics and repair
- [x] GTK3 interface with tabbed layout
- [x] VPN operator (Angristan) with SHA256 integrity
- [x] Lifecycle management (singleton lock, crash recovery)
- [x] IPC server with session token authorization
- [x] Optional AI pilot with guardrail whitelist
- [x] 39-test automated suite
- [x] Documentation and GitHub-ready structure

## v1.1.0 — Released (2026-06-18)

- [x] IPC session tokens and security hardening
- [x] Headless runtime / GUI split
- [x] AI pilot restoration with guardrail whitelist
- [x] Repository restructure (`scripts/`, `assets/`, `tools/`, `docs/`)
- [x] Icon/desktop install fixes and adversarial audit remediation
- [x] 45+ test automated suite

## v1.2.0 — Refinement (In Progress)

- [x] Polkit-backed privileged IPC authorization
- [x] Fail-closed AI toolkit execution
- [x] CI PyInstaller build smoke
- [x] Smart Repair gateway heuristic (skip renew when no gateway)
- [x] Minimal plugin operator registration API
- [ ] Real-time network sensor visualization (deferred UI)
- [ ] Flatpak packaging (deferred)

## v2.0.0 — Framework (Future)

- [ ] Full plugin architecture with discovery
- [ ] Multi-interface management (bridge/bond)
- [ ] Remote diagnostics via secure channel
- [ ] Internationalization (i18n)