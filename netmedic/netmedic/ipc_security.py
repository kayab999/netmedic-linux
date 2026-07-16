import logging
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
from netmedic.polkit_auth import check_authorization

logger = logging.getLogger(__name__)


class IPCSession:
    """Manages per-instance IPC authorization for privileged operations."""

    def __init__(self):
        self.token_file: Path = Config.get_state_dir() / "ipc.token"
        self._token: Optional[str] = None

    def issue_token(self) -> str:
        self._token = secrets.token_hex(32)
        self.token_file.write_text(self._token)
        self.token_file.chmod(0o600)
        logger.debug("IPC session token issued.")
        return self._token

    def get_token(self) -> Optional[str]:
        if self._token is None and self.token_file.exists():
            self._token = self.token_file.read_text().strip()
        return self._token

    def validate_privileged(
        self,
        action: str,
        params: Dict[str, Any],
        *,
        peer_uid: int = -1,
        peer_pid: int = -1,
    ) -> Optional[Dict[str, Any]]:
        """Returns an error payload if the action is not authorized, else None."""
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

        authorized, polkit_error = check_authorization(action, peer_uid, peer_pid)
        if not authorized:
            return {
                "status": "error",
                "message": polkit_error or "Polkit authorization denied.",
                "requires_polkit": True,
            }

        expected = self.get_token()
        supplied = str(params.get("session_token", ""))
        if not expected or len(supplied) != len(expected):
            return {
                "status": "error",
                "message": "Invalid or missing IPC session token.",
            }
        if not secrets.compare_digest(supplied, expected):
            return {
                "status": "error",
                "message": "Invalid or missing IPC session token.",
            }

        return None

    def cleanup(self):
        if self.token_file.exists():
            try:
                self.token_file.unlink()
            except OSError as exc:
                logger.error("Error removing IPC token: %s", exc)