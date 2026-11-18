#!/usr/bin/env python3
"""Read-only evidence collector for the 1.9.x VM checklist.

Run from the repository root on the target VM, recording the whole session:

    script -a vm-evidence.log
    python3 scripts/runbook_vm_evidence.py

The script validates the installed helper, policy, pkexec, the vendored VPN
installer hash and the fixed-verb dry-runs. It never performs destructive
actions: the manual blocks for F5/F6.1/F6.2/F2-F3 are printed for the operator
to execute and paste under the matching item in docs/VM_CHECKLIST.md.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "netmedic"))

from netmedic.action_catalog import POLKIT_ACTION_IDS  # noqa: E402
from netmedic.helper_verbs import (  # noqa: E402
    HELPER_VERSION,
    PINNED_VPN_INSTALL_SHA256,
)

HELPER = Path("/usr/libexec/netmedic/helper")
PKEXEC = Path("/usr/bin/pkexec")
POLICY = Path("/usr/share/polkit-1/actions/com.kayab.netmedic.policy")
VPN_SCRIPT = Path("/usr/lib/netmedic/scripts/openvpn-install.sh")
REPO_VPN_SCRIPT = ROOT / "netmedic" / "netmedic" / "data" / "vpn" / "openvpn-install.sh"

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
    elif info.st_uid != 0:
        _fail(f"{label} is not root-owned: {path} (uid={info.st_uid})")
    elif not info.st_mode & 0o111:
        _fail(f"{label} is not executable: {path}")
    else:
        _ok(f"{label}: {path} root-owned regular executable mode={info.st_mode & 0o777:04o}")


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


def _check_policy() -> None:
    if not POLICY.is_file():
        _fail(f"polkit policy missing: {POLICY}")
        return
    info = POLICY.stat()
    if info.st_uid != 0:
        _fail(f"polkit policy is not root-owned: {POLICY} (uid={info.st_uid})")
    else:
        _ok(f"polkit policy present, root-owned, mode={info.st_mode & 0o777:04o}")

    result = _run(["pkaction"])
    if result.returncode != 0:
        _fail(f"pkaction rc={result.returncode}: {result.stderr.strip()}")
        return
    listed = set(result.stdout.split())
    expected = set(POLKIT_ACTION_IDS.values())
    missing = sorted(expected - listed)
    if missing:
        _fail(f"pkaction does not list {len(missing)} expected action(s): {missing}")
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
    staged = Path("/run/netmedic")
    if not staged.exists():
        _warn("/run/netmedic not present (created on demand for VPN staging)")
        return
    info = staged.stat()
    if info.st_uid != 0 or info.st_mode & 0o777 != 0o700:
        _fail(
            f"/run/netmedic must be root:root 0700, got uid={info.st_uid} "
            f"mode={info.st_mode & 0o777:04o}"
        )
    else:
        _ok("/run/netmedic is root:root 0700")


def _check_dry_runs() -> None:
    cases = [
        ("flush-dns", None),
        ("restart-adapter", {"iface": "lo"}),
        ("vpn-list", None),
    ]
    for verb, params in cases:
        argv = [str(HELPER), verb, "--dry-run"]
        if params is not None:
            argv.extend(["--json", json.dumps(params, separators=(",", ":"))])
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
    print(
        """
=== Manual checks (execute separately, paste under docs/VM_CHECKLIST.md) ===

F1 install/journal:
  cd /tmp && sudo /path/to/netmedic_linux/scripts/install-polkit-policy.sh
  pkexec /usr/libexec/netmedic/helper flush-dns --execute --json '{}'
  journalctl -t netmedic-helper -n 1 --no-pager

F2 tamper (restore afterwards):
  sudo cp /usr/lib/netmedic/scripts/openvpn-install.sh /tmp/vpn.bak
  echo '# tampered' | sudo tee -a /usr/lib/netmedic/scripts/openvpn-install.sh
  pkexec /usr/libexec/netmedic/helper vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare"}'
  sudo cp /tmp/vpn.bak /usr/lib/netmedic/scripts/openvpn-install.sh

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
  pkexec /usr/libexec/netmedic/helper vpn-install --execute --json '{"port":1194,"protocol":"udp","dns":"cloudflare","client_ipv6":false,"client":"client"}'
  pkexec /usr/libexec/netmedic/helper vpn-add-client --execute --json '{"name":"laptop"}'
  pkexec /usr/libexec/netmedic/helper vpn-revoke-client --execute --json '{"name":"laptop"}'
  Check where `install --client` leaves the initial profile and whether
  `/root/client.ovpn` exists with a key that has no passphrase.

Do not mark any item complete without the literal output next to it.
"""
    )


def main() -> int:
    _print_environment()
    _check_versions()
    _check_regular_root(HELPER, "helper")
    _check_helper_version()
    _check_pkexec()
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
