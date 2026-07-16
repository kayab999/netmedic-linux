"""Versioned IPC action schema exported from the action catalog."""
from __future__ import annotations

from typing import Any, Dict

from netmedic.action_catalog import (
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    polkit_action_for,
)
from netmedic.config import Config

IPC_API_VERSION = "1.0"

_ACTION_PARAMS: Dict[str, Dict[str, str]] = {
    "change_dns": {"server": "optional string (default 1.1.1.1)"},
    "vpn_create_client": {"name": "required string"},
    "vpn_revoke_client": {"name": "required string"},
    "user_intent": {"user_request": "required string", "network_state": "optional object"},
}


def export_schema() -> Dict[str, Any]:
    """Return the machine-readable IPC contract for integrators."""
    actions: Dict[str, Any] = {}
    for name in sorted(PRIVILEGED_ACTIONS):
        actions[name] = {
            "tier": "privileged",
            "polkit_action": polkit_action_for(name),
            "requires": ["confirmed", "session_token", "polkit", "matching_peer_uid"],
            "params": _ACTION_PARAMS.get(name, {}),
        }
    for name in sorted(SAFE_ACTIONS):
        actions[name] = {
            "tier": "safe",
            "polkit_action": None,
            "requires": [],
            "params": _ACTION_PARAMS.get(name, {}),
        }
    return {
        "api_version": IPC_API_VERSION,
        "transport": "unix_stream",
        "framing": "newline_delimited_json",
        "socket_path": str(Config.get_state_dir() / "ipc.sock"),
        "actions": actions,
    }