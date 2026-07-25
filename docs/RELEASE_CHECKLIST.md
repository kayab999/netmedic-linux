# Release Checklist — v1.0.0+

Use this checklist before tagging a public release.

## 1. Code Quality

- [ ] Automated smoke: `./scripts/smoke_release.sh` (version, helper dry-run, pytest)
- [ ] All tests pass: `venv/bin/python -m pytest tests/ -v`
- [ ] Linter clean: `venv/bin/ruff check netmedic/ netmedic_ai/ tests/`
- [ ] Version aligned in `netmedic/pyproject.toml`, `netmedic_ai/`, `CHANGELOG.md`, `README.md`, `docs/RELEASE_NOTES.md`
- [ ] Policy contract: privileged actions ⊆ polkit XML with helper `exec.path` annotate

## 2. Installation

- [ ] Clean VM install via `./install.sh`
- [ ] GUI launches: `venv/bin/netmedic`
- [ ] Headless launches: `venv/bin/netmedic --headless`
- [ ] Desktop entry appears in application menu
- [ ] Log created at `~/.local/state/netmedic/netmedic.log` (mode 600)

## 3. Core Features

- [ ] Smart Repair completes without errors
- [ ] Check Connectivity shows gateway/DNS/internet status
- [ ] Flush DNS and Renew IP work (pkexec prompt)
- [ ] Wi-Fi scan returns channel recommendations

## 4. Infrastructure

- [ ] VPN install flow (download → SHA256 verify → install)
- [ ] Add and revoke VPN client with PKI verification
- [ ] Firewall toggle reflects actual UFW state
- [ ] Privileged action cancellation handled gracefully

## 5. Security & Resilience

- [ ] Second instance blocked with clear error message
- [ ] Crash recovery: app restarts after SIGKILL
- [ ] IPC privileged actions rejected without token and polkit authorization
- [ ] Privileged IPC writes structured lines to `~/.local/state/netmedic/audit.log`
- [ ] Privileged IPC rejects peers whose UID does not match the daemon owner
- [ ] `NETMEDIC_SKIP_POLKIT` has no effect without `NETMEDIC_TEST_MODE=1`
- [ ] Helper install (optional but recommended): `./scripts/install-polkit-policy.sh`
- [ ] `pkaction | grep kayab` shows actions; `/usr/libexec/netmedic/helper flush-dns --dry-run` works
- [ ] Polkit policy installed (`com.kayab.netmedic.policy`)
- [ ] VPN service remains running after app close

## 6. Packaging

- [ ] `./scripts/prepare_release_assets.sh` produces `dist/netmedic`, `SHA256SUMS`, and SBOM
- [ ] `./scripts/package_appimage.sh` produces AppImage (if appimagetool available)
- [ ] Tag push triggers `.github/workflows/release.yml` (or manual upload)
- [ ] `sha256sum -c SHA256SUMS` passes on release artifacts
- [ ] `CHANGELOG.md` and `docs/RELEASE_NOTES.md` updated