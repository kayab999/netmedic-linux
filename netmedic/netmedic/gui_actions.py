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
    from netmedic.models import ResultCode
    operation = _ACTION_OPERATION.get(action, action)
    status = payload.get("status")
    success = status == "ok"
    # Prefer explicit code when present (PR2)
    code_raw = payload.get("code")
    try:
        code = ResultCode(code_raw) if code_raw else (ResultCode.OK if success else ResultCode.FAILED)
    except ValueError:
        code = ResultCode.OK if success else ResultCode.FAILED
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
        # Surface polkit / confirmation / helper hints in the log when present.
        hints = []
        if payload.get("requires_polkit"):
            hints.append("polkit required")
        if payload.get("requires_confirmation"):
            hints.append("confirmation required")
        if payload.get("requires_peer_auth"):
            hints.append("peer auth failed")
        msg_low = (message or "").lower()
        if "helper-missing" in msg_low or "helper not installed" in msg_low:
            hints.append("helper missing: run ./scripts/install-polkit-policy.sh")
        elif payload.get("requires_helper"):
            hints.append("helper missing")
        if hints:
            details = ", ".join(hints)
    # Also surface helper-missing even when details already present — append hint
    if not success and details is not None:
        msg_low = (message or "").lower() + " " + (details or "").lower()
        if "helper-missing" in msg_low and "helper missing" not in (details or "").lower():
            details = f"{details} (helper missing: run ./scripts/install-polkit-policy.sh)"

    return NetResult(
        operation=operation,
        success=success,
        message=message,
        details=details,
        data=data,
        code=code,
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
