"""Fixed-verb privileged helper: validation and argv templates (no elevation).

Phase B prototype for docs/PRIVILEGED_HELPER.md. Verbs own the root command
shape so callers cannot invent arbitrary elevated argv.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from netmedic.validators import (
    ValidationError as _ValidationError,
    validate_client_name as _validate_client_name,
    validate_conn_name as _validate_conn_name,
    validate_dns as _validate_dns,
    validate_iface as _validate_iface,
    validate_service as _validate_service,
)

# IPC action → helper verb
IPC_TO_VERB: Dict[str, str] = {
    "flush_dns": "flush-dns",
    "renew_ip": "renew-ip",
    "change_dns": "change-dns",
    "restart_adapter": "restart-adapter",
    "reset_tcp_ip_stack": "reset-stack",
    "toggle_firewall": "toggle-firewall",
    "vpn_list_clients": "vpn-list",
    "vpn_reconnect": "vpn-restart-service",
    "vpn_start_service": "vpn-start-service",
    "vpn_install": "vpn-run-script",
    "vpn_create_client": "vpn-run-script",
    "vpn_revoke_client": "vpn-run-script",
}

ALL_VERBS: frozenset[str] = frozenset({
    "flush-dns",
    "renew-ip",
    "change-dns",
    "restart-adapter",
    "reset-stack",
    "toggle-firewall",
    "vpn-list",
    "vpn-start-service",
    "vpn-restart-service",
    "vpn-run-script",
    "iface-del",
    "iface-add-dummy",
})

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
HELPER_VERSION = "1.6.4"


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


def _reraise_as_verb(fn, *args, **kwargs):
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


def plan_verb(verb: str, args: Optional[Mapping[str, Any]] = None) -> VerbPlan:
    """Validate args and return the fixed argv sequence for *verb*.

    Does not execute anything. Raises VerbValidationError on bad input.
    """
    if verb not in ALL_VERBS:
        raise VerbValidationError(f"Unknown verb: {verb}")
    args = dict(args or {})

    if verb == "flush-dns":
        return VerbPlan(verb, [["resolvectl", "flush-caches"]], "flush DNS caches")

    if verb == "renew-ip":
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

    if verb == "change-dns":
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

    if verb == "restart-adapter":
        iface = validate_iface(_require_str(args, "iface") or "")
        return VerbPlan(
            verb,
            [
                ["ip", "link", "set", iface, "down"],
                ["ip", "link", "set", iface, "up"],
            ],
            f"cycle adapter {iface}",
        )

    if verb == "reset-stack":
        return VerbPlan(
            verb,
            [["systemctl", "restart", "NetworkManager"]],
            "restart NetworkManager",
        )

    if verb == "toggle-firewall":
        action = _require_str(args, "action") or ""
        if action == "enable":
            return VerbPlan(verb, [["ufw", "--force", "enable"]], "enable UFW")
        if action == "disable":
            return VerbPlan(verb, [["ufw", "disable"]], "disable UFW")
        raise VerbValidationError("toggle-firewall action must be 'enable' or 'disable'")

    if verb == "vpn-list":
        # F2: fixed path only. index_path param removed — caller cannot pick
        # root-read paths (was startswith bypass: /etc/openvpn/../shadow).
        if "index_path" in args:
            raise VerbValidationError("vpn-list takes no path arguments (fixed PKI index)")
        return VerbPlan(verb, [["__vpn_list__"]], "read VPN PKI index")

    if verb in ("vpn-start-service", "vpn-restart-service"):
        service = validate_service(
            _require_str(args, "service", required=False) or DEFAULT_VPN_SERVICE
        )
        unit_action = "start" if verb == "vpn-start-service" else "restart"
        return VerbPlan(
            verb,
            [["systemctl", unit_action, service]],
            f"{unit_action} {service}",
        )

    if verb == "vpn-run-script":
        script = _require_str(args, "script") or ""
        import os as _os
        if ".." in script.split("/") or not script.startswith("/") or "//" in script:
            raise VerbValidationError("vpn-run-script requires an absolute script path")
        if _os.path.normpath(script) != script:
            raise VerbValidationError("vpn-run-script path must be normalized")
        # NOTE: the normpath check subsumes the ".." check above; both layers
        # stay on purpose (defense in depth — proven equivalent by mutation testing).
        # Canonicalization is enforced at exec time via SHA256 sealed-copy re-hash
        # (helper_main re-hashes FD before exec); planning stage rejects tricks above.
        # F1: caller hash is never trusted — must equal the root-side pin.
        expected_sha = _require_str(args, "expected_sha256") or ""
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise VerbValidationError("expected_sha256 must be 64 lowercase hex chars")
        if expected_sha != PINNED_VPN_INSTALL_SHA256:
            raise VerbValidationError(
                "expected_sha256 does not match pinned installer (see docs/VPN_REPIN.md)"
            )
        # F1: script_id forward-compat. Required going forward; defaults for
        # old callers during transition, but unknown IDs are rejected.
        script_id = args.get("script_id", "openvpn-install")
        if not isinstance(script_id, str) or script_id not in VPN_SCRIPT_IDS:
            raise VerbValidationError(f"Unknown script_id: {script_id!r}")
        env = args.get("env") or {}
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
        # Marker command: helper_main executes integrity + env script specially.
        # Hash emitted is always the pin, never the caller value verbatim
        # (they are equal by the check above, but pin is canonical).
        return VerbPlan(
            verb,
            [["__vpn_script__", script, PINNED_VPN_INSTALL_SHA256, *env_pairs]],
            "run verified VPN installer script",
        )

    if verb == "iface-del":
        iface = validate_iface(_require_str(args, "iface") or "", medic_only=True)
        return VerbPlan(verb, [["ip", "link", "del", iface]], f"delete {iface}")

    if verb == "iface-add-dummy":
        iface = validate_iface(_require_str(args, "iface") or "", medic_only=True)
        return VerbPlan(
            verb,
            [["ip", "link", "add", iface, "type", "dummy"]],
            f"add dummy {iface}",
        )

    raise VerbValidationError(f"Unhandled verb: {verb}")


def plan_to_dict(plan: VerbPlan, *, dry_run: bool = True) -> Dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry_run,
        "verb": plan.verb,
        "message": plan.message,
        "commands": plan.commands,
    }
