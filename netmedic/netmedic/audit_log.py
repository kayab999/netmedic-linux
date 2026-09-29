"""Structured audit log for privileged IPC operations.

M3 trust note: this file lives under the caller's UID (XDG state dir), so
it is evidence, not tamper-proof truth, against a same-UID attacker. The
tamper-evident records are the root-side ones the helper emits to the
system journal on every verb outcome (see helper_main._journal_result).
What M3 hardens here: no symlink following, 0600 at creation (not
open-then-chmod), fsync per record, and denial rate-limiting so a local
client cannot rotate evidence away by spamming denials.
"""
from __future__ import annotations

import json
import logging
import os
import stat
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

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


# M3: denial/auth-failure rate limit — one record per key per window, with
# a suppressed counter so rotation cannot be forced by spamming denials.
_DENIAL_WINDOW_S = 5.0
_denial_state: Dict[Tuple[str, str], Tuple[float, int]] = {}


def _denial_allowed(action: str, outcome: str) -> Tuple[bool, int]:
    """Return (allowed, suppressed_count) for a denial-class record."""
    now = time.monotonic()
    key = (action, outcome)
    with _lock:
        window_start, suppressed = _denial_state.get(key, (0.0, 0))
        if now - window_start < _DENIAL_WINDOW_S:
            _denial_state[key] = (window_start, suppressed + 1)
            return False, suppressed + 1
        _denial_state[key] = (now, 0)
        return True, suppressed


def _reset_denial_state() -> None:
    """Test hook: clear the denial rate-limiter."""
    with _lock:
        _denial_state.clear()


def _append_entry(entry: Dict[str, Any]) -> None:
    """Append one entry; raises OSError on failure (fail-closed callers).

    M3: O_APPEND|O_CREAT|O_NOFOLLOW with 0600 at creation (umask-proof via
    O_CREAT mode + fchmod guard), fsync before close. Symlinked audit.log
    is refused instead of followed.
    """
    line = (json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    path = get_audit_log_path()
    with _lock:
        _rotate_audit_if_needed(path)
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    raise OSError("audit log is not a regular file")
                if stat.S_IMODE(st.st_mode) != 0o600:
                    os.fchmod(fd, 0o600)
            except OSError:
                raise
            mv = memoryview(line)
            while mv:
                written = os.write(fd, mv)
                mv = mv[written:]
            os.fsync(fd)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


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
    if outcome == "denied":
        # M3: rate-limit denial records (rotation-spam guard). Intent records
        # are never limited — record_intent stays the fail-closed gate.
        allowed, suppressed = _denial_allowed(action, outcome)
        if not allowed:
            logger.debug("Suppressing duplicate denial audit for %s", action)
            return
    else:
        suppressed = 0
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
    if suppressed:
        entry["suppressed_denials"] = suppressed
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