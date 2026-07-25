"""Fixed-verb privileged helper: validation and argv templates (no elevation).

Phase B prototype for docs/PRIVILEGED_HELPER.md. Verbs own the root command
shape so callers cannot invent arbitrary elevated argv.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Keep patterns aligned with network.py / operators.
_DNS_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_IFACE_RE = re.compile(r"^[A-Za-z0-9._@+-]+$")
_MEDIC_IFACE_RE = re.compile(r"^medic[0-9a-f]{6}$")
_CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_CONN_NAME_RE = re.compile(r"^[A-Za-z0-9 ._@+-]{1,128}$")
_SERVICE_RE = re.compile(r"^[A-Za-z0-9@._+-]+$")

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


@dataclass(frozen=True)
class VerbPlan:
    """Planned root command sequence for a verb."""

    verb: str
    commands: List[List[str]]
    message: str = ""


class VerbValidationError(ValueError):
    """Invalid verb name or arguments."""


def _require_str(args: Mapping[str, Any], key: str, *, required: bool = True) -> Optional[str]:
    if key not in args or args[key] is None:
        if required:
            raise VerbValidationError(f"Missing required argument: {key}")
        return None
    value = args[key]
    if not isinstance(value, str):
        raise VerbValidationError(f"Argument '{key}' must be a string")
    return value


def validate_iface(iface: str, *, medic_only: bool = False) -> str:
    if not _IFACE_RE.fullmatch(iface):
        raise VerbValidationError(f"Invalid interface name: {iface!r}")
    if medic_only and not _MEDIC_IFACE_RE.fullmatch(iface):
        raise VerbValidationError(f"Refusing non-medic interface: {iface!r}")
    return iface


def validate_dns(server: str) -> str:
    if not _DNS_IP_RE.fullmatch(server):
        raise VerbValidationError(f"Invalid DNS server IP: {server}")
    return server


def validate_client_name(name: str) -> str:
    if not _CLIENT_NAME_RE.fullmatch(name):
        raise VerbValidationError("Invalid client name (use a-z, 0-9, -, _)")
    return name


def validate_conn_name(name: str) -> str:
    if not _CONN_NAME_RE.fullmatch(name):
        raise VerbValidationError(f"Invalid connection name: {name!r}")
    return name


def validate_service(name: str) -> str:
    if not _SERVICE_RE.fullmatch(name):
        raise VerbValidationError(f"Invalid service name: {name!r}")
    return name


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
        path = args.get("index_path", INDEX_TXT_PATH)
        if not isinstance(path, str) or not path.startswith("/etc/openvpn/"):
            raise VerbValidationError("vpn-list index_path must be under /etc/openvpn/")
        return VerbPlan(verb, [["cat", path]], "read VPN PKI index")

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
        if ".." in script or not script.startswith("/"):
            raise VerbValidationError("vpn-run-script requires an absolute script path")
        expected_sha = _require_str(args, "expected_sha256") or ""
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise VerbValidationError("expected_sha256 must be 64 lowercase hex chars")
        env = args.get("env") or {}
        if not isinstance(env, dict):
            raise VerbValidationError("env must be an object of string values")
        env_pairs: List[str] = []
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise VerbValidationError("env keys and values must be strings")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise VerbValidationError(f"Invalid env key: {key!r}")
            if "\n" in value or "\x00" in value:
                raise VerbValidationError(f"Invalid env value for {key}")
            env_pairs.append(f"{key}={value}")
        # Marker command: helper_main executes integrity + env script specially.
        return VerbPlan(
            verb,
            [["__vpn_script__", script, expected_sha, *env_pairs]],
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
