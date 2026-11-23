# Changelog

All notable changes to NetMedic Linux are documented here.

## [Unreleased]

### Added

- **LUCP Phase 2b — portable headless installer.** `install.sh` now accepts
  `--headless` / `--profile=desktop|headless`. The headless profile installs
  only the Python core, skips GTK/NetworkManager/Polkit/helper and runs the
  core test subset. Unknown distributions no longer abort solely because the
  package manager is unrecognized; `scripts/check-deps.sh` reports Python,
  optional tools, GUI and helper status by profile without making optional
  capabilities mandatory.
- **LUCP Phase 2a — optional GUI package.** `netmedic` no longer requires
  PyGObject at runtime: `dependencies = []` and GTK lives in the `gui` extra
  (`pip install 'netmedic[gui]'`). The diagnostic core and `--headless` mode
  install and run with `--no-deps` on hosts without GTK. Starting the GUI
  without PyGObject now prints an actionable install hint instead of a
  traceback. CI adds a headless-core job without GTK and checks wheel/sdist
  metadata for mandatory dependencies.
- **LUCP Phase 1 — capability registry and readiness split.** `--status` and
  `--status-json` now expose `schema_version`, `scope` (current network
  namespace plus a conservative container hint) and `capabilities` with
  separate `availability` (`AVAILABLE`/`UNAVAILABLE`/`UNKNOWN`) and `outcome`.
  `core_ready` depends only on a supported Python runtime and a `0700` state
  directory; `privileged_ready` covers helper, `pkexec` and all Kayab Polkit
  actions. `production_ready` is a deprecated alias of `core_ready`.
  `--require-privileged` exits 1 when L2 is unavailable. `nmcli`, `ip`, `curl`
  and the other tools are reported as capabilities, not core failures.

### Fixed

- **Polkit per-verb wrappers (post-1.9.0).** Ubuntu 22.04/24.04 ship polkit
  0.105, whose `pkexec` selects the action by `org.freedesktop.policykit.exec.path`
  only and ignores `exec.argv1`. With one shared helper path, every action
  collapsed into the first enumerated one (`renew-ip`), so `change-dns` and
  `restart-adapter` inherited `auth_admin_keep` instead of re-prompting.
  `install-polkit-policy.sh` now installs one root-owned `helper-<verb>`
  wrapper per action and the generated policy annotates each action with that
  unique path; `exec.argv1` is gone. Reinstall helper and policy after
  updating. Documentation in `docs/IPC_API.md`, `docs/PRIVILEGED_HELPER.md`,
  `docs/THREAT_MODEL.md` and `docs/VPN_CONTRACT.md` reflects the new contract.
- **Release build no longer pins an unavailable package.** Removed the
  `cyclonedx-bom==8.6.2` pin (the version does not exist on PyPI); the SBOM
  step was already best-effort and guarded by a module probe.

## [1.9.0] — 2026-11-18

Release lines up the application, package and privileged helper at **1.9.0**.
The daemon refuses a helper whose `HELPER_VERSION` differs, so the helper and
policy must be reinstalled (see Breaking changes).

### Security

- **F1 — helper hardening (L1/L3/L4):** elevation uses the fixed, validated
  `/usr/bin/pkexec` (root-owned, regular, executable) instead of `PATH`
  resolution. Root journal records carry a validated `pkexec_uid` and a
  control-character-flattened message; the unused alternate helper path is
  removed. The installer reads `HELPER_VERSION` from an absolute path with the
  validated `/usr/bin/python3`.
- **F2 — vendored VPN installer:** the Angristan installer is vendored and
  pinned by SHA256 at the helper (`PINNED_VPN_INSTALL_SHA256`); no runtime
  download, no caller-supplied path/hash, root reads `O_NOFOLLOW`, verifies the
  bytes actually read and executes a root-owned staged copy in `/run/netmedic`.
