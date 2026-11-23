"""Install / runtime health checks for `netmedic --status`.

LUCP Phase 1 separates the diagnostic core from privileged administration:

* ``core_ready`` means the diagnostic engine is usable. It does not require
  NetworkManager, iproute2, curl, the helper, pkexec or Polkit.
* ``privileged_ready`` means helper, pkexec and the Polkit actions are usable.
  ``False`` never degrades ``core_ready``.
* ``production_ready`` is kept as a deprecated alias of ``core_ready``.

Availability and operation outcome are distinct (see ``capabilities.py``).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from netmedic import __version__
from netmedic.action_catalog import POLKIT_ACTION_IDS
from netmedic.capabilities import (
    SCHEMA_VERSION,
    DetectionContext,
    collect_capabilities,
    collect_scope,
)
from netmedic.config import Config

TIER_CORE = "core"
TIER_PRIVILEGED = "privileged"
TIER_INTEGRATION = "integration"
TIER_OPTIONAL = "optional"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    tier: str = TIER_INTEGRATION


def _pkaction_probe() -> Tuple[Optional[List[str]], str]:
    """Return (action ids, detail). ``None`` means the probe is inconclusive.

    polkit 0.105 (Ubuntu 22.04/24.04) returns a non-zero exit status even when
    it lists every action, so validate the ids instead of the process rc.
    """
    pkaction = shutil.which("pkaction")
    if not pkaction:
        return None, "pkaction not found"
    try:
        proc = subprocess.run(  # noqa: S603 (fixed argv (pkaction path resolved by caller); no shell)
            [pkaction],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"pkaction probe failed: {exc}"
    return (
        [
            line.strip()
            for line in (proc.stdout or "").splitlines()
            if line.strip().startswith("com.kayab.netmedic.")
        ],
        pkaction,
    )


def _ipc_socket_alive() -> tuple[bool, str]:
    try:
        sock = Config.get_state_dir() / "ipc.sock"
    except OSError as exc:
        return False, f"state dir unavailable ({exc})"
    if not sock.exists():
        return False, f"missing {sock}"
    # Presence only — connecting may race a live daemon; try non-blocking connect.
    import socket

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(0.5)
        client.connect(str(sock))
        return True, str(sock)
    except OSError as exc:
        return False, f"{sock} not accepting connections ({exc})"
    finally:
        try:
            client.close()
        except OSError:
            pass


def _state_dir_check() -> CheckResult:
    try:
        state_dir = Config.get_state_dir()
        mode = state_dir.stat().st_mode & 0o777
        owner_ok = state_dir.stat().st_uid == os.getuid()
        return CheckResult(
            "state_dir",
            mode == 0o700 and owner_ok,
            f"{state_dir} mode={oct(mode)} owner_ok={owner_ok}",
            TIER_CORE,
        )
    except OSError as exc:
        return CheckResult("state_dir", False, str(exc), TIER_CORE)


def collect_status() -> Dict[str, Any]:
    """Return a structured health report."""
    checks: List[CheckResult] = []

    runtime_ok = sys.version_info >= (3, 10)
    checks.append(
        CheckResult(
            "python_runtime",
            runtime_ok,
            f"python {platform.python_version()}",
            TIER_CORE,
        )
    )
    checks.append(_state_dir_check())

    helper_path = Config.get_helper_path()
    helper_system = Config.SYSTEM_HELPER_PATH
    helper_on = Config.use_privileged_helper()
    # Marker path "python|-m|..." is not a real file.
    helper_marker = "|" in str(helper_path)

    lib_ok = (Config.SYSTEM_HELPER_LIB / "netmedic" / "helper_main.py").is_file()
    system_ok = helper_system.is_file() and lib_ok
    helper_ready = helper_on and (system_ok or helper_marker)
    checks.append(
        CheckResult(
            "privileged_helper",
            helper_ready,
            (
                f"mode={'on' if helper_on else 'off'} path={helper_path}"
                + (
                    ""
                    if system_ok
                    else " (re-run ./scripts/install-polkit-policy.sh for system lib)"
                )
            ),
            TIER_PRIVILEGED,
        )
    )

    checks.append(
        CheckResult(
            "helper_library",
            lib_ok or helper_marker,
            str(Config.SYSTEM_HELPER_LIB / "netmedic")
            if lib_ok
            else "system library missing (run install-polkit-policy.sh)",
            TIER_PRIVILEGED,
        )
    )

    pkexec = shutil.which("pkexec")
    checks.append(
        CheckResult(
            "pkexec",
            pkexec is not None,
            pkexec or "pkexec not found",
            TIER_PRIVILEGED,
        )
    )

    seen_ids, pkaction_detail = _pkaction_probe()
    polkit_known = seen_ids is not None
    seen = set(seen_ids or [])
    expected = set(POLKIT_ACTION_IDS.values())
    missing = sorted(expected - seen)
    if not polkit_known:
        polkit_ok = False
        polkit_detail = f"polkit probe inconclusive ({pkaction_detail})"
    elif missing:
        polkit_ok = False
        polkit_detail = f"missing: {', '.join(missing[:5])}" + (
            "…" if len(missing) > 5 else ""
        )
    else:
        polkit_ok = bool(expected)
        polkit_detail = f"{len(seen & expected)}/{len(expected)} kayab actions registered"
    checks.append(
        CheckResult("polkit_actions", polkit_ok, polkit_detail, TIER_PRIVILEGED)
    )

    for bin_name in ("nmcli", "ip", "curl"):
        path = shutil.which(bin_name)
        checks.append(
            CheckResult(
                f"bin_{bin_name}",
                path is not None,
                path or "not found",
                TIER_INTEGRATION,
            )
        )

    ipc_ok, ipc_detail = _ipc_socket_alive()
    checks.append(CheckResult("ipc_daemon", ipc_ok, ipc_detail, TIER_OPTIONAL))

    core_ready = all(c.ok for c in checks if c.tier == TIER_CORE)
    # Dev module-marker helper without the system library is not privileged.
    privileged_ready = bool(
        helper_on
        and system_ok
        and not helper_marker
        and pkexec is not None
        and polkit_ok
    )

    ctx = DetectionContext(
        which=shutil.which,
        helper_installed=system_ok,
        helper_enabled=helper_on,
        pkexec_present=pkexec is not None,
        polkit_probe_ok=polkit_known,
        polkit_actions=frozenset(seen),
    )
    capabilities = [cap.to_dict() for cap in collect_capabilities(ctx)]

    return {
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "scope": collect_scope().to_dict(),
        "overall_ok": core_ready,
        "core_ready": core_ready,
        # Deprecated alias: use core_ready for diagnostics and privileged_ready
        # for automation that needs L2.
        "production_ready": core_ready,
        "privileged_ready": privileged_ready,
        "helper_mode": helper_on,
        "capabilities": capabilities,
        "checks": [asdict(c) for c in checks],
        "hints": _hints(checks, core_ready=core_ready, privileged_ready=privileged_ready),
        "deprecations": [
            "production_ready is a deprecated alias of core_ready; "
            "use core_ready for diagnostics and privileged_ready for L2 automation."
        ],
    }


def _hints(
    checks: List[CheckResult], *, core_ready: bool, privileged_ready: bool
) -> List[str]:
    hints: List[str] = []
    by_name = {c.name: c for c in checks}
    if not core_ready:
        hints.append("Core diagnostics unavailable: review the failed core checks.")
    if not by_name.get("privileged_helper", CheckResult("", True, "")).ok:
        hints.append("Install helper + policy: ./scripts/install-polkit-policy.sh")
    if not by_name.get("helper_library", CheckResult("", True, "")).ok:
        hints.append("Helper library missing — re-run ./scripts/install-polkit-policy.sh as root")
    if not by_name.get("pkexec", CheckResult("", True, "")).ok:
        hints.append("pkexec not found — privileged actions stay unavailable")
    if not by_name.get("polkit_actions", CheckResult("", True, "")).ok:
        hints.append("Polkit actions missing or unknown — re-run install-polkit-policy.sh as root")
    if not by_name.get("ipc_daemon", CheckResult("", True, "")).ok:
        hints.append("IPC socket down — start GUI or: netmedic --headless")
    if privileged_ready:
        hints.append("Privileged administration path looks ready.")
    elif core_ready:
        hints.append("Core diagnostics remain available without helper/Polkit.")
    return hints


def format_status_text(report: Dict[str, Any]) -> str:
    scope = report.get("scope") or {}
    netns = scope.get("network_namespace") or "namespace unknown"
    lines = [
        f"NetMedic {report['version']} status (schema {report['schema_version']})",
        f"  scope: {scope.get('label', 'unknown')} ({netns}; "
        f"container_hint={scope.get('container_hint')})",
        f"  core_ready: {report['core_ready']}",
        f"  privileged_ready: {report['privileged_ready']}",
        f"  production_ready: {report['production_ready']} "
        "(deprecated alias of core_ready)",
        f"  helper_mode: {report['helper_mode']}",
        "  capabilities:",
    ]
    for cap in report.get("capabilities", []):
        reason = f", {cap['reason_code']}" if cap.get("reason_code") else ""
        backend = cap.get("backend") or "no backend"
        lines.append(
            f"    [{cap['availability']}] {cap['id']} "
            f"({cap['level']}, {backend}{reason})"
        )
    lines.append("  checks:")
    for c in report["checks"]:
        mark = "OK" if c["ok"] else "FAIL"
        lines.append(f"    [{mark}] {c['name']}: {c['detail']}")
    if report.get("hints"):
        lines.append("  hints:")
        for h in report["hints"]:
            lines.append(f"    - {h}")
    return "\n".join(lines) + "\n"


def print_status(*, as_json: bool = False, require_privileged: bool = False) -> int:
    """Print status to stdout. Returns 0 when core_ready (and L2 if required)."""
    report = collect_status()
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_status_text(report), end="")
    ready = bool(report.get("core_ready"))
    if require_privileged and not report.get("privileged_ready"):
        ready = False
    return 0 if ready else 1
