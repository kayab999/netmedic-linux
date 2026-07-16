"""Structured audit log for privileged IPC operations."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from netmedic.config import Config

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def get_audit_log_path():
    return Config.get_state_dir() / "audit.log"


def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in params.items():
        if key == "session_token":
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def record(
    *,
    action: str,
    peer_uid: int,
    peer_pid: int,
    params: Dict[str, Any],
    result: Dict[str, Any],
    duration_ms: float,
    outcome: str,
) -> None:
    """Append one JSON audit record for a privileged IPC action."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "privileged_ipc",
        "action": action,
        "peer_uid": peer_uid,
        "peer_pid": peer_pid,
        "outcome": outcome,
        "status": result.get("status"),
        "message": result.get("message"),
        "duration_ms": round(duration_ms, 2),
        "params": _sanitize_params(params),
    }
    if result.get("requires_polkit"):
        entry["requires_polkit"] = True
    if result.get("requires_confirmation"):
        entry["requires_confirmation"] = True

    line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
    path = get_audit_log_path()
    try:
        with _lock:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            os.chmod(path, 0o600)
    except OSError:
        logger.exception("Failed to write privileged IPC audit record for action=%s", action)