- **F3/F3b/F3c — typed VPN verbs and artifact delivery:** `vpn-run-script` and
  the caller env dictionary are gone. `vpn-install`, `vpn-add-client` and
  `vpn-revoke-client` accept only validated parameters and fixed subcommands.
  The `.ovpn` artifact is sealed in `/run/netmedic`, returned to the daemon and
  written `0600 O_EXCL|O_NOFOLLOW` under `~/.local/share/netmedic/vpn-clients/`
  (0700); `artifact` is redacted from logs/audit. AI confirmation is
  fail-closed when no invocable dialog exists.
- **F5 — no keep window for high-risk verbs:** `change-dns` and
  `restart-adapter` use `auth_admin`, so polkit re-prompts on every invocation.
  `flush-dns` and `renew-ip` keep `auth_admin_keep`.
- **F6/F6.1 — recoverability:** `change-dns` snapshots both `ipv4.dns` and
  `ipv4.ignore-auto-dns` (fail-closed), applies the exact dry-run argv under one
  monotonic deadline with a reserved rollback budget, restores the config first
  on failure and reports `config=unchanged|reverted|not-restored` without
  claiming unconfirmed reactivation. `restart-adapter` retries `up` once and
  reports IFF_UP plus carrier from sysfs.
- **F6.2 — truthful restart-adapter:** the daemon no longer polls
  `ip link`/operstate nor accepts the `"UP"` substring inside
  `<NO-CARRIER,...,UP> state DOWN`; it propagates the helper's `ok`, message and
  details verbatim.
- **Supply chain:** Pillow 13.0.0 and setuptools 84.2.1 in the hash-pinned
  `requirements.lock`; `pip-audit` is blocking in CI. The GGUF model SHA256 is
  hardcoded for the optional AI pilot (`netmedic_ai` remains outside the release
  supply chain until its own hash-pinned lock lands).

### Breaking changes

- **`vpn-run-script` is removed.** Automation must use `vpn-install`,
  `vpn-add-client` or `vpn-revoke-client`; the helper rejects caller-supplied
  script paths, hashes and environment dictionaries.
- **Polkit policy changed.** The three VPN verbs have distinct `exec.argv1`
  values and the two high-risk verbs no longer use `auth_admin_keep`. The
  installed XML must be regenerated from this release.
- **The daemon requires a helper with the same version (1.9.0).** A stale
  helper fails with `helper-missing`/version mismatch instead of running.
  After updating, reinstall the helper and policy and restart the daemon:

  ```bash
  sudo ./scripts/install-polkit-policy.sh
  systemctl --user restart netmedic-headless.service   # headless/MCP
  # GUI: close and reopen `netmedic`
  ```

### Compatibility

- Python 3.13 joins the CI matrix in both elevation modes. The supported range
  remains **3.10–3.13** (`requires-python = ">=3.10,<3.14"`), and
  `scripts/check-deps.sh` warns above 3.13.
- The optional AI pilot remains **experimental and outside the supported
  1.9.0 surface**. Enabling it requires a hash-pinned AI lock and an
  admin-owned, user-non-writable model directory; see
  `docs/AI_SUPPLY_CHAIN.md` and issue #62.

### Behavior changes

- `restart-adapter` details no longer include the interface IP or a fabricated
  operstate. They are the helper's sysfs facts
  (`iff_up=...; carrier=...`), and `ok` equals the helper's verdict.
- `change-dns` restores `ipv4.dns` and `ipv4.ignore-auto-dns` when the apply or
  `con up` fails, and says whether reactivation was confirmed.
- `change-dns` and `restart-adapter` prompt for authorization every time.
- `CommandResult` exposes the helper's `message`/`details`; the legacy `stdout`
  details payload is preserved for existing callers.

## 1.9.0 implementation record — F6.2 restart-adapter truth end-to-end

### Fixed
- `restart_adapter` no longer polls `ip link`/operstate for up to 5 s nor
  accepts `"UP"` inside `<NO-CARRIER,...,UP> state DOWN`. It reports the
  helper's own `ok`, message (`carrier detected`, `no carrier`,
  `carrier unknown`, `not UP after restart`) and details
  (`iff_up=...; carrier=...`) verbatim, so loopback and carrier-less links
  show the real verdict.
- `CommandResult` now carries the helper's `message` and `details`; the legacy
  `stdout` details payload remains for existing callers.
