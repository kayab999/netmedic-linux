"""Single source of truth for IPC action classification and polkit mapping."""
from __future__ import annotations

from typing import Dict, FrozenSet

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

SAFE_ACTIONS: FrozenSet[str] = frozenset({
    "user_intent",
    "network_status",
    "wifi_diagnostics",
    "get_session_token",
    "donate",
    "vpn_status",
    "vpn_list_clients",
    "firewall_status",
})

POLKIT_ACTION_IDS: Dict[str, str] = {
    "flush_dns": "com.kayab.netmedic.flush-dns",
    "renew_ip": "com.kayab.netmedic.renew-ip",
    "change_dns": "com.kayab.netmedic.change-dns",
    "restart_adapter": "com.kayab.netmedic.restart-adapter",
    "reset_tcp_ip_stack": "com.kayab.netmedic.reset-stack",
    "toggle_firewall": "com.kayab.netmedic.toggle-firewall",
    "vpn_create_client": "com.kayab.netmedic.vpn-create",
    "vpn_revoke_client": "com.kayab.netmedic.vpn-revoke",
    "vpn_reconnect": "com.kayab.netmedic.vpn-reconnect",
}

_INTERNAL_ACTIONS: FrozenSet[str] = frozenset({"get_session_token", "user_intent", "donate"})


def polkit_action_for(ipc_action: str) -> str | None:
    return POLKIT_ACTION_IDS.get(ipc_action)


def is_privileged(ipc_action: str) -> bool:
    return ipc_action in PRIVILEGED_ACTIONS


def is_safe(ipc_action: str) -> bool:
    return ipc_action in SAFE_ACTIONS


def is_internal(ipc_action: str) -> bool:
    return ipc_action in _INTERNAL_ACTIONS