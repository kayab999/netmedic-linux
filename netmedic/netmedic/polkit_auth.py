"""PolicyKit authorization checks for privileged IPC actions."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

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

    try:
        import gi

        gi.require_version("Polkit", "1.0")
        from gi.repository import Polkit

        authority = Polkit.Authority.get_sync(None)
        try:
            subject = Polkit.UnixProcess.new_for_owner(pid, uid, -1)
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

    try:
        proc = subprocess.run(
            [pkcheck, "--action-id", action_id, "--process", str(pid), "--uid", str(uid)],
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