- F6.2 itself did not change the helper contract (it was 1.8.5 at the time);
  the 1.9.0 release aligns `HELPER_VERSION` with the application version.

## 1.9.0 implementation record — H4 supply-chain lock refresh

### Security
- `requirements.lock`: Pillow 12.3.0 -> 13.0.0 (CVE-2026-128066) and
  setuptools 84.0.0 -> 84.2.1 (GHSA-xmj3-9gf7-h52w). The cp312 manylinux
  wheel hashes were re-verified with `pip download`.
- `pip-audit -r requirements.lock` is green on Python 3.12.

### Changed
- Static guard `test_lock_build_tools_above_cve_floor` keeps both build
  tools above the known-vulnerable floor.

## 1.9.0 implementation record — F6.1 shared deadline and veracious rollback

### Security
- `change-dns` uses one monotonic deadline for the whole verb: every command
  receives only the time left in its phase, and `R = min(10s, total/3)` is
  reserved for rollback. The daemon still waits `timeout + IPC margin`.
- `restart-adapter` makes a final `up` attempt after a timeout and reports
  IFF_UP plus carrier from sysfs (`unknown` carrier is not an error).
- Rollback results are veracious: `config=unchanged|reverted|not-restored`;
  a reverted config does not claim reactivation; a failed rollback includes
  the exact manual command.
- `VerbPlan.params` carries validated connection/server/interface; the executor
  no longer slices argv, so dry-run and execution share one source of truth.

### Changed
- `HELPER_VERSION` 1.8.4 -> 1.8.5.
- `--timeout` help now documents it as the total verb deadline (not per command).

## 1.9.0 implementation record — F3c cierres (hotfix)

### Security
- AI pilot confirmation is now fail-closed: disruptive actions without an
  invocable dialog are not executed (A).
- README no longer claims IPC token/`confirmed` as root protection (B).
- `SECURITY.md`: only 1.8.x supported; <=1.6.0 affected (C).
- `COMPLIANCE_MATRIX.md`: ISO control column + honest status; model hash test
  and MCP gate test cited (D).
- mypy CI command verified clean (13 modules). H4 (`pip-audit` against the
  lock) was open at the time and is closed by the H4 lock refresh entry above.

## 1.9.0 implementation record — F7 AI supply chain (partial)

### Security
- Model GGUF hash hardcoded in `netmedic_ai/pilot.py` (`MODEL_SHA256`); verified
  at load. The `.sum` sidecar is no longer trusted.
- `build_binary.sh` now requires `pillow>=13.0.0`.

### Changed
- `netmedic_ai` declared out of the release supply chain until
  `netmedic_ai/requirements.lock` (with hashes) lands; generation script added.
- `docs/AI_SUPPLY_CHAIN.md` documents the lock workflow.

## 1.9.0 implementation record — F6 recoverability of change-dns/restart-adapter

### Security
- `change-dns` now snapshots both `ipv4.dns` and `ipv4.ignore-auto-dns` before
  modifying; aborts (fail-closed) if the snapshot is invalid. On failure it
  restores the config first, then `con up` best-effort, with a reserved rollback
  budget and a veracious result (applied / reverted / rollback FAILED).
- `restart-adapter` retries `up` and reports final state via IFF_UP (no false
  "unknown is failure").

### Changed
- `HELPER_VERSION` 1.8.3 -> 1.8.4.
- `docs/RECOVERABILITY_DESIGN.md` (approved with corrections).

## 1.9.0 implementation record — F5 keep_auth for high-risk verbs

### Security
- `change-dns` and `restart-adapter` now use `auth_admin` (no keep window):
  polkit re-prompts on every invocation. `flush-dns` and `renew-ip` keep
  `auth_admin_keep`.
- GUI `on_restart_adapter` confirmation now names the detected interface.

### Changed
- Policy XML regenerated (allow_active auth_admin for the two high-risk verbs).

## 1.9.0 implementation record — F3 typed VPN verbs on the vendored CLI

