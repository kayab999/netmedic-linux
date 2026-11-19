#!/usr/bin/env python3
"""Read-only evidence collector for the 1.9.x VM checklist.

Run from the repository root on the target VM, recording the whole session:

    script -a vm-evidence.log
    python3 scripts/runbook_vm_evidence.py

The script validates the installed helper, policy, pkexec, the vendored VPN
installer hash and the fixed-verb dry-runs. It never performs destructive
actions: helper invocations use `--dry-run`, which prints the plan without
running it, and the manual blocks for F5/F6.1/F6.2/F2-F3 are printed for the
operator to execute and paste under the matching item in docs/VM_CHECKLIST.md.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shlex
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "netmedic"))

# Import after injecting the repo on sys.path; the repo modules are the source
# of truth for the helper version, verbs and VPN pin.
from netmedic.action_catalog import (  # noqa: E402 (repo path injected above)
    POLKIT_ACTION_IDS,
    spec_for_ipc,
)
from netmedic.helper_verbs import (  # noqa: E402 (repo path injected above)
    HELPER_VERSION,
    PINNED_VPN_INSTALL_SHA256,
)

HELPER = Path("/usr/libexec/netmedic/helper")
PKEXEC = Path("/usr/bin/pkexec")
POLICY = Path("/usr/share/polkit-1/actions/com.kayab.netmedic.policy")
REPO_POLICY = ROOT / "assets" / "com.kayab.netmedic.policy"
VPN_SCRIPT = Path("/usr/lib/netmedic/scripts/openvpn-install.sh")
REPO_VPN_SCRIPT = ROOT / "netmedic" / "netmedic" / "data" / "vpn" / "openvpn-install.sh"
INSTALLED_HELPER_PKG = Path("/usr/lib/netmedic/netmedic")
REPO_HELPER_PKG = ROOT / "netmedic" / "netmedic"
HELPER_DIRS = (
    Path("/usr/libexec/netmedic"),
    Path("/usr/lib/netmedic"),
    Path("/usr/lib/netmedic/scripts"),
)
HELPER_MODULES = (
    "helper_verbs.py",
    "helper_main.py",
    "validators.py",
    "action_catalog.py",
)
KEEP_AUTH_POLKIT_IDS = frozenset(
    {
        "com.kayab.netmedic.flush-dns",
        "com.kayab.netmedic.renew-ip",
    }
)
RUN_DIR = Path("/run/netmedic")

FAILURES: list[str] = []
WARNINGS: list[str] = []


def _ok(message: str) -> None:
    print(f"PASS: {message}")


def _warn(message: str) -> None:
    print(f"WARN: {message}")
    WARNINGS.append(message)


def _fail(message: str) -> None:
    print(f"FAIL: {message}")
    FAILURES.append(message)


def _run(argv: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 (fixed absolute argv, no shell)
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_regular_root(path: Path, label: str) -> None:
    try:
        info = path.stat()
    except OSError as exc:
        _fail(f"{label} missing: {path} ({exc})")
        return
    if not stat.S_ISREG(info.st_mode):
        _fail(f"{label} is not a regular file: {path}")
    elif info.st_mode & 0o022:
        _fail(
            f"{label} is group/world writable: {path} "
            f"mode={info.st_mode & 0o777:04o}"
        )
    elif info.st_uid != 0:
        _fail(f"{label} is not root-owned: {path} (uid={info.st_uid})")
    elif not info.st_mode & 0o111:
        _fail(f"{label} is not executable: {path}")
    else:
        _ok(f"{label}: {path} root-owned regular executable mode={info.st_mode & 0o777:04o}")


def _check_root_dir(path: Path) -> None:
    try:
        info = path.stat()
    except OSError as exc:
        _fail(f"directory missing: {path} ({exc})")
        return
    if not stat.S_ISDIR(info.st_mode):
        _fail(f"not a directory: {path}")
    elif info.st_uid != 0 or info.st_gid != 0:
        _fail(f"directory is not root:root: {path} (uid={info.st_uid} gid={info.st_gid})")
    elif info.st_mode & 0o022:
        _fail(
            f"directory is group/world writable: {path} "
            f"mode={info.st_mode & 0o777:04o}"
        )
    else:
        _ok(f"directory root:root, not group/world writable: {path}")


def _check_helper_dirs() -> None:
    for directory in HELPER_DIRS:
        _check_root_dir(directory)


def _check_helper_modules() -> None:
    if not INSTALLED_HELPER_PKG.is_dir():
        _fail(f"installed helper package missing: {INSTALLED_HELPER_PKG}")
        return

    problems = 0
    for name in HELPER_MODULES:
        repo_file = REPO_HELPER_PKG / name
        installed_file = INSTALLED_HELPER_PKG / name
        if not repo_file.is_file():
            _fail(f"repo helper module missing: {repo_file}")
            problems += 1
            continue
        if not installed_file.is_file():
            _fail(f"installed helper module missing: {installed_file}")
            problems += 1
            continue
        repo_hash = _sha256(repo_file)
        installed_hash = _sha256(installed_file)
        if repo_hash != installed_hash:
            _fail(
                f"installed {name} hash {installed_hash} != repo {repo_hash}"
            )
            problems += 1

    expected = set(HELPER_MODULES) | {"__init__.py"}
    unexpected = sorted(
        entry.name
        for entry in INSTALLED_HELPER_PKG.glob("*.py")
        if entry.name not in expected
    )
    if unexpected:
        _fail(f"unexpected .py file(s) in {INSTALLED_HELPER_PKG}: {unexpected}")
        problems += 1

    if problems == 0:
        _ok(
            f"installed helper modules match repo "
            f"({len(HELPER_MODULES)} files, no extra .py)"
        )


def _read_repo_version() -> str:
    text = (ROOT / "netmedic" / "netmedic" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.M)
    return match.group(1) if match else "unknown"


def _read_pyproject_version() -> str:
    text = (ROOT / "netmedic" / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.M)
    return match.group(1) if match else "unknown"


def _check_versions() -> None:
    app = _read_repo_version()
    package = _read_pyproject_version()
    print(f"Versions: app={app} package={package} helper={HELPER_VERSION}")
    if app == package == HELPER_VERSION:
        _ok(f"app, package and helper versions agree ({app})")
    else:
        _fail(
            f"version mismatch: app={app} package={package} helper={HELPER_VERSION}"
        )


def _check_helper_version() -> None:
    result = _run([str(HELPER), "--version"])
    if result.returncode != 0:
        _fail(f"helper --version rc={result.returncode}: {result.stderr.strip()}")
        return
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        _fail(f"helper --version is not JSON: {exc}: {result.stdout!r}")
        return
    installed = str(payload.get("version") or "")
    if payload.get("ok") is not True:
        _fail(f"helper --version did not report ok: {payload}")
    elif installed != HELPER_VERSION:
        _fail(f"installed helper {installed!r} != daemon {HELPER_VERSION!r}")
    else:
        _ok(f"installed helper version matches daemon ({installed})")


def _check_pkexec() -> None:
    _check_regular_root(PKEXEC, "pkexec")


def _check_policy_hash() -> None:
    if not REPO_POLICY.is_file():
        _fail(f"repo polkit policy missing: {REPO_POLICY}")
        return
    if not POLICY.is_file():
        _fail(f"installed policy missing: {POLICY}")
        return
    repo_hash = _sha256(REPO_POLICY)
    installed_hash = _sha256(POLICY)
    if repo_hash != installed_hash:
        _fail(f"installed policy hash {installed_hash} != repo {repo_hash}")
    else:
        _ok("installed policy hash matches assets/com.kayab.netmedic.policy")


def _check_policy_actions() -> None:
    try:
        root = ET.parse(POLICY).getroot()  # noqa: S314 (root-owned local policy)
    except (OSError, ET.ParseError) as exc:
        _fail(f"cannot parse installed policy {POLICY}: {exc}")
        return

    nodes = {node.get("id"): node for node in root.findall("action")}
    seen_argv1: dict[str, str] = {}
    problems = 0
    for ipc_action, polkit_id in sorted(
        POLKIT_ACTION_IDS.items(), key=lambda item: item[1]
    ):
        spec = spec_for_ipc(ipc_action)
        node = nodes.get(polkit_id)
        if spec is None:
            _fail(f"{ipc_action}: no action_catalog spec for {polkit_id}")
            problems += 1
            continue
        if node is None:
            _fail(f"installed policy is missing action {polkit_id}")
            problems += 1
            continue

        annotate = {
            element.get("key"): (element.text or "")
            for element in node.findall("annotate")
        }
        exec_path = annotate.get("org.freedesktop.policykit.exec.path")
        exec_argv1 = annotate.get("org.freedesktop.policykit.exec.argv1")
        if exec_path != str(HELPER):
            _fail(f"{polkit_id}: exec.path {exec_path!r} != {str(HELPER)!r}")
            problems += 1
        if exec_argv1 != spec.helper_verb:
            _fail(
                f"{polkit_id}: exec.argv1 {exec_argv1!r} "
                f"!= catalog {spec.helper_verb!r}"
            )
            problems += 1
        elif exec_argv1 in seen_argv1:
            _fail(
                f"{polkit_id}: exec.argv1 {exec_argv1!r} "
                f"also used by {seen_argv1[exec_argv1]}"
            )
            problems += 1
        else:
            assert exec_argv1 is not None
            seen_argv1[exec_argv1] = polkit_id

        allow_active = (node.findtext("defaults/allow_active") or "").strip()
        wanted = "auth_admin_keep" if spec.keep_auth else "auth_admin"
        if allow_active != wanted:
            _fail(
                f"{polkit_id}: allow_active {allow_active!r} != {wanted!r}"
            )
            problems += 1

    configured_keep = frozenset(
        polkit_id
        for ipc_action, polkit_id in POLKIT_ACTION_IDS.items()
        if (spec := spec_for_ipc(ipc_action)) is not None and spec.keep_auth
    )
    if configured_keep != KEEP_AUTH_POLKIT_IDS:
        _fail(
            f"catalog keeps {sorted(configured_keep)}, "
            f"expected {sorted(KEEP_AUTH_POLKIT_IDS)}"
        )
        problems += 1

    if problems == 0:
        _ok(
            f"policy maps all {len(POLKIT_ACTION_IDS)} actions "
            f"to helper verbs with expected auth retention"
        )


def _check_policy() -> None:
    if not POLICY.is_file():
        _fail(f"polkit policy missing: {POLICY}")
        return
    info = POLICY.stat()
    if info.st_uid != 0:
        _fail(f"polkit policy is not root-owned: {POLICY} (uid={info.st_uid})")
    else:
        _ok(f"polkit policy present, root-owned, mode={info.st_mode & 0o777:04o}")

    _check_policy_hash()
    _check_policy_actions()
    _check_pkaction_listing()


def _check_pkaction_listing() -> None:
    """Validate the daemon-visible action list.

    polkit 0.105 (Ubuntu 22.04/24.04) returns rc=1 even on a successful
    enumeration, so the verdict must come from the listed action ids, not from
    the process exit status. An empty list still fails, including when pkaction
    itself is missing or cannot reach the authority.
    """
    result = _run(["pkaction"])
    listed = set(result.stdout.split())
    expected = set(POLKIT_ACTION_IDS.values())
    missing = sorted(expected - listed)
    if missing:
        detail = result.stderr.strip()
        suffix = f": {detail}" if detail else ""
        _fail(
            f"pkaction missing {len(missing)} NetMedic action(s): {missing}"
            f"{suffix}"
        )
    else:
        _ok(f"pkaction lists all {len(expected)} NetMedic actions")


def _check_vpn_installer() -> None:
    if not REPO_VPN_SCRIPT.is_file():
        _fail(f"vendored VPN installer missing from repo: {REPO_VPN_SCRIPT}")
    else:
        repo_hash = _sha256(REPO_VPN_SCRIPT)
        if repo_hash != PINNED_VPN_INSTALL_SHA256:
            _fail(f"repo VPN installer hash {repo_hash} != pin {PINNED_VPN_INSTALL_SHA256}")
        else:
            _ok("repo VPN installer hash matches the pin")

    if not VPN_SCRIPT.is_file():
        _fail(f"installed VPN installer missing: {VPN_SCRIPT}")
        return
    installed_hash = _sha256(VPN_SCRIPT)
    if installed_hash != PINNED_VPN_INSTALL_SHA256:
        _fail(
            f"installed VPN installer hash {installed_hash} != pin "
            f"{PINNED_VPN_INSTALL_SHA256}"
        )
    else:
        _ok("installed VPN installer hash matches the pin")


def _check_run_dir() -> None:
    if not RUN_DIR.exists():
        _warn(f"{RUN_DIR} not present (created on demand for VPN staging)")
        return
    info = RUN_DIR.stat()
    if info.st_uid != 0 or info.st_mode & 0o777 != 0o700:
        _fail(
            f"{RUN_DIR} must be root:root 0700, got uid={info.st_uid} "
            f"mode={info.st_mode & 0o777:04o}"
        )
    else:
        _ok(f"{RUN_DIR} is root:root 0700")


def _check_dry_runs() -> None:
    cases = [
        ("flush-dns", None),
        ("change-dns", {"connection": "netmedic-test", "server": "1.1.1.1"}),
        ("restart-adapter", {"iface": "lo"}),
        ("vpn-list", None),
        (
            "vpn-install",
            {
                "port": 1194,
                "protocol": "udp",
                "dns": "cloudflare",
                "client_ipv6": False,
                "client": "client",
            },
        ),
        ("vpn-add-client", {"name": "laptop"}),
        ("vpn-revoke-client", {"name": "laptop"}),
    ]
    for verb, params in cases:
        argv = [str(HELPER), verb, "--dry-run"]
        if params is not None:
            argv.extend(["--json", json.dumps(params, separators=(",", ":"))])
        print(f"dry-run argv: {shlex.join(argv)}")
        result = _run(argv)
        if result.returncode != 0:
            _fail(f"dry-run {verb} rc={result.returncode}: {result.stderr.strip()}")
            continue
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            _fail(f"dry-run {verb} is not JSON: {exc}")
            continue
        if payload.get("ok") is not True or payload.get("dry_run") is not True:
            _fail(f"dry-run {verb} did not report ok/dry_run: {payload}")
        else:
            commands = payload.get("commands") or []
            _ok(f"dry-run {verb} -> {commands}")


def _print_environment() -> None:
    print("=== NetMedic VM evidence (read-only) ===")
    print(f"Date:    {datetime.now().isoformat()}")
    print(f"Kernel:  {platform.platform()}")
    release = Path("/etc/os-release")
    if release.is_file():
        for line in release.read_text(encoding="utf-8").splitlines():
            if line.startswith(("PRETTY_NAME=", "VERSION_ID=")):
                print(f"OS:      {line}")
    git = _run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])
    if git.returncode == 0:
        print(f"Commit:  {git.stdout.strip()}")
    print()


def _print_manual_steps() -> None:
    text = """
