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

## v1.5.0 — Privileged Helper (Released)

- [x] Phase B: in-tree `netmedic-helper` verbs + dry-run + `run_elevated` flag ([PRIVILEGED_HELPER.md](PRIVILEGED_HELPER.md))
- [x] Phase C: polkit path annotations + libexec wrapper install script
- [x] Production call sites use `run_elevated` (network + VPN operators)
- [x] Auto-enable helper when `/usr/libexec/netmedic/helper` is installed
- [x] Phase D: helper-only production elevation; single polkit prompt; system-owned helper lib
- [x] `netmedic --status` health CLI + SECURITY.md
- [ ] Distro packages (deb/rpm) — skeleton under `packaging/`

## v1.6.0 — Honest Repair (RC1 v1.6.0-rc1, Soak)

- [x] `VERBS.md` live contract + guardian 1/2/3 (ratchets) + `ResultCode` (models.py:59) — exit 0 ≠ fixed
- [x] `probes.py` single source DNS+TCP+https+captive + NM divergence, TCP-only `internet_ok`
- [x] Smart Repair `SKIPPED` when healthy, `partial` DNS→WAN, `settle` poll `ui.py:456` (no sleep blind)
- [x] `canary_shim_prod` UserWarning (outside DeprecationWarning shadowing) + `filterwarnings` error last
- [x] `netmedic-sim` v0 `tools/netmedic-sim/` `nmsim-*` + 2 scenarios + golden `tests/test_golden_replay_ns.py` (<30s)
- [x] `captureWarnings(True)` → `netmedic.log` + `filterwarnings` ignore DeprecationWarning noise
- [ ] Soak p95 settle <5s / recheck <10s, zero misclass — gate to `v1.6.0` final

## v1.6.1 — Post-release (1.6 backlog, ordered)

- [ ] mtr `--report --json` in `details` (bounded 10s)
- [ ] Snapshots sanitized (`system.py` redaction reuse) versioned
- [ ] RFC 8910 opt 114 `captive-portal` + `networkctl renew` fallback (systemd ≥248)
- [ ] Multi-interface candidates (`network.py:155` `details.candidates` + metric)
- [ ] AppImage helper bundling (1–2d design) — separated from `SKIP-03` (`curl --fail` 0.5d)

## v2.0.0 — Framework (Future)

## v2.0.0 — Framework (Future)

- [ ] Full plugin architecture with discovery
- [ ] Multi-interface management (bridge/bond)
- [ ] Remote diagnostics via secure channel
- [ ] Internationalization (i18n)