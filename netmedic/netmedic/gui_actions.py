"""GUI → IPC bridge so window handlers share auth, polkit, and audit with the daemon.

Privileged GUI work must not call NetworkMedic/operators with pkexec directly;
it goes through the Unix-socket IPC path (session token + polkit + audit log).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from netmedic.action_catalog import is_privileged
from netmedic.ipc_sync_client import SyncIPCClient
from netmedic.models import NetResult
from netmedic.operators.vpn.base import VPNClient

_ACTION_OPERATION: Dict[str, str] = {
    "network_status": "Diagnostics",
    "wifi_diagnostics": "Wi-Fi Scan",
    "flush_dns": "Flush DNS",
    "renew_ip": "Renew IP",
    "change_dns": "Change DNS",
    "restart_adapter": "Restart Adapter",
    "reset_tcp_ip_stack": "Reset Stack",
    "toggle_firewall": "Firewall",
    "firewall_status": "Firewall Status",
    "vpn_status": "OpenVPN (Angristan)",
    "vpn_list_clients": "OpenVPN (Angristan)",
    "vpn_create_client": "OpenVPN (Angristan)",
    "vpn_revoke_client": "OpenVPN (Angristan)",
    "vpn_reconnect": "OpenVPN (Angristan)",
    "vpn_install": "OpenVPN (Angristan)",
    "vpn_start_service": "OpenVPN (Angristan)",
}


def payload_to_net_result(action: str, payload: Dict[str, Any]) -> NetResult:
    """Map an IPC JSON response into a NetResult for existing UI logging paths."""
    operation = _ACTION_OPERATION.get(action, action)
    status = payload.get("status")
    success = status == "ok"
    message = payload.get("message") or ("OK" if success else "IPC error")
    details = payload.get("details")
    data = payload.get("data")

    if action == "vpn_list_clients" and isinstance(data, list):
        clients = []
        for item in data:
            if isinstance(item, VPNClient):
                clients.append(item)
            elif isinstance(item, dict) and "name" in item:
                clients.append(
                    VPNClient(name=str(item["name"]), active=bool(item.get("active")))
                )
            else:
                clients.append(item)
        data = clients

    if not success and details is None:
        # Surface polkit / confirmation hints in the log when present.
        hints = []
        if payload.get("requires_polkit"):
            hints.append("polkit required")
        if payload.get("requires_confirmation"):
            hints.append("confirmation required")
        if payload.get("requires_peer_auth"):
            hints.append("peer auth failed")
        if hints:
            details = ", ".join(hints)

    return NetResult(
        operation=operation,
        success=success,
        message=message,
        details=details,
        data=data,
    )


class GuiActionBridge:
    """Thread-safe enough for ThreadPoolExecutor: one SyncIPCClient per bridge."""

    def __init__(self, client: Optional[SyncIPCClient] = None):
        self._client = client or SyncIPCClient()

    @property
    def client(self) -> SyncIPCClient:
        return self._client

    def is_available(self) -> bool:
        return self._client.is_available()

    def call(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        confirmed: Optional[bool] = None,
    ) -> NetResult:
        """Invoke an IPC action and return NetResult.

        Privileged actions default to confirmed=True because the GUI either
        already showed a confirmation dialog or is an intentional user click
        (flush/renew) that will still hit polkit server-side.
        """
        if not self._client.is_available():
            return NetResult(
                _ACTION_OPERATION.get(action, action),
                False,
                "NetMedic IPC is not available (daemon socket missing).",
            )

        if confirmed is None:
            confirmed = is_privileged(action)

        payload = self._client.request(action, params or {}, confirmed=bool(confirmed))
        return payload_to_net_result(action, payload)