### Security
- **No caller env dict (H3):** `VPN_ALLOWED_ENV_KEYS` and `_validate_vpn_script_env` are
  gone. `vpn-run-script` is removed; replaced by `vpn-install`, `vpn-add-client`,
  `vpn-revoke-client`, each with its own `exec.argv1`. The helper builds
  `/bin/bash <staged> <subcommand> <flags>` from validated parameters only; the
  caller sends no path, hash, or env.
- **Typed argv:** client name via `validate_client_name`; port 1-65535; protocol
  `udp`/`tcp`; dns in the closed provider enum. `vpn-revoke-client` always passes
  `--force`; `uninstall` and `renew` are not exposed.
- **Artifact delivery (F4):** `vpn-add-client` passes `--output <sealed path>` in
  `/run/netmedic`; the helper reads the `.ovpn` with `O_NOFOLLOW` + `S_ISREG` +
  size cap, returns it as the `artifact` JSON field, and deletes the temp file.
  The daemon writes it with `0600 O_EXCL|O_NOFOLLOW` under
  `~/.local/share/netmedic/vpn-clients/` (0700). Root never writes `$HOME`.
  `artifact` is redacted in `audit_log`.

### Changed
- `HELPER_VERSION` 1.8.2 → 1.8.3.
- Policy XML regenerated (`vpn-install`, `vpn-add-client`, `vpn-revoke-client`
  distinct `exec.argv1`); uniqueness test added.
- `docs/VPN_CONTRACT.md` is the source of truth for the mapping.

## 1.9.0 implementation record — F2 vendored VPN installer

### Security
- **Supply chain (F2):** the Angristan installer is vendored at
  `netmedic/netmedic/data/vpn/openvpn-install.sh` (commit
  `9c966d4d043a0340503d6df577aa174a68468aed`, SHA256
  `e0ac8731…`) and installed root-owned as
  `/usr/lib/netmedic/scripts/openvpn-install.sh`. The previous runtime
  `curl` download and the user-writable `~/.local/share/netmedic/operators`
  copy are gone.
- **Single trust anchor:** `helper_verbs.PINNED_VPN_INSTALL_SHA256` is now
  the SHA256 of the vendored bytes. The old value (`65c3b53f…`) did not
  match the pinned commit, so installs could never pass integrity; a
  guardian test recomputes the repo file hash to keep all three values
  (file, pin, provenance) in sync.
- **Caller path/hash removed:** `plan_verb("vpn-run-script")` accepts only
  `script_id`; `script` and `expected_sha256` are rejected. The helper
  resolves the id to a fixed path, reads it with `O_NOFOLLOW`, rejects
  non-regular/foreign-owned/writable/oversized files, verifies the pin over
  the bytes actually read, stages a root-owned copy in `/run/netmedic`
  (0700) and executes only that copy. Env pairs are re-validated at the root
  side even if the planner is bypassed in-process.
- The daemon no longer hashes, seals or downloads anything; `check_status`,
  `start_service` and `restart_service` use `/etc/openvpn/server/server.conf`
  as the installed marker instead of the user-space script copy.

### Changed
- `HELPER_VERSION` 1.8.1 → 1.8.2 (helper code and its trust anchor changed).

### Known limitations
- **VPN no funcional hasta Fase 2b/3.** La supply chain está cerrada (instalador
  vendorizado y pinneado), pero la interfaz env/menú que NetMedic envía al script no coincide
  con el CLI no interactivo del commit pineado (`DNS=3` exige nombre de proveedor; el menú de
  revocación es 3, no 2). Las operaciones install/add/revoke fallan hasta que la Fase 3
  construya argv sobre `install`/`client add`/`client revoke`. No etiquetar como "VPN arreglado".
- `install-polkit-policy.sh` and the Debian rules install the vendored
  script; `pyproject.toml` ships it as package data. Re-run the policy
  installer so the system copy matches the new pin.
- The `env` channel is still transitional: the pinned commit's non-interactive
  CLI (`install`, `client add`, `client revoke`) replaces it in F3.

## 1.9.0 implementation record — F1 helper hardening

### Security
- **L1 (pkexec resolution):** elevation now uses the fixed
  `/usr/bin/pkexec` constant and validates it as a root-owned, executable
  regular file before use, instead of `shutil.which("pkexec")`. A hostile
  `pkexec` earlier in `PATH` can no longer capture the admin password. Both
  the helper path and the legacy test path use the validated binary; refusal
  surfaces as exit 127.
