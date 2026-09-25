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


_SENSITIVE_SUBSTR = ("password", "pass", "token", "key", "secret", "auth")
_MAX_PARAM_STR = 500


def _redact_value(key: str, value: Any) -> Any:
    kl = key.lower()
    if key == "session_token" or any(s in kl for s in _SENSITIVE_SUBSTR):
        return "<redacted>"
    if isinstance(value, str) and len(value) > _MAX_PARAM_STR:
        return value[:_MAX_PARAM_STR] + "...[truncated]"
    return value


def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in params.items():
        safe[key] = _redact_value(key, value)
    return safe


_MAX_AUDIT_BYTES = 1_048_576
_MAX_AUDIT_BACKUPS = 3


def _rotate_audit_if_needed(path) -> None:
    try:
        if path.exists() and path.stat().st_size > _MAX_AUDIT_BYTES:
            # Rotate audit.log -> audit.log.1 -> .2 -> .3
            for i in range(_MAX_AUDIT_BACKUPS, 0, -1):
                src = path.with_name(f"{path.name}.{i}")
                dst = path.with_name(f"{path.name}.{i+1}")
                if src.exists():
                    if i == _MAX_AUDIT_BACKUPS:
                        try:
                            src.unlink()
                        except OSError:
                            pass
                    else:
                        try:
                            src.rename(dst)
                        except OSError:
                            pass
            try:
                path.rename(path.with_name(f"{path.name}.1"))
            except OSError:
                pass
    except OSError:
        pass


def _append_entry(entry: Dict[str, Any]) -> None:
    """Append one entry; raises OSError on failure (fail-closed callers)."""
    line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
    path = get_audit_log_path()
    with _lock:
        _rotate_audit_if_needed(path)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        os.chmod(path, 0o600)


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
    """Append one JSON audit record for a privileged IPC action (completion).

    Best-effort: failures are logged, never raised — the intent record
    (record_intent) is the fail-closed gate, written before execution.
    """
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
    if result.get("requires_helper"):
        entry["requires_helper"] = True

    try:
        _append_entry(entry)
    except OSError:
        logger.exception("Failed to write privileged IPC audit record for action=%s", action)


def record_intent(
    *,
    action: str,
    peer_uid: int,
    peer_pid: int,
    params: Dict[str, Any],
) -> None:
    """Record intent BEFORE a privileged action executes.

    Lets OSError propagate: callers must abort the action when intent cannot
    be recorded (no action-without-audit). Completion is recorded separately
    by record() with event "privileged_ipc".
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "privileged_intent",
        "action": action,
        "peer_uid": peer_uid,
        "peer_pid": peer_pid,
        "params": _sanitize_params(params),
    }
    _append_entry(entry)