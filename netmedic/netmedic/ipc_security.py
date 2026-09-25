import logging
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from netmedic.action_catalog import (  # noqa: F401 — re-exported for callers
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    is_privileged,
    is_safe,
)
from netmedic.config import Config
from netmedic.ipc_peer import validate_peer_identity
from netmedic.polkit_auth import check_authorization

logger = logging.getLogger(__name__)


def _write_secret_file(path: Path, content: str, mode: int = 0o600) -> None:
    """Atomically create/replace a secret file with restrictive mode.

    Write-then-rename in the same directory: readers of `path` observe the
    old or the new content, never a torn write. The temp file is created
    with the final mode up front (no chmod window) and unlinked on failure.
    Sibling directory is required — cross-device rename is not atomic.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        # Stale tmp from a crashed run under a recycled PID; ours to replace.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, mode)
    except OSError:
        pass


class IPCSession:
    """Manages per-instance IPC authorization for privileged operations."""

    def __init__(self) -> None:
        self.token_file: Path = Config.get_state_dir() / "ipc.token"
        self._token: Optional[str] = None

    def issue_token(self) -> str:
        self._token = secrets.token_hex(32)
        _write_secret_file(self.token_file, self._token, 0o600)
        logger.debug("IPC session token issued.")
        return self._token

    def get_token(self) -> Optional[str]:
        if self._token is None and self.token_file.exists():
            self._token = self.token_file.read_text(encoding="utf-8").strip()
        return self._token

    def validate_privileged(
        self,
        action: str,
        params: Dict[str, Any],
        *,
        peer_uid: int = -1,
        peer_pid: int = -1,
    ) -> Optional[Dict[str, Any]]:
        """Returns an error payload if the action is not authorized, else None.

        Order: classification → confirmed → peer → session token → polkit.
        Cheap non-interactive checks run before interactive polkit prompts so
        invalid-token clients cannot spam authorization dialogs.
        """
        if is_safe(action):
            return None

        if not is_privileged(action):
            return {"status": "error", "message": f"Unknown privileged action: {action}"}

        if params.get("confirmed") is not True:
            return {
                "status": "error",
                "message": "Privileged action requires explicit confirmation (confirmed=true).",
                "requires_confirmation": True,
            }

        peer_error = validate_peer_identity(peer_uid, peer_pid)
        if peer_error:
            return peer_error

        expected = self.get_token()
        supplied = str(params.get("session_token", ""))
        if not expected or not supplied:
            return {
                "status": "error",
                "message": "Invalid or missing IPC session token.",
            }
        # Constant-time compare; pad only when lengths match is insufficient for
        # full CT, but fixed-length tokens make length oracle negligible. Always
        # compare when both non-empty and equal length; otherwise reject.
        if len(supplied) != len(expected) or not secrets.compare_digest(supplied, expected):
            return {
                "status": "error",
                "message": "Invalid or missing IPC session token.",
            }

        # Phase D single-prompt model: when the privileged helper is in use,
        # interactive polkit is deferred to `pkexec netmedic-helper` (annotated
        # exec.path). IPC still enforces peer + token + confirmed.
        if Config.use_privileged_helper():
            logger.debug(
                "Skipping IPC interactive polkit for %s (helper elevation path)",
                action,
            )
            return None

        authorized, polkit_error = check_authorization(action, peer_uid, peer_pid)
        if not authorized:
            return {
                "status": "error",
                "message": polkit_error or "Polkit authorization denied.",
                "requires_polkit": True,
            }

        return None

    def cleanup(self) -> None:
        if self.token_file.exists():
            try:
                self.token_file.unlink()
            except OSError as exc:
                logger.error("Error removing IPC token: %s", exc)
