# Security Advisory: v1.6.1 Privilege Boundary Fixes (F1–F5 + M1)

## Summary

NetMedic Linux v1.6.1 fixes five high-impact flaws in the privileged helper
(privilege boundary: helper, polkit policy, installer). A same-UID attacker
with one polkit approval could otherwise run arbitrary code as root (F1),
read arbitrary root files (F2), or hijack the root interpreter (F3).

## Affected / Fixed

- Affected: v1.6.0 and earlier (tag `v1.6.0`).
- Fixed: v1.6.1 (this branch, untagged until VM verification passes).

## Details

### F1 Critical — `vpn-run-script` trusted caller hash + free-form env

- Before: `helper_verbs.py plan_verb("vpn-run-script")` took `expected_sha256`
  from caller JSON; `helper_main.py` verified script bytes against that same
  value. Attacker script + own hash passed. Env keys unrestricted
  (`LD_PRELOAD`, `BASH_ENV`, `PATH` accepted).
- Fix: caller hash must equal root pin `PINNED_VPN_INSTALL_SHA256`
  (`65c3b53f…`, mirrors `AngristanOperator.EXPECTED_SHA256`); `script_id`
  allowlist (`openvpn-install`); env allowlist (11 Angristan vars only);
  helper re-checks pin on in-process calls and runs
  `env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin … /bin/bash <staged>`
  (noexec-safe, no env injection).
- Files: `netmedic/netmedic/helper_verbs.py`, `netmedic/netmedic/helper_main.py`,
  `netmedic/netmedic/operators/vpn/angristan.py`.

### F2 High — `vpn-list` arbitrary root read

- Before: `index_path` validated with `startswith("/etc/openvpn/")`;
  `/etc/openvpn/../shadow` accepted → `cat` as root.
- Fix: `index_path` param removed; fixed-path Python read with `O_NOFOLLOW`,
  regular-file check, 1 MiB cap.
- Files: `helper_verbs.py`, `helper_main.py::_read_vpn_index`.

### F3 High — root wrapper baked user interpreter

- Before: `install-polkit-policy.sh` used `command -v python3` (venv/pyenv/conda
  hijack) + `PYTHONPATH` + `-s -m`.
- Fix: pins `/usr/bin/python3`, `install -o root`, wrapper
  `exec /usr/bin/python3 -I -s …/_run_helper.py` (sys.path set explicitly).
- File: `scripts/install-polkit-policy.sh`.

### F4 High — polkit actions indistinguishable

- Before: 12 actions shared `exec.path`, no `exec.argv1`; shared
  `auth_admin_keep` window.
- Fix: per-action `exec.argv1` = helper verb; `vpn-*`, `toggle-firewall`,
  `reset-stack` → `auth_admin` (no keep); contract test enforces both.
- File: `assets/com.kayab.netmedic.policy`.

### F5 High — stale helper / moved tag

- Before: installed helper `__version__ = "1.5.0"` stub, daemon never checked;
  `v1.6.0` retagged across commits.
- Fix: `HELPER_VERSION = "1.6.1"`, helper `--version`, daemon refuses mismatch
  with re-run hint. Tag `v1.6.1` to be created after VM checks; add `v*`
  tag ruleset (block update/delete).
- Files: `helper_verbs.py`, `helper_main.py`, `system.py`, installer.

### M1 Medium — legacy downgrade gated to tests

- `allow_legacy_elevation()` and `NETMEDIC_HELPER_PATH` now require
  `NETMEDIC_TEST_MODE=1`; no `PATH` lookup in production.
- File: `netmedic/netmedic/config.py`.

## Mitigation / Detection

- Upgrade to v1.6.1 and re-run `./scripts/install-polkit-policy.sh`.
- Workaround: remove `/usr/share/polkit-1/actions/com.kayab.netmedic.policy`.
- Detect: `journalctl -t netmedic-audit | grep vpn-run-script`;
  `/usr/libexec/netmedic/helper --version` must print `1.6.1`;
  `pkaction --verbose` must show distinct `argv1` per action.

## Verification (this branch)

- `PYTHONPATH=netmedic venv/bin/python -m pytest tests/ -q -k "not netns and not golden"`: 466 passed.
- `ruff check netmedic/ tests/`: clean.
- `mypy --strict helper_verbs.py helper_main.py`: clean.
- Coverage total 85%; `helper_verbs.py` 90%, `helper_main.py` 70% (M9 follow-up).
- VM still required: `head -6 /usr/libexec/netmedic/helper`,
  `findmnt -no OPTIONS /run`, `journalctl -t polkitd` (two verbs),
  `git ls-remote --tags origin`.

## Timeline

- 2026-09-26: audit findings confirmed at `e3be5eb` (dry-run repro).
- 2026-09-28: F1–F5+M1 implemented + regression tests, 466 passing.
- Next: VM verification → tag `v1.6.1` → GitHub release + advisory → M2.
