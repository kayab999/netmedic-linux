# NetMedic Roadmap

## Vision

NetMedic aims to be a sovereign, open-source network management platform for Linux — transparent, verifiable, and resilient. The GUI is one client; the privileged IPC core is the product.

## v1.0.0 — Released

- [x] Core network diagnostics and repair
- [x] GTK3 interface with tabbed layout
- [x] VPN operator (Angristan) with SHA256 integrity
- [x] Lifecycle management (singleton lock, crash recovery)
- [x] IPC server with session token authorization
- [x] Optional AI pilot with guardrail whitelist

## v1.1.0 — Released (2026-06-18)

- [x] IPC session tokens and security hardening
- [x] Headless runtime / GUI split
- [x] AI pilot restoration with guardrail whitelist
- [x] Repository restructure (`scripts/`, `assets/`, `tools/`, `docs/`)

## v1.2.0 — Released (2026-07-16)

- [x] Polkit-backed privileged IPC authorization
- [x] Action catalog as single source of truth
- [x] Fail-closed AI toolkit execution
- [x] CI PyInstaller build smoke
- [x] Threat model documentation
- [x] 95-test trust-core suite

## v1.3.0 — Enterprise Governance (Released 2026-07-16)

- [x] Structured audit log for privileged IPC
- [x] Release integrity pipeline (SHA256SUMS, SBOM, GitHub workflow)
- [x] Documentation version sync

## v1.4.0 — Platform (Released 2026-07-16)

- [x] Versioned IPC action schema and integration guide
- [x] Peer UID enforcement hardening
- [x] Production fail-closed without `NETMEDIC_SKIP_POLKIT`
- [x] systemd user unit for headless daemon
- [ ] Real-time network sensor visualization (deferred UI)
- [ ] Flatpak packaging (deferred)

## v1.4.1 — Security Hardening (Released 2026-07-24)

- [x] Enterprise audit remediation (polkit subject, auth order, medic* allowlist)
- [x] GUI → IPC bridge for shared polkit + audit on catalog actions
- [x] VPN install/start privileged IPC; list-clients reclassified privileged
- [x] Privileged IPC concurrency limit; AI process_event confirmation gate
- [x] Overlay click-steal fix; UI wiring regression suite
- [x] Polkit install script and installer system-path install

## v2.0.0 — Framework (Future)

- [ ] Full plugin architecture with discovery
- [ ] Multi-interface management (bridge/bond)
- [ ] Remote diagnostics via secure channel
- [ ] Internationalization (i18n)