=== Manual checks (execute separately, paste under docs/VM_CHECKLIST.md) ===

F1 install/journal:
  cd /tmp && sudo /path/to/netmedic_linux/scripts/install-polkit-policy.sh
  pkexec /usr/libexec/netmedic/helper-flush-dns --execute --json '{}'
  journalctl -t netmedic-helper -n 1 --no-pager

F2 tamper (run only after a VM snapshot; subshell + trap; records openvpn state before/after):
  (
    set -euo pipefail
    VPN=/usr/lib/netmedic/scripts/openvpn-install.sh
    PIN=__PIN__
    BAK=$(mktemp)
    ERR=$(mktemp)
    trap 'if test -s "$BAK"; then sudo cp -p "$BAK" "$VPN"; fi; rm -f "$BAK" "$ERR"' EXIT
    sudo cp -p "$VPN" "$BAK"
    if dpkg -l openvpn 2>/dev/null | grep -q '^ii'; then
      DPKG_BEFORE=installed
    else
      DPKG_BEFORE=absent
    fi
    echo '# tampered' | sudo tee -a "$VPN" >/dev/null

    set +e
    OUT=$(pkexec /usr/libexec/netmedic/helper-vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare"}' 2>"$ERR")
    RC=$?
    set -e
    DIAG="stdout=[$OUT] stderr=[$(cat "$ERR")]"

    if [ "$RC" -eq 3 ]; then
      if printf '%s' "$OUT" | grep -Fq '"ok":false' &&
         printf '%s' "$OUT" | grep -Fq 'Security abort: Script integrity failure.'; then
        echo 'PASS: helper rejected the tampered installer (rc=3, ok=false, integrity failure)'
      else
        echo "INCONCLUSIVE/FAIL: rc=$RC missing ok=false or the integrity message: $DIAG"
      fi
    else
      case "$RC" in
        126) echo "INCONCLUSIVE/FAIL: rc=$RC cancelado (autorización descartada), no rechazo por integridad: $DIAG" ;;
        127) echo "INCONCLUSIVE/FAIL: rc=$RC helper ausente o no autorizado: $DIAG" ;;
        2)   echo "INCONCLUSIVE/FAIL: rc=$RC args inválidos: $DIAG" ;;
        1)   echo "INCONCLUSIVE/FAIL: rc=$RC fallo operativo, no rechazo por integridad: $DIAG" ;;
        *)   echo "INCONCLUSIVE/FAIL: rc=$RC resultado inesperado: $DIAG" ;;
      esac
    fi

    sudo cp -p "$BAK" "$VPN"
    trap - EXIT
    rm -f "$BAK" "$ERR"
    if test "$(sha256sum "$VPN" | cut -d' ' -f1)" = "$PIN"; then
      echo 'PASS: VPN installer restored to the pin'
    else
      echo 'FAIL: VPN installer did not return to the pin'
    fi
    if dpkg -l openvpn 2>/dev/null | grep -q '^ii'; then
      DPKG_AFTER=installed
    else
      DPKG_AFTER=absent
    fi
    echo "openvpn package: before=$DPKG_BEFORE after=$DPKG_AFTER"
    if [ "$DPKG_BEFORE" != "$DPKG_AFTER" ]; then
      echo "FAIL: openvpn package state changed $DPKG_BEFORE -> $DPKG_AFTER"
    elif [ "$DPKG_AFTER" = "installed" ]; then
      echo 'WARN: openvpn was already installed; reinstall by the helper is undetectable on this VM'
    else
      echo 'PASS: openvpn package state unchanged (absent before and after)'
    fi
  )

