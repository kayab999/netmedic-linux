"""Single source of truth for IPC action classification and polkit mapping.

M8: the ACTIONS table below is the ONE definition of every action. The
legacy module-level sets/dicts are derived from it (same names, same
values) so existing imports keep working while generators (policy XML,
VERBS.md registry, IPC schema) read the table. stdlib only (`dataclasses`
+ `typing`) so the privileged helper can ship this module under `-I`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple


@dataclass(frozen=True)
class ActionSpec:
    """One row of the action registry.

    - ipc_action: snake_case IPC name, or None for helper-only verbs.
    - helper_verb: kebab-case helper verb, or None for unprivileged actions.
    - polkit_id: full polkit action id, or None when no elevation applies.
    - tier: "privileged" | "safe" | "internal".
    - disruptive: extra GUI confirmation required on the AI path.
    - keep_auth: allow_active retention window (auth_admin_keep vs auth_admin).
      Meaningful only when polkit_id is set; low-impact verbs keep the
      5-minute window, high-risk verbs re-prompt every time.
    - description: human text, feeds generated policy/docs.
    """

    ipc_action: Optional[str]
    helper_verb: Optional[str]
    polkit_id: Optional[str]
    tier: str
    disruptive: bool
    keep_auth: bool
    description: str


ACTIONS: Tuple[ActionSpec, ...] = (
    # Privileged: fixed helper verbs behind polkit.
    ActionSpec("flush_dns", "flush-dns", "com.kayab.netmedic.flush-dns",
               "privileged", False, True, "Flush DNS resolver cache"),
    ActionSpec("renew_ip", "renew-ip", "com.kayab.netmedic.renew-ip",
               "privileged", False, True, "Renew DHCP IP address"),
    ActionSpec("change_dns", "change-dns", "com.kayab.netmedic.change-dns",
               "privileged", False, True, "Change DNS server"),
    ActionSpec("restart_adapter", "restart-adapter", "com.kayab.netmedic.restart-adapter",
               "privileged", True, True, "Restart network adapter"),
    ActionSpec("reset_tcp_ip_stack", "reset-stack", "com.kayab.netmedic.reset-stack",
               "privileged", True, False, "Reset TCP/IP stack"),
    ActionSpec("toggle_firewall", "toggle-firewall", "com.kayab.netmedic.toggle-firewall",
               "privileged", True, False, "Toggle UFW firewall"),
    ActionSpec("vpn_create_client", "vpn-run-script", "com.kayab.netmedic.vpn-create",
               "privileged", False, False, "Create VPN client"),
    ActionSpec("vpn_revoke_client", "vpn-run-script", "com.kayab.netmedic.vpn-revoke",
               "privileged", True, False, "Revoke VPN client"),
    ActionSpec("vpn_reconnect", "vpn-restart-service", "com.kayab.netmedic.vpn-reconnect",
               "privileged", False, False, "Reconnect VPN service"),
    # Elevates via pkexec to read EasyRSA index; must not be unauthenticated.
    ActionSpec("vpn_list_clients", "vpn-list", "com.kayab.netmedic.vpn-list",
               "privileged", False, False, "List VPN clients"),
    ActionSpec("vpn_install", "vpn-run-script", "com.kayab.netmedic.vpn-install",
               "privileged", True, False, "Install OpenVPN server"),
    ActionSpec("vpn_start_service", "vpn-start-service", "com.kayab.netmedic.vpn-start",
               "privileged", False, False, "Start OpenVPN service"),
    # Safe: no elevation, no helper verb.
    ActionSpec("user_intent", None, None, "safe", False, False, "AI guardrail validation"),
    ActionSpec("network_status", None, None, "safe", False, False, "Multi-target connectivity probes"),
    ActionSpec("wifi_diagnostics", None, None, "safe", False, False, "Wi-Fi scan parse"),
    ActionSpec("get_session_token", None, None, "safe", False, False, "IPC token issue"),
    ActionSpec("donate", None, None, "safe", False, False, "Open browser"),
    ActionSpec("vpn_status", None, None, "safe", False, False, "VPN service state"),
    ActionSpec("firewall_status", None, None, "safe", False, False, "UFW status parse"),
    # Internal: helper-only verbs with no IPC action, no policy entry.
    ActionSpec(None, "iface-del", None, "internal", False, False, "Delete medic dummy iface"),
    ActionSpec(None, "iface-add-dummy", None, "internal", False, False, "Add medic dummy iface"),
)


def _by_tier(tier: str) -> FrozenSet[str]:
    return frozenset(s.ipc_action for s in ACTIONS if s.tier == tier and s.ipc_action is not None)


def _helper_verbs() -> FrozenSet[str]:
    return frozenset(s.helper_verb for s in ACTIONS if s.helper_verb is not None)


def _ipc_to_verb() -> Dict[str, str]:
    return {s.ipc_action: s.helper_verb for s in ACTIONS
            if s.ipc_action is not None and s.helper_verb is not None}


def _polkit_ids() -> Dict[str, str]:
    return {s.ipc_action: s.polkit_id for s in ACTIONS
            if s.ipc_action is not None and s.polkit_id is not None}


# Legacy names, derived — same values as the hand-maintained sets they replace.
PRIVILEGED_ACTIONS: FrozenSet[str] = _by_tier("privileged")

SAFE_ACTIONS: FrozenSet[str] = _by_tier("safe")

DISRUPTIVE_ACTIONS: FrozenSet[str] = frozenset(
    s.ipc_action for s in ACTIONS if s.disruptive and s.ipc_action is not None
)

POLKIT_ACTION_IDS: Dict[str, str] = _polkit_ids()

IPC_TO_VERB: Dict[str, str] = _ipc_to_verb()

ALL_HELPER_VERBS: FrozenSet[str] = _helper_verbs()

_INTERNAL_ACTIONS: FrozenSet[str] = frozenset({"get_session_token", "user_intent", "donate"})


def spec_for_ipc(ipc_action: str) -> Optional[ActionSpec]:
    """Return the table row for an IPC action, or None."""
    for spec in ACTIONS:
        if spec.ipc_action == ipc_action:
            return spec
    return None


def spec_for_polkit(polkit_id: str) -> Optional[ActionSpec]:
    """Return the table row for a polkit action id, or None."""
    for spec in ACTIONS:
        if spec.polkit_id == polkit_id:
            return spec
    return None


def keep_auth_for(polkit_id: str) -> bool:
    """Retention window for a polkit id (False = auth_admin, re-prompt)."""
    spec = spec_for_polkit(polkit_id)
    return spec.keep_auth if spec is not None else False


def polkit_action_for(ipc_action: str) -> str | None:
    return POLKIT_ACTION_IDS.get(ipc_action)


def is_privileged(ipc_action: str) -> bool:
    return ipc_action in PRIVILEGED_ACTIONS


def is_safe(ipc_action: str) -> bool:
    return ipc_action in SAFE_ACTIONS


def is_disruptive(ipc_action: str) -> bool:
    return ipc_action in DISRUPTIVE_ACTIONS


def is_internal(ipc_action: str) -> bool:
    return ipc_action in _INTERNAL_ACTIONS
