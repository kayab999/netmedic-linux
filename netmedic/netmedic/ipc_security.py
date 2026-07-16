import logging
import secrets
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional

from netmedic.config import Config

logger = logging.getLogger(__name__)

# Actions that mutate system state and require explicit user confirmation via IPC.
PRIVILEGED_ACTIONS: FrozenSet[str] = frozenset({
    "flush_dns",
    "renew_ip",
    "change_dns",
    "vpn_reconnect",
    "restart_adapter",
    "reset_tcp_ip_stack",
    "toggle_firewall",
    "vpn_create_client",
    "vpn_revoke_client",
})

# Read-only / inference actions allowed without confirmation token.
SAFE_ACTIONS: FrozenSet[str] = frozenset({
    "user_intent",
    "network_status",
    "wifi_diagnostics",
    "get_session_token",
    "donate",
    "vpn_status",
    "vpn_list_clients",
})


class IPCSession:
    """Manages per-instance IPC authorization tokens for privileged operations."""

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

    def validate_privileged(self, action: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Returns an error payload if the action is not authorized, else None."""
        if action in SAFE_ACTIONS:
            return None

        if action not in PRIVILEGED_ACTIONS:
            return {"status": "error", "message": f"Acción desconocida: {action}"}

        if not params.get("confirmed"):
            return {
                "status": "error",
                "message": "Acción privilegiada requiere confirmación explícita (confirmed=true).",
                "requires_confirmation": True,
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
                "message": "Token de sesión IPC inválido o ausente.",
            }

        return None

    def cleanup(self):
        if self.token_file.exists():
            try:
                self.token_file.unlink()
            except OSError as exc:
                logger.error("Error removing IPC token: %s", exc)