- **L3 (root journal):** each helper record now carries a validated
  `pkexec_uid` (decimal, else `unknown`) and a control-character-flattened,
  length-capped message, so a crafted stderr line cannot inject a second
  record. Verb arguments (including env secrets) are never serialized.
- **Dead path removed:** `Config.SYSTEM_HELPER_ALT_PATH`
  (`/usr/lib/netmedic/helper`) is gone. No in-tree installer ever wrote it
  (the policy script and the Debian rules both use
  `/usr/libexec/netmedic/helper`), so the fallback only widened the trusted
  path surface. `status.py` and `docs/MANUAL.md` describe the single path.
- **L4 (installer):** `install-polkit-policy.sh` reads `HELPER_VERSION` from an
  absolute path via the validated `/usr/bin/python3`, so it works from any
  working directory.

### Changed
- `HELPER_VERSION` 1.8.1 → 1.8.2: helper code changed, so stale system
  installs are refused until the installer is re-run. The application version
  stayed 1.8.1 until the 1.9.0 release.
- Added `docs/VM_CHECKLIST.md` with the F1 items that require a real VM.

## 1.9.0 implementation record — F0 test/CI hygiene

### Fixed
- **F0 (repo layout):** `pytest.ini` now sets `pythonpath = netmedic`. With a
  plain `pip install -e netmedic/`, `python -m pytest tests/` from the repo
  root imported the root-level `netmedic/` directory as a namespace package
  and shadowed the real one (`ImportError: cannot import name '__version__'`).
  Only `editable_mode=strict` or an explicit `PYTHONPATH` worked before.
  Guarded by `tests/test_pytest_layout.py`; verified green under both normal
  and strict editable installs.

### Added
- **F0 (CI):** weekly `schedule` trigger with a dedicated
  `supply-chain-audit` job that runs `pip-audit` against `requirements.lock`.
  All push/PR jobs explicitly skip on `schedule`; the new job keeps SHA-pinned
  actions and `contents: read`.

## 1.9.0 implementation record — N1–N3 follow-ups (post-v1.8.1)

### Fixed
- **N3:** `validate_iface` rejects `"."`/`".."` explicitly (charset regex
  let them through; the kernel is no longer the backstop).
- **N1:** MCP `smart_repair()` drives headless `run_smart_repair`
  (diagnose → conditional flush/renew → verify → delta) instead of a
  manual flush+renew chain; verdict rendered as human text.
- **N2:** `plan_verb` F(48) → per-verb planner table (worst B);
  `run_smart_repair` F(61) → phase functions (worst C); radon target
  (nothing above rank C) met. Includes the N3 + N1 merges.

## 1.9.0 implementation record — M8 architecture + M9 typing + M10 governance

