"""Install / runtime health checks for `netmedic --status`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from netmedic import __version__
from netmedic.action_catalog import POLKIT_ACTION_IDS
from netmedic.config import Config


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _file_ok(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _pkaction_ids() -> List[str]:
    pkaction = shutil.which("pkaction")
    if not pkaction:
        return []
    try:
        proc = subprocess.run(
            [pkaction],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [
        line.strip()
        for line in (proc.stdout or "").splitlines()
        if line.strip().startswith("com.kayab.netmedic.")
    ]


def _ipc_socket_alive() -> tuple[bool, str]:
    sock = Config.get_state_dir() / "ipc.sock"
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


def collect_status() -> Dict[str, Any]:
    """Return a structured health report."""
    checks: List[CheckResult] = []

    helper_path = Config.get_helper_path()
    helper_system = Config.SYSTEM_HELPER_PATH
    helper_on = Config.use_privileged_helper()
    helper_exists = _file_ok(helper_system) or (
        helper_path.exists() if hasattr(helper_path, "exists") else False
    )
    # Marker path "python|-m|..." is not a real file.
    helper_marker = "|" in str(helper_path)
    if helper_marker:
        helper_exists = True  # module path usable in dev

    lib_ok = (Config.SYSTEM_HELPER_LIB / "netmedic" / "helper_main.py").is_file()
    helper_ready = helper_on and (
        (helper_system.is_file() and lib_ok) or helper_marker
    )
    checks.append(
        CheckResult(
            "privileged_helper",
            helper_ready,
            (
                f"mode={'on' if helper_on else 'off'} path={helper_path}"
                + (
                    ""
                    if helper_system.is_file() and lib_ok
                    else " (re-run ./scripts/install-polkit-policy.sh for system lib)"
                )
            ),
        )
    )

    checks.append(
        CheckResult(
            "helper_library",
            lib_ok or helper_marker,
            str(Config.SYSTEM_HELPER_LIB / "netmedic")
            if lib_ok
            else "system library missing (run install-polkit-policy.sh)",
        )
    )

    pkexec = shutil.which("pkexec")
    checks.append(
        CheckResult(
            "pkexec",
            pkexec is not None,
            pkexec or "pkexec not found",
        )
    )

    seen = set(_pkaction_ids())
    expected = set(POLKIT_ACTION_IDS.values())
    missing = sorted(expected - seen)
    checks.append(
        CheckResult(
            "polkit_actions",
            len(missing) == 0 and len(expected) > 0,
            (
                f"{len(seen & expected)}/{len(expected)} kayab actions registered"
                if not missing
                else f"missing: {', '.join(missing[:5])}"
                + ("…" if len(missing) > 5 else "")
            ),
        )
    )

    for bin_name in ("nmcli", "ip", "curl"):
        path = shutil.which(bin_name)
        checks.append(
            CheckResult(f"bin_{bin_name}", path is not None, path or "not found")
        )

    ipc_ok, ipc_detail = _ipc_socket_alive()
    checks.append(CheckResult("ipc_daemon", ipc_ok, ipc_detail))

    state_dir = Config.get_state_dir()
    try:
        mode = state_dir.stat().st_mode & 0o777
        owner_ok = state_dir.stat().st_uid == os.getuid()
        checks.append(
            CheckResult(
                "state_dir",
                mode == 0o700 and owner_ok,
                f"{state_dir} mode={oct(mode)} owner_ok={owner_ok}",
            )
        )
    except OSError as exc:
        checks.append(CheckResult("state_dir", False, str(exc)))

    overall = all(c.ok for c in checks if c.name != "ipc_daemon")
    # IPC is optional for --status (daemon may be stopped).
    production_ready = all(
        c.ok
        for c in checks
        if c.name
        in (
            "privileged_helper",
            "helper_library",
            "pkexec",
            "polkit_actions",
            "bin_nmcli",
            "bin_ip",
        )
    )
    # Dev module-marker helper without system lib is not production_ready.
    if helper_marker and not lib_ok:
        production_ready = False

    return {
        "version": __version__,
        "overall_ok": overall,
        "production_ready": production_ready,
        "helper_mode": helper_on,
        "checks": [asdict(c) for c in checks],
        "hints": _hints(checks, production_ready),
    }


def _hints(checks: List[CheckResult], production_ready: bool) -> List[str]:
    hints: List[str] = []
    by_name = {c.name: c for c in checks}
    if not by_name.get("privileged_helper", CheckResult("", False, "")).ok:
        hints.append("Install helper + policy: ./scripts/install-polkit-policy.sh")
    if not by_name.get("polkit_actions", CheckResult("", False, "")).ok:
        hints.append("Polkit actions missing — re-run install-polkit-policy.sh as root")
    if not by_name.get("ipc_daemon", CheckResult("", True, "")).ok:
        hints.append("IPC socket down — start GUI or: netmedic --headless")
    if production_ready:
        hints.append("Core privileged path looks ready.")
    return hints


def format_status_text(report: Dict[str, Any]) -> str:
    lines = [
        f"NetMedic {report['version']} status",
        f"  helper_mode: {report['helper_mode']}",
        f"  production_ready: {report['production_ready']}",
        "  checks:",
    ]
    for c in report["checks"]:
        mark = "OK" if c["ok"] else "FAIL"
        lines.append(f"    [{mark}] {c['name']}: {c['detail']}")
    if report.get("hints"):
        lines.append("  hints:")
        for h in report["hints"]:
            lines.append(f"    - {h}")
    return "\n".join(lines) + "\n"


def print_status(*, as_json: bool = False) -> int:
    """Print status to stdout. Returns process exit code (0 if production_ready)."""
    report = collect_status()
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_status_text(report), end="")
    return 0 if report.get("production_ready") else 1
