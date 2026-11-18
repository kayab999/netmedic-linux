"""Fixed-verb privileged helper: validation and argv templates (no elevation).

Phase B prototype for docs/PRIVILEGED_HELPER.md. Verbs own the root command
shape so callers cannot invent arbitrary elevated argv.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    "VPN_SCRIPT_PATHS",
    "VerbPlan",
    "VerbValidationError",
    "change_dns_apply_commands",
    "change_dns_restore_command",
    "change_dns_up_command",
    "plan_verb",
    "plan_to_dict",
    "restart_adapter_commands",
    "validate_iface",
    "validate_dns",
    "validate_client_name",
    "validate_conn_name",
    "validate_service",
]

INDEX_TXT_PATH = "/etc/openvpn/server/easy-rsa/pki/index.txt"
DEFAULT_VPN_SERVICE = "openvpn-server@server.service"

# F2: vendored, root-owned installer. The pin is the SHA256 of the exact
# file shipped in the repository (netmedic/data/vpn/openvpn-install.sh) and
# installed to the fixed path below. Callers name the script by id only:
# neither the path nor the hash is accepted from the daemon anymore.
PINNED_VPN_INSTALL_SHA256 = (
    "e0ac8731423204c671f7699003e9fb6f191be77ae15ca8e5a28031f498947a07"
)
VPN_SCRIPT_PATHS: Dict[str, str] = {
    "openvpn-install": "/usr/lib/netmedic/scripts/openvpn-install.sh",
}
VPN_SCRIPT_IDS: frozenset[str] = frozenset(VPN_SCRIPT_PATHS)

# Closed enum of DNS providers accepted by the vendored installer (see
# docs/VPN_CONTRACT.md). Validated both in the planner and root-side.
VPN_DNS_PROVIDERS: frozenset[str] = frozenset({
    "system", "unbound", "cloudflare", "quad9", "quad9-uncensored",
    "fdn", "dnswatch", "opendns", "google", "yandex", "adguard",
    "nextdns", "custom",
})
VPN_PROTOCOLS: frozenset[str] = frozenset({"udp", "tcp"})
HELPER_VERSION = "1.9.0"


@dataclass(frozen=True)
class VerbPlan:
    """Planned root command sequence for a verb.

    ``params`` holds the already-validated structured values the executor
    needs (connection/server/interface).  The executor must never recover
    them by slicing ``commands``: the dry-run and the executed argv have to
    come from the same source.
    """

    verb: str
    commands: List[List[str]]
    message: str = ""
    params: Mapping[str, str] = field(default_factory=dict)


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


def change_dns_apply_commands(conn: str, server: str) -> List[List[str]]:
    """Single source of truth for the change-dns apply argv (dry-run == exec)."""
    return [
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
    ]


def change_dns_restore_command(conn: str, dns: str, ignore_auto_dns: str) -> List[str]:
    """Rollback argv; built from the pre-change snapshot, never from callers."""
    return [
        "nmcli",
        "con",
        "mod",
        conn,
        "ipv4.dns",
        dns,
        "ipv4.ignore-auto-dns",
        ignore_auto_dns,
    ]


def change_dns_up_command(conn: str) -> List[str]:
    return ["nmcli", "con", "up", conn]


def restart_adapter_commands(iface: str) -> List[List[str]]:
    """Single source of truth for the restart-adapter apply argv."""
    return [
        ["ip", "link", "set", iface, "down"],
        ["ip", "link", "set", iface, "up"],
    ]


def _plan_change_dns(verb: str, args: Dict[str, Any]) -> VerbPlan:
    server = validate_dns(_require_str(args, "server") or "1.1.1.1")
    conn = validate_conn_name(_require_str(args, "connection") or "")
    return VerbPlan(
        verb,
        change_dns_apply_commands(conn, server),
        f"set DNS {server} on {conn}",
        {"connection": conn, "server": server},
    )


def _plan_restart_adapter(verb: str, args: Dict[str, Any]) -> VerbPlan:
    iface = validate_iface(_require_str(args, "iface") or "")
    return VerbPlan(
        verb,
        restart_adapter_commands(iface),
        f"cycle adapter {iface}",
        {"iface": iface},
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


def _require_int(args: Mapping[str, Any], key: str, *, lo: int, hi: int) -> int:
    if key not in args or args[key] is None:
        raise VerbValidationError(f"Missing required argument: {key}")
    value = args[key]
    if isinstance(value, bool) or not isinstance(value, int):
        # Accept a decimal string for JSON callers that stringify numbers.
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        else:
            raise VerbValidationError(f"Argument '{key}' must be an integer")
    if not (lo <= value <= hi):
        raise VerbValidationError(f"Argument '{key}' out of range [{lo}, {hi}]")
    return int(value)


def _require_choice(args: Mapping[str, Any], key: str, allowed: frozenset[str]) -> str:
    value = _require_str(args, key) or ""
    if value not in allowed:
        raise VerbValidationError(
            f"Argument '{key}' must be one of {sorted(allowed)!r}, got {value!r}"
        )
    return value


def _plan_vpn_install(verb: str, args: Dict[str, Any]) -> VerbPlan:
    # F3: typed verb. No caller env dict, no script path/hash.
    for forbidden in ("script", "expected_sha256", "script_id", "env"):
        if forbidden in args:
            raise VerbValidationError(f"vpn-install does not accept '{forbidden}'")
    port = 1194
    if "port" in args and args.get("port") is not None:
        port = _require_int(args, "port", lo=1, hi=65535)
    protocol = "udp"
    if "protocol" in args and args.get("protocol") is not None:
        protocol = _require_choice(args, "protocol", VPN_PROTOCOLS)
    dns = "cloudflare"
    if "dns" in args and args.get("dns") is not None:
        dns = _require_choice(args, "dns", VPN_DNS_PROVIDERS)
    client_ipv6 = args.get("client_ipv6", False)
    if not isinstance(client_ipv6, bool):
        raise VerbValidationError("Argument 'client_ipv6' must be a boolean")
    client = args.get("client", "client")
    if client is None:
        client = "client"
    client = validate_client_name(str(client))
    flags = ["--port", str(port), "--protocol", protocol, "--dns", dns]
    flags.append("--client-ipv6" if client_ipv6 else "--no-client-ipv6")
    flags += ["--client", client]
    return VerbPlan(verb, [["__vpn_cli__", "install", *flags]], "install OpenVPN server")


def _plan_vpn_add_client(verb: str, args: Dict[str, Any]) -> VerbPlan:
    for forbidden in ("script", "expected_sha256", "script_id", "env", "password"):
        if forbidden in args:
            raise VerbValidationError(f"vpn-add-client does not accept '{forbidden}'")
    name = validate_client_name(_require_str(args, "name") or "")
    flags = ["client", "add", name]
    return VerbPlan(verb, [["__vpn_cli__", *flags]], "add VPN client")


def _plan_vpn_revoke_client(verb: str, args: Dict[str, Any]) -> VerbPlan:
    for forbidden in ("script", "expected_sha256", "script_id", "env"):
        if forbidden in args:
            raise VerbValidationError(f"vpn-revoke-client does not accept '{forbidden}'")
    name = validate_client_name(_require_str(args, "name") or "")
    return VerbPlan(
        verb,
        [["__vpn_cli__", "client", "revoke", name, "--force"]],
        "revoke VPN client",
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
    "vpn-install": _plan_vpn_install,
    "vpn-add-client": _plan_vpn_add_client,
    "vpn-revoke-client": _plan_vpn_revoke_client,
    "vpn-start-service": _plan_vpn_service,
    "vpn-restart-service": _plan_vpn_service,
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
        "params": dict(plan.params),
        "commands": plan.commands,
    }
