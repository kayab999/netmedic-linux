"""PolicyKit authorization checks for privileged IPC actions."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional, Tuple

from netmedic.action_catalog import polkit_action_for

logger = logging.getLogger(__name__)


def skip_polkit() -> bool:
    """Honor polkit skip only in explicit test mode (fail-closed in production)."""
    if os.environ.get("NETMEDIC_SKIP_POLKIT", "").lower() not in ("1", "true", "yes"):
        return False
    if os.environ.get("NETMEDIC_TEST_MODE") == "1":
        return True
    logger.warning(
        "NETMEDIC_SKIP_POLKIT is set but ignored outside NETMEDIC_TEST_MODE (fail-closed)."
    )
    return False


def process_start_time(pid: int) -> Optional[int]:
    """Return Linux process starttime ticks from /proc/<pid>/stat, or None."""
    if pid <= 0:
        return None
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as handle:
            data = handle.read()
        # comm may contain spaces/parens; starttime is field 22 after ") ".
        close_paren = data.rfind(")")
        if close_paren < 0:
            return None
        fields = data[close_paren + 2 :].split()
        # After ")": state is fields[0] → starttime is fields[19] (stat field 22).
        if len(fields) < 20:
            return None
        return int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


def _process_subject_spec(pid: int, uid: int) -> Tuple[str, Optional[int]]:
    """Build pkcheck --process value and optional start_time for GI.

    pkcheck accepts ``pid`` or ``pid,start_time`` or ``pid,start_time,uid``.
    """
    start_time = process_start_time(pid)
    if start_time is None:
        return str(pid), None
    return f"{pid},{start_time},{uid}", start_time


def check_authorization(
    ipc_action: str,
    uid: int,
    pid: int,
    *,
    allow_interaction: bool = True,
) -> tuple[bool, Optional[str]]:
    """Return (authorized, error_message)."""
    if skip_polkit():
        return True, None

    action_id = polkit_action_for(ipc_action)
    if not action_id:
        return False, f"No polkit policy mapped for action: {ipc_action}"

    if uid < 0 or pid < 0:
        return False, "Missing peer credentials for polkit authorization."

    process_spec, start_time = _process_subject_spec(pid, uid)

    try:
        import gi

        gi.require_version("Polkit", "1.0")
        from gi.repository import Polkit

        authority = Polkit.Authority.get_sync(None)
        # Signature: new_for_owner(pid, start_time, uid). start_time=0 → look up.
        gi_start = 0 if start_time is None else start_time
        try:
            subject = Polkit.UnixProcess.new_for_owner(pid, gi_start, uid)
        except (AttributeError, TypeError):
            subject = Polkit.UnixProcess.new(pid)
        flags = (
            Polkit.CheckAuthorizationFlags.ALLOW_USER_INTERACTION
            if allow_interaction
            else Polkit.CheckAuthorizationFlags.NONE
        )
        result = authority.check_authorization_sync(subject, action_id, None, flags, None)
        if result.get_is_authorized():
            return True, None
        return False, "Polkit authorization denied."
    except Exception as exc:
        logger.debug("Polkit GI authorization failed, trying pkcheck: %s", exc)

    pkcheck = shutil.which("pkcheck")
    if not pkcheck:
        return False, "Polkit unavailable (pkcheck not found)."

    cmd = [
        pkcheck,
        "--action-id",
        action_id,
        "--process",
        process_spec,
    ]
    if allow_interaction:
        cmd.append("--allow-user-interaction")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60 if allow_interaction else 5,
            check=False,
        )
        if proc.returncode == 0:
            return True, None
        if proc.returncode == 127:
            return False, "Interactive polkit authorization required (start pkttyagent or use GUI)."
        return False, "Polkit authorization denied."
    except subprocess.TimeoutExpired:
        return False, "Polkit authorization timed out."
    except OSError as exc:
        return False, f"Polkit check failed: {exc}"
