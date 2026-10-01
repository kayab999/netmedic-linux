"""Fixed-verb privileged helper: validation and argv templates (no elevation).

Phase B prototype for docs/PRIVILEGED_HELPER.md. Verbs own the root command
shape so callers cannot invent arbitrary elevated argv.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from netmedic.validators import (
    ValidationError as _ValidationError,
    validate_client_name as _validate_client_name,
    validate_conn_name as _validate_conn_name,
    validate_dns as _validate_dns,
    validate_iface as _validate_iface,
    validate_service as _validate_service,
)

# M8: single-sourced from action_catalog.ACTIONS. Re-exported here so
# existing `from netmedic.helper_verbs import IPC_TO_VERB, ALL_VERBS`
# imports (daemon, tests) keep working during the migration.
from netmedic.action_catalog import ALL_HELPER_VERBS as ALL_VERBS
from netmedic.action_catalog import IPC_TO_VERB as IPC_TO_VERB

__all__ = [
    "ALL_VERBS",
    "IPC_TO_VERB",
    "HELPER_VERSION",
    "INDEX_TXT_PATH",
    "DEFAULT_VPN_SERVICE",
    "PINNED_VPN_INSTALL_SHA256",
    "VPN_SCRIPT_IDS",
    "VPN_ALLOWED_ENV_KEYS",
    "VerbPlan",
    "VerbValidationError",
    "plan_verb",
    "plan_to_dict",
    "validate_iface",
    "validate_dns",
    "validate_client_name",
    "validate_conn_name",
    "validate_service",
]

INDEX_TXT_PATH = "/etc/openvpn/server/easy-rsa/pki/index.txt"
DEFAULT_VPN_SERVICE = "openvpn-server@server.service"

# F1: root-side trust anchor. Must match AngristanOperator.EXPECTED_SHA256.
# The helper never trusts caller-supplied hashes; plan_verb requires the
# caller value to equal this pin (transitional) and helper_main re-verifies
# staged bytes against it. Full script_id-only model (no path/hash from
# caller) is the follow-up once /usr/lib/netmedic/scripts ships the bundle.
PINNED_VPN_INSTALL_SHA256 = (
    "65c3b53f652615598696ec062a4d3106540c43666f2722108ecf62a4b87e2f5b"
)
VPN_SCRIPT_IDS: frozenset[str] = frozenset({"openvpn-install"})
# Angristan installer inputs only. No LD_*, PATH, PYTHON*, BASH_ENV, etc.
VPN_ALLOWED_ENV_KEYS: frozenset[str] = frozenset({
    "APPROVE_INSTALL",
    "APPROVE_IP",
    "IPV6_SUPPORT",
    "PORT_CHOICE",
    "PROTOCOL_CHOICE",
    "DNS",
    "COMPRESSION_ENABLED",
    "CUSTOMIZE_ENC",
    "MENU_OPTION",
    "CLIENT",
    "PASS",
})
HELPER_VERSION = "1.8.1"


@dataclass(frozen=True)
class VerbPlan:
    """Planned root command sequence for a verb."""

    verb: str
    commands: List[List[str]]
    message: str = ""


class VerbValidationError(_ValidationError):
    """Invalid verb name or arguments (subclass: except ValueError still works)."""


def _require_str(args: Mapping[str, Any], key: str, *, required: bool = True) -> Optional[str]:
    if key not in args or args[key] is None:
        if required:
            raise VerbValidationError(f"Missing required argument: {key}")
        return None
    value = args[key]
    if not isinstance(value, str):
        raise VerbValidationError(f"Argument '{key}' must be a string")
    return value


def _reraise_as_verb(fn: Callable[..., str], *args: Any, **kwargs: Any) -> str:
    try:
        return fn(*args, **kwargs)
    except _ValidationError as exc:
        raise VerbValidationError(str(exc)) from None


def validate_iface(iface: str, *, medic_only: bool = False) -> str:
    """Re-export of validators.validate_iface as VerbValidationError."""
    return _reraise_as_verb(_validate_iface, iface, medic_only=medic_only)


def validate_dns(server: str) -> str:
    """Re-export of validators.validate_dns as VerbValidationError."""
    return _reraise_as_verb(_validate_dns, server)


def validate_client_name(name: str) -> str:
    """Re-export of validators.validate_client_name as VerbValidationError."""
    return _reraise_as_verb(_validate_client_name, name)


def validate_conn_name(name: str) -> str:
    """Re-export of validators.validate_conn_name as VerbValidationError."""
    return _reraise_as_verb(_validate_conn_name, name)


def validate_service(name: str) -> str:
    """Re-export of validators.validate_service as VerbValidationError."""
    return _reraise_as_verb(_validate_service, name)


def _plan_flush_dns(verb: str, args: Dict[str, Any]) -> VerbPlan:
    return VerbPlan(verb, [["resolvectl", "flush-caches"]], "flush DNS caches")


def _plan_renew_ip(verb: str, args: Dict[str, Any]) -> VerbPlan:
    iface = validate_iface(_require_str(args, "iface") or "")
    mode = args.get("mode", "nmcli")
    if mode == "nmcli":
        return VerbPlan(
            verb,
            [["nmcli", "device", "reapply", iface]],
            f"renew IP via NetworkManager on {iface}",
        )
    if mode == "dhclient":
        return VerbPlan(
            verb,
            [
                ["dhclient", "-r", iface],
                ["dhclient", iface],
            ],
            f"renew IP via dhclient on {iface}",
        )
    raise VerbValidationError(f"Invalid renew mode: {mode!r}")


def _plan_change_dns(verb: str, args: Dict[str, Any]) -> VerbPlan:
    server = validate_dns(_require_str(args, "server") or "1.1.1.1")
    conn = validate_conn_name(_require_str(args, "connection") or "")
    return VerbPlan(
        verb,
        [
            [
                "nmcli",
                "con",
                "mod",
                conn,
                "ipv4.dns",
                server,
                "ipv4.ignore-auto-dns",
                "yes",
            ],
            ["nmcli", "con", "up", conn],
        ],
        f"set DNS {server} on {conn}",
    )


def _plan_restart_adapter(verb: str, args: Dict[str, Any]) -> VerbPlan:
    iface = validate_iface(_require_str(args, "iface") or "")
    return VerbPlan(
        verb,
        [
            ["ip", "link", "set", iface, "down"],
            ["ip", "link", "set", iface, "up"],
        ],
        f"cycle adapter {iface}",
    )


def _plan_reset_stack(verb: str, args: Dict[str, Any]) -> VerbPlan:
    return VerbPlan(
        verb,
        [["systemctl", "restart", "NetworkManager"]],
        "restart NetworkManager",
    )


def _plan_toggle_firewall(verb: str, args: Dict[str, Any]) -> VerbPlan:
    action = _require_str(args, "action") or ""
    if action == "enable":
        return VerbPlan(verb, [["ufw", "--force", "enable"]], "enable UFW")
    if action == "disable":
        return VerbPlan(verb, [["ufw", "disable"]], "disable UFW")
    raise VerbValidationError("toggle-firewall action must be 'enable' or 'disable'")


def _plan_vpn_list(verb: str, args: Dict[str, Any]) -> VerbPlan:
    # F2: fixed path only. index_path param removed — caller cannot pick
    # root-read paths (was startswith bypass: /etc/openvpn/../shadow).
    if "index_path" in args:
        raise VerbValidationError("vpn-list takes no path arguments (fixed PKI index)")
    return VerbPlan(verb, [["__vpn_list__"]], "read VPN PKI index")


def _plan_vpn_service(verb: str, args: Dict[str, Any]) -> VerbPlan:
    service = validate_service(
        _require_str(args, "service", required=False) or DEFAULT_VPN_SERVICE
    )
    unit_action = "start" if verb == "vpn-start-service" else "restart"
    return VerbPlan(
        verb,
        [["systemctl", unit_action, service]],
        f"{unit_action} {service}",
    )


def _validate_vpn_script_path(script: str) -> str:
    if ".." in script.split("/") or not script.startswith("/") or "//" in script:
        raise VerbValidationError("vpn-run-script requires an absolute script path")
    if os.path.normpath(script) != script:
        raise VerbValidationError("vpn-run-script path must be normalized")
    # NOTE: the normpath check subsumes the ".." check above; both layers
    # stay on purpose (defense in depth — proven equivalent by mutation testing).
    # Canonicalization is enforced at exec time via SHA256 sealed-copy re-hash
    # (helper_main re-hashes FD before exec); planning stage rejects tricks above.
    return script


def _validate_vpn_script_hash(expected_sha: str) -> str:
    # F1: caller hash is never trusted — must equal the root-side pin.
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise VerbValidationError("expected_sha256 must be 64 lowercase hex chars")
    if expected_sha != PINNED_VPN_INSTALL_SHA256:
        raise VerbValidationError(
            "expected_sha256 does not match pinned installer (see docs/VPN_REPIN.md)"
        )
    return PINNED_VPN_INSTALL_SHA256


def _validate_vpn_script_env(env: object) -> List[str]:
    if not isinstance(env, dict):
        raise VerbValidationError("env must be an object of string values")
    env_pairs: List[str] = []
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise VerbValidationError("env keys and values must be strings")
        if key not in VPN_ALLOWED_ENV_KEYS:
            raise VerbValidationError(f"env key not allowlisted for vpn-run-script: {key!r}")
        if "\n" in value or "\x00" in value or "=" in key:
            raise VerbValidationError(f"Invalid env value for {key}")
        # Values are passed as KEY=val to env(1); reject arg-split tricks.
        if value.startswith("-"):
            # Angristan values never start with '-'; blocks env flag injection
            # if a future refactor mishandles the argv split.
            raise VerbValidationError(f"Invalid env value for {key}")
        env_pairs.append(f"{key}={value}")
    return env_pairs


def _plan_vpn_run_script(verb: str, args: Dict[str, Any]) -> VerbPlan:
    script = _validate_vpn_script_path(_require_str(args, "script") or "")
    sealed_hash = _validate_vpn_script_hash(_require_str(args, "expected_sha256") or "")
    # F1: script_id forward-compat. Required going forward; defaults for
    # old callers during transition, but unknown IDs are rejected.
    script_id = args.get("script_id", "openvpn-install")
    if not isinstance(script_id, str) or script_id not in VPN_SCRIPT_IDS:
        raise VerbValidationError(f"Unknown script_id: {script_id!r}")
    env_pairs = _validate_vpn_script_env(args.get("env") or {})
    # Marker command: helper_main executes integrity + env script specially.
    # Hash emitted is always the pin, never the caller value verbatim
    # (they are equal by the check above, but pin is canonical).
    return VerbPlan(
        verb,
        [["__vpn_script__", script, sealed_hash, *env_pairs]],
        "run verified VPN installer script",
    )


def _plan_iface_del(verb: str, args: Dict[str, Any]) -> VerbPlan:
    iface = validate_iface(_require_str(args, "iface") or "", medic_only=True)
    return VerbPlan(verb, [["ip", "link", "del", iface]], f"delete {iface}")


def _plan_iface_add_dummy(verb: str, args: Dict[str, Any]) -> VerbPlan:
    iface = validate_iface(_require_str(args, "iface") or "", medic_only=True)
    return VerbPlan(
        verb,
        [["ip", "link", "add", iface, "type", "dummy"]],
        f"add dummy {iface}",
    )


# N2: verb → planner table (mirrors the M8.3 dispatcher pattern). Adding a
# verb = adding one planner here plus the ActionSpec row; plan_verb itself
# stays a thin lookup so its complexity no longer scales with verb count.
_VERB_PLANNERS: Dict[str, Callable[[str, Dict[str, Any]], VerbPlan]] = {
    "flush-dns": _plan_flush_dns,
    "renew-ip": _plan_renew_ip,
    "change-dns": _plan_change_dns,
    "restart-adapter": _plan_restart_adapter,
    "reset-stack": _plan_reset_stack,
    "toggle-firewall": _plan_toggle_firewall,
    "vpn-list": _plan_vpn_list,
    "vpn-start-service": _plan_vpn_service,
    "vpn-restart-service": _plan_vpn_service,
    "vpn-run-script": _plan_vpn_run_script,
    "iface-del": _plan_iface_del,
    "iface-add-dummy": _plan_iface_add_dummy,
}


def plan_verb(verb: str, args: Optional[Mapping[str, Any]] = None) -> VerbPlan:
    """Validate args and return the fixed argv sequence for *verb*.

    Does not execute anything. Raises VerbValidationError on bad input.
    """
    planner = _VERB_PLANNERS.get(verb)
    if planner is None:
        if verb not in ALL_VERBS:
            raise VerbValidationError(f"Unknown verb: {verb}")
        raise VerbValidationError(f"Unhandled verb: {verb}")
    return planner(verb, dict(args or {}))


def plan_to_dict(plan: VerbPlan, *, dry_run: bool = True) -> Dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry_run,
        "verb": plan.verb,
        "message": plan.message,
        "commands": plan.commands,
    }
