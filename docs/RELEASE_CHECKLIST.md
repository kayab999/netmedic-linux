# Release Checklist — v1.0.0+

Use this checklist before tagging a public release.

## 1. Code Quality

- [ ] All tests pass: `PYTHONPATH="netmedic:." venv/bin/python -m pytest tests/ -v`
- [ ] Linter clean: `venv/bin/ruff check netmedic/ netmedic_ai/ tests/`
- [ ] Version aligned in `netmedic/pyproject.toml`, `CHANGELOG.md`, `README.md`

## 2. Installation

- [ ] Clean VM install via `./install.sh`
- [ ] GUI launches: `venv/bin/python -m netmedic`
- [ ] Headless launches: `venv/bin/python -m netmedic --headless`
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
- [ ] IPC privileged actions rejected without token
- [ ] VPN service remains running after app close

## 6. Packaging

- [ ] `./scripts/build_binary.sh` produces `dist/netmedic`
- [ ] `./scripts/package_appimage.sh` produces AppImage (if appimagetool available)
- [ ] Release assets uploaded to GitHub Releases page
- [ ] `CHANGELOG.md` and `docs/RELEASE_NOTES.md` updated