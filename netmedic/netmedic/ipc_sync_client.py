"""Synchronous IPC client for MCP, scripts, and headless automation."""
from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any, Dict, Optional

from netmedic.config import Config
from netmedic.ipc_framing import IPC_SOCKET_TIMEOUT, encode_message, parse_message, recv_message
from netmedic.ipc_security import PRIVILEGED_ACTIONS

logger = logging.getLogger(__name__)


class SyncIPCClient:
    """Blocking IPC client that mirrors PilotClient auth semantics without GTK."""

    def __init__(self, sock_path: Optional[str] = None, timeout: float = IPC_SOCKET_TIMEOUT):
        self._sock_path = sock_path or str(Config.get_state_dir() / "ipc.sock")
        self._timeout = timeout
        self._session_token: Optional[str] = None

    @property
    def sock_path(self) -> str:
        return self._sock_path

    def is_available(self) -> bool:
        return os.path.exists(self._sock_path)

    def _raw_request(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._sock_path)
            sock.sendall(encode_message({"action": action, "params": params}))
            data = recv_message(sock, timeout=self._timeout)
            return parse_message(data)
        except (ConnectionRefusedError, FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("IPC sync request failed: %s", exc)
            return {"status": "error", "message": str(exc)}
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _refresh_token(self) -> bool:
        result = self._raw_request("get_session_token", {})
        if result.get("status") == "ok":
            self._session_token = result.get("session_token")
            return True
        return False

    def request(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        if not self.is_available():
            return {
                "status": "error",
                "message": (
                    "NetMedic IPC is not available. "
                    "Start the GUI or run: netmedic --headless"
                ),
            }

        request_params = dict(params or {})
        needs_auth = action in PRIVILEGED_ACTIONS or confirmed
        if needs_auth:
            request_params["confirmed"] = True
            if not self._session_token and not self._refresh_token():
                return {"status": "error", "message": "Failed to obtain IPC session token."}
            request_params["session_token"] = self._session_token

        result = self._raw_request(action, request_params)
        if (
            needs_auth
            and result.get("status") == "error"
            and "token" in result.get("message", "").lower()
        ):
            if self._refresh_token():
                request_params["session_token"] = self._session_token
                result = self._raw_request(action, request_params)
        return result