F5 re-prompt (run each twice within 5 minutes):
  change-dns and restart-adapter must ask every time; flush-dns keeps the window.
  pkaction --action-id com.kayab.netmedic.change-dns --verbose | grep implicit
  pkaction --action-id com.kayab.netmedic.restart-adapter --verbose | grep implicit

F6.1 rollback:
  Force `nmcli con up` to fail on a test profile; compare
  `nmcli -g ipv4.dns,ipv4.ignore-auto-dns connection show <conn>` before/after.
  Repeat with a short timeout and confirm the rollback fits min(10s, timeout/3).

F6.2 restart-adapter:
  Cycle `lo` and an interface without carrier as root; confirm the GUI/CLI shows
  the helper message (carrier detected / no carrier / carrier unknown) and
  details `iff_up=...; carrier=...`. Confirm the daemon does not run `ip ... link`
  after the helper.

F2/F3 VPN end-to-end:
  pkexec /usr/libexec/netmedic/helper-vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare","client_ipv6":false,"client":"client"}'
  pkexec /usr/libexec/netmedic/helper-vpn-add-client --execute --json '{"name":"laptop"}'
  pkexec /usr/libexec/netmedic/helper-vpn-revoke-client --execute --json '{"name":"laptop"}'
  Check where `install --client` leaves the initial profile and whether
  `/root/client.ovpn` exists with a key that has no passphrase.

Do not mark any item complete without the literal output next to it.
"""
    print(text.replace("__PIN__", PINNED_VPN_INSTALL_SHA256))


def main() -> int:
    _print_environment()
    _check_versions()
    _check_regular_root(HELPER, "helper")
    _check_helper_version()
    _check_pkexec()
    _check_helper_dirs()
    _check_helper_modules()
    _check_policy()
    _check_vpn_installer()
    _check_run_dir()
    _check_dry_runs()
    _print_manual_steps()

    print(f"=== Summary: {len(FAILURES)} failure(s), {len(WARNINGS)} warning(s) ===")
    if FAILURES:
        for item in FAILURES:
            print(f"  FAIL: {item}")
        return 1
    print("Read-only evidence PASSED. Complete the manual blocks above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
