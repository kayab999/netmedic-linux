# Release Checklist — v1.6.0 Soak Gate (closed 2026-09-25: shipped with partial physical soak; `netns-golden` A+B in CI is the standing regression gate — see ROADMAP)

> Soak exit criteria (must pass before `v1.6.0` final — not dates, but evidence):
> - **p95 `settle` < 5s and p95 `recheck` < 10s** (from `ui.py:456` `logging.info settle %ss` + diag timing; budget PR3 ~15s worst case). Extract mechanically, not by reading:
>   ```bash
>   grep -oP 'settle \K[0-9.]+s' ~/.local/state/netmedic/netmedic.log | sort -n | awk '{a[NR]=$1} END {printf "p95: %ss (n=%d)\n", a[int(NR*0.95)], NR}'
>   ```
>   `n` is sample count — **if `n=0` (or `n<5` broken-network repairs), soak is empty, not passed** (fails, not approves). This is the soak version of `2/3 steps succeeded`.
> - zero `CANCELLED`/`ERROR` misclassified in `netmedic.log`/`audit.log` period (`code` vs `message`)
> - `POST_REPAIR_VERIFY` default ON, no disable needed
> - Installed **from tag** (`clone --branch v1.6.0-rc1` → `./install.sh` → `./scripts/install-polkit-policy.sh`) — dogfooding install path, not `venv` dev
> - **Minimum samples (otherwise soak is empty, not passed):** ≥5 Smart Repair on **broken** network (≥2 deliberate WAN-unplug 10 min, the real incident dogfooded) + ≥1 cancel via Escape (`audit.log` `code=CANCELLED`) + ≥1 healthy short-circuit `SKIPPED` (`code=SKIPPED`, no elevation). p95 computed only on broken-network samples; `netns` `nmsim-*` samples excluded from soak p95 (synthetic topology, not real).
> - **Failure path:** p95 breach → tune `settle`/`timeout` → **`v1.6.0-rc2`** (never patch `rc1` in place — rc tag is a contract once public)

# Release Checklist — v1.0.0+

Use this checklist before tagging a public release.

## 1. Code Quality

- [ ] Automated smoke: `./scripts/smoke_release.sh` (version, helper dry-run, pytest)
- [ ] Netns goldens: `sudo ./scripts/netns-golden.sh` (A WAN-drop + B TCP-blocked/ICMP-ok → PARTIAL). CI job `netns-golden` must be green.
- [ ] All tests pass: `venv/bin/python -m pytest tests/ -v`
- [ ] Linter clean: `venv/bin/ruff check netmedic/ netmedic_ai/ tools/ tests/`
- [ ] Version aligned in `netmedic/pyproject.toml`, `netmedic_ai/`, `CHANGELOG.md`, `README.md`, `docs/RELEASE_NOTES.md`
- [ ] Policy contract: privileged actions ⊆ polkit XML with helper `exec.path` annotate

## 2. Installation

 - [ ] Clean VM (Ubuntu 24.04 GNOME, desktop session, not SSH) install **from tag** via `./install.sh` + `./scripts/install-polkit-policy.sh` (validates `config.py:60` both `/usr/libexec` and `/usr/lib` paths)
 - [ ] GUI launches: `venv/bin/netmedic`
 - [ ] Headless launches: `venv/bin/netmedic --headless`
- [ ] Desktop launch: `gtk-launch netmedic` (or the `Exec=` line from `~/.local/share/applications/netmedic.desktop`) — not only a PYTHONPATH shell or `runbook_vm_evidence.py`
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