### Changed
- **M10 (governance):** `git gc` (44 MB loose → 22 MB packed; nothing vendored to purge); docs drift fixed (PRIVILEGED_HELPER acceptance boxes checked with evidence, README 1.8.0/counts/links, DEVELOPMENT counts + 13-module mypy + glob warning, debian/changelog 1.8.0 entry, netmedic_ai version/requires-python sync; release-notes history left intact); ruff S603/S607/S110/S112/S108 moved from global ignore to 56 per-line `noqa` with reasons (S101/E501 stay global: test asserts + docs lines); new `docs/SETTINGS_CHECKLIST.md` for what code can't enforce.
- **M9 (typing that actually runs):** probe-proven that `[mypy-netmedic.*] ignore_errors` shadowed every specific strict section in mypy 2.x — all "strict" CI runs silently checked nothing. Fixed with `mypy_path` + `explicit_package_bases`; glob deleted and banned by guardian test; 17 unstrict followers moved to explicit per-file ratchet-queue sections; `config`/`polkit_auth` now truly strict (CI's "10 modules" claim made real); `helper_main`/`system`/`validators` strict (Popen generics, `int`→`float` timeouts, `_reraise_as_verb` annotation, gi `import-untyped` exemption). CI Typecheck covers 13 modules; per-file coverage gates (helper_main 70, system 76, polkit_auth 82) run separately so ui.py can't mask the root path; 6 GTK test files skip cleanly without gi (proven in a gi-free venv).
- **M8.5 (repair extraction):** Smart Repair orchestration moved from `ui.py:490-664` to headless `netmedic/repair.py` (`run_smart_repair` + injected `RepairDeps`/`RepairCallbacks`); `on_smart_repair` is a thin `run_async_task` wrapper, `_wait_for_settle`/`_default_iface_for_repair` delegate. Headless/MCP/AI paths can now drive the flow; 7 new GTK-free tests. Minor: dead `gateway and None` placeholder dropped; non-dict diag data handled defensively; `is_healthy` fallback now code-based (no shim read).
- **M8.4 (shim narrowing):** `NetResult.success` warns on every external read — the filename ("tests") and inline-comment exemptions are gone, so tests run production behavior. `_result_payload` splits test doubles (`isinstance`: legacy truthiness, no shim touch) from real results (code-only). ~100 test asserts migrated `success` → `code in (OK, EXECUTED)`; `CommandResult.success` untouched (legitimate low-level API); marker ratchet pinned to 0 and the guard no longer honors markers.
- **M8.3 (dispatcher table):** the 18-`if` chain in `create_action_dispatcher` is now a module-level verb→handler table over a frozen `_DispatchCtx` (medic/session/wifi/vpn + request fields); gates (shape, peer, auth, params, slot, audit-intent), error and slot-release paths unchanged. Drive-by fix: pre-existing order-dependent failure from the M3 global denial limiter leaking across test files — conftest now resets it autouse.
- **M8.2 (policy generator):** `scripts/generate_policy.py` renders `assets/com.kayab.netmedic.policy` from the table (`--write` regenerates, `--check` fails on drift, wired into CI); `ActionSpec.message` holds the 12 auth prompts; `test_generated_policy_matches` pins asset==render; `test_registry_keys_match_action_table` pins VERBS.md identity keys to the table; fixed stale `vpn-list-clients` header in VERBS.md §3.4. (Caught during implementation: `--` is illegal inside XML comments — generator text avoids it.)
- **M8.1 (ActionSpec table):** `action_catalog.ACTIONS` (21 rows: 12 privileged + 7 safe + 2 internal, with `keep_auth` retention flags) is now the single source; `PRIVILEGED/SAFE/DISRUPTIVE_ACTIONS`, `POLKIT_ACTION_IDS`, `IPC_TO_VERB` and `ALL_VERBS` are derived (legacy names kept as re-exports). The hardcoded 8-ID `no_keep_ids` list in the policy contract test is table-driven. Installer ships `action_catalog.py` root-side (helper runs `-I`). Guardian: new `test_action_table_self_consistent`.

## [1.8.1] — 2026-10-01 (tag `v1.8.1`)

M10 governance + dependency SHA pins + M2 test hardening. Suite 546.

- M10: `git gc`, docs drift (6 files), ruff globals → 56 per-line `noqa`,
  `docs/SETTINGS_CHECKLIST.md`.
- Maintenance: 5 Dependabot majors adopted as API-resolved SHAs (bot PRs
  #9–13 closed under the M6 floating-tag policy); M2 orphan-detection
  tests hardened from fixed sleeps to polling (flaked under full-suite load).

## [1.8.0] — 2026-09-30 (tag `v1.8.0`)

M8 architecture + M9 typing. Suite 466 → 546.

- M8.1–M8.5: ActionSpec table, generated policy XML, dispatcher table,
  narrowed success shim, headless `repair.py` service (details under
  [Unreleased] below, kept as the implementation record).
- M9: strict typing made real (mypy 2.x glob shadowing fixed),
  `helper_main`/`system`/`validators` strict, per-path coverage gates,
  hermetic gi skips, glob-ban guardian.

## [1.7.0] — 2026-09-29 (tag `v1.7.0`)

Audit-remediation milestone: every critical, high and medium finding
closed. Suite 466 → 533.

- v1.6.1: F1–F5 + M1 (privilege boundary).
- v1.6.2: M2–M4 (deadlines, audit, validators).
- v1.6.3: M7 (packaging, Python 3.13, uninstall).
- v1.6.4: M6 (supply chain, provenance).
- v1.7.0: M5 (AI pilot).

## 1.9.0 implementation record — M2 and follow-ups (post-v1.6.1)

### Fixed
- **M2 (timeout enforcement):** helper `_run_argv` now uses Popen + `killpg` instead of `subprocess.run(timeout)` (which killed only the direct child). New `execute_with_deadline()` + `DeadlineResult` (no signals; SIGALRM is not thread-safe). Daemon waits helper deadline + 5s IPC margin instead of firing first; EPERM-after-setuid documented as expected. `IPCBridge.stop()` no longer joins behind in-flight elevated calls.

## 1.9.0 implementation record — v1.6.1 candidate

### Security (audit F1-F5 + M1)
- **F1 (vpn-run-script generic root):** caller hash no longer trusted — must equal root pin `PINNED_VPN_INSTALL_SHA256`; `script_id` allowlist (`openvpn-install`); env allowlist (11 Angristan vars only, no `LD_*`/`PATH`/`BASH_ENV`); helper executes with `env -i PATH=fixed` + `/bin/bash` (noexec-safe) and re-checks pin even on in-process calls.
- **F2 (vpn-list traversal):** `index_path` param removed; fixed-path `O_NOFOLLOW` Python read with 1 MiB cap (no `cat`, no caller path).
- **F3 (interpreter hijack):** installer pins `/usr/bin/python3`, uses `install -o root`, wrapper runs `-I -s` via root-owned `_run_helper.py` (no `PYTHONPATH`, no venv).
- **F4 (polkit granularity):** all 12 actions annotate `exec.argv1` with helper verb; `vpn-*`/`toggle-firewall`/`reset-stack` use `auth_admin` (no keep).
- **F5 (stale helper):** daemon refuses version-mismatched helper (`--version` vs `HELPER_VERSION=1.6.1`); installer syncs version from source.
- **M1 (downgrade):** legacy elevation and `NETMEDIC_HELPER_PATH` honored only in `NETMEDIC_TEST_MODE=1`; no `PATH` lookup in production.
- **M3 (audit hardening):** `_append_entry` uses `O_APPEND|O_CREAT|O_NOFOLLOW` with 0600 at creation + fsync (symlinks refused); denials rate-limited (1/5s/action, suppressed count reported, intents never limited); helper emits one root-side journal record per verb via stdlib syslog.
- **M4 (validator unification):** new `netmedic/validators.py` (stdlib-only, shipped to the helper) replaces four drifted DNS-regex copies and three iface-name copies; `helper_verbs`, `network.py`, `ipc_actions.py` and `netmedic_ai/param_validation.py` (guarded import + strict fallback) all delegate to it. DNS via `ipaddress` (rejects `"1.1.1.1\n"` and leading-zero octets); ifaces reject a leading `-` and cap at 15 chars; conn names reject a leading `-`. Breaking in the strict direction only; property test updated to the new contract.
- **M5 (AI pilot):** network-state block gets the same control-char scrubbing as `user_request`, bounded to 1500 chars / 64 keys / 120-char strings so state + request + system prompt fit `n_ctx=2048` with `max_tokens=128`; `infer_intent` serialized on an instance lock and `_get_pilot` double-checked (llama_cpp is not thread-safe; 4 IPC workers shared one instance and could double-load 950 MB); model dir resolution order `NETMEDIC_AI_MODEL_DIR` → package data → `sys._MEIPASS` → checkout legacy (fixes installed/PyInstaller layouts); `.sum`-is-corruption-not-tamper-evidence documented; `install.sh` GPU flags `-DLLAMA_CUBLAS/-DLLAMA_VULKAN` → `-DGGML_CUDA/-DGGML_VULKAN` (old names silently built CPU-only).
- **M6 (supply chain):** `requirements.lock` hash-pinned for `--require-hashes` (cp312 manylinux scope; PyGObject stays apt-sourced); `Dockerfile.build` installs only from the lock; all GitHub Actions pinned by SHA; workflows default `contents: read`, write token only in the `publish` job behind the `release` environment; SLSA provenance via `attest-build-provenance` (GPG kept until verifiers migrate); `pip-audit` blocking against the lock (was `|| echo` on the CI env); Dependabot pip entries point at `/netmedic` and `/netmedic_ai`.
- **M7 (packaging/installer):** `requires-python` ceiling `<3.13` → `<3.14` (3.13 verified; was blocking dev installs); Pillow dropped from runtime deps (dev-time icon script only; build image pins its own); `install.sh` now runs `install-polkit-policy.sh` and fails loudly otherwise (was policy-XML-only → runtime 127); dev tools pinned to `requirements-dev.lock`; `--yes` is truly non-interactive; Fedora package `policykit` → `polkit`; unsupported distros exit 1; launcher `Exec` quoted for paths with spaces; new `scripts/uninstall.sh` covering every install artifact; package version 1.6.0 → 1.6.2. `editable_mode=strict` kept (guardian test + rc2 fix depend on it).

### Fixed relative to 1.6.0
- **C-1 (same-UID script swap):** helper re-stages verified scripts into root-owned `/run/netmedic` (0700, unique per invocation), re-hashes at the exec path, unlinks after. 1.6.0 hashed then exec'd a user-owned path.
- **B-4/C-16 (fail-closed audit):** privileged intent is recorded before execution; unwritable audit log refuses the action ("Audit unavailable") instead of executing unaudited.
- **B-1 (portal misdiagnosis):** all-green verdicts are re-verified via the 204-endpoint check — TCP-behind-portal now reports PARTIAL, not healthy. `NETMEDIC_PORTAL_URL` override added.
- **H-2 (torn token reads):** secret files via tmp+rename with 0600 at creation.
- **C-9 (timeout containment):** `run_elevated` converts escaped timeouts to structured results; real-hang wall-clock test added.
- **C-8 (helper backdoor):** `NETMEDIC_HELPER_EXECUTE` honored only with `NETMEDIC_TEST_MODE=1`.
- AI confirmation dialogs now show the resolved verb **and** concrete args.
- Notebook page fill and the log view no longer follow a light gtk-theme: the page `Gtk.Stack` and the text-view `text` node are owned by the dark stylesheet.
- A closed AI palette no longer keeps a full-width invisible overlay over the notebook tab strip, which swallowed clicks on Infrastructure.
- Renew IP Address is a destructive (red) control again. The flag was dropped when its accessibility description was added.

## [1.6.0] — 2026-09-25 — final (tag `v1.6.0`)

### Breaking
- **Python `>=3.10,<3.13` (was `>=3.8`):** intentional per internal-IT Narrow+Pin (Ubuntu 22.04/24.04, CI 3.10/3.11/3.12). Affected: Ubuntu 20.04 (3.8), Debian 11 (3.9) — pin to `v1.5.x` for these platforms (security fixes only). Rationale: Python 3.8 EOL Oct 2024, `pillow>=10`/`PyGObject>=3.42` pins, `X|Y` typing + `match` readiness, matrix cost. Not a SemVer major: pre-1.6.0-final RC series, documented here + `README.md` + `docs/RELEASE_NOTES.md`.

### Added
- P1 coverage: `runtime.py` 100% (`tests/test_runtime_lifecycle.py`), `ui.py` 98% (`tests/test_ui_flows.py`) — total 77%→83%, CI gate 70→75
- Property tests (`tests/test_properties.py`, Hypothesis): framing roundtrip, token uniqueness/shape, catalog/schema consistency, verb totality, redaction shape
- Mutation-tested `ipc_security` + `helper_verbs` (targeted mutants, 15/16 killed = 94%; 1 equivalent mutant documented in code) + dispatch-level peer/empty-token tests
- `mypy.ini`: strict on 10 modules (ipc_security/helper_verbs/action_catalog/models/ipc_bridge/ipc_actions/runtime/lifecycle/config/polkit_auth); `Dockerfile.build` reproducible image + CI `container-build` job; `setup.cfg` mutmut scope

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