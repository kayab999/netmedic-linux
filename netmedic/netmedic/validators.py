"""Single source of truth for network-identifier validation (M4).

Replaces four drifted DNS-regex copies (helper_verbs, network, ipc_actions,
netmedic_ai.param_validation) and three iface-name copies. stdlib only
(`ipaddress` + `re`) so the privileged helper can ship it under `-I`.

Rules (see audit M4):
- DNS: `ipaddress.IPv4Address`, strict. Unlike `re.match` + `$`, this
  rejects `"1.1.1.1\\n"`. Unlike the old octet regex, it also rejects
  leading-zero octets (`01.02.03.04`, ambiguous octal). IPv4-only by
  design (the stack configures `ipv4.dns`); IPv6 DNS is out of scope.
- Interface names: kernel charset, must not start with `-` (blocks `-h` /
  `--help` landing in an option slot of fixed root argv), max 15 chars
  (Linux IFNAMSIZ-1).
- Connection/profile names: same charset as before, must not start with
  `-`. Length cap unchanged (128): these are NM profile labels, not
  kernel ifnames.
"""
from __future__ import annotations

import ipaddress
import re

__all__ = [
    "ValidationError",
    "is_medic_iface",
    "validate_dns",
    "validate_iface",
    "validate_conn_name",
    "validate_client_name",
    "validate_service",
    "VPN_SERVICE_RE",
]

_IFACE_RE = re.compile(r"^[A-Za-z0-9._@+-]+$")
_MEDIC_IFACE_RE = re.compile(r"^medic[0-9a-f]{6}$")
_CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_CONN_NAME_RE = re.compile(r"^[A-Za-z0-9 ._@+-]{1,128}$")
VPN_SERVICE_RE = re.compile(r"^[A-Za-z0-9@._+-]+$")

MAX_IFACE_LEN = 15


class ValidationError(ValueError):
    """Invalid network identifier. Base for helper_verbs.VerbValidationError."""


def is_medic_iface(name: object) -> bool:
    """True only for NetMedic-owned dummy names (medic + 6 hex digits)."""
    return isinstance(name, str) and bool(_MEDIC_IFACE_RE.fullmatch(name))


def validate_dns(server: str) -> str:
    """Return the canonical IPv4 address or raise ValidationError."""
    if not isinstance(server, str):
        raise ValidationError("DNS server IP must be a string")
    try:
        addr = ipaddress.IPv4Address(server)
    except ipaddress.AddressValueError:
        raise ValidationError(f"Invalid DNS server IP: {server}") from None
    return str(addr)


def validate_iface(iface: str, *, medic_only: bool = False) -> str:
    """Return *iface* or raise ValidationError (leading dash, length)."""
    if not isinstance(iface, str) or not _IFACE_RE.fullmatch(iface):
        raise ValidationError(f"Invalid interface name: {iface!r}")
    if iface.startswith("-"):
        raise ValidationError(f"Invalid interface name: {iface!r}")
    if len(iface) > MAX_IFACE_LEN:
        raise ValidationError(f"Invalid interface name: {iface!r}")
    if medic_only and not _MEDIC_IFACE_RE.fullmatch(iface):
        raise ValidationError(f"Refusing non-medic interface: {iface!r}")
    return iface


def validate_conn_name(name: str) -> str:
    """Return an NM profile name or raise ValidationError."""
    if not isinstance(name, str) or not _CONN_NAME_RE.fullmatch(name):
        raise ValidationError(f"Invalid connection name: {name!r}")
    if name.startswith("-"):
        raise ValidationError(f"Invalid connection name: {name!r}")
    return name


def validate_client_name(name: str) -> str:
    """Return a VPN client name or raise ValidationError."""
    if not isinstance(name, str) or not _CLIENT_NAME_RE.fullmatch(name):
        raise ValidationError("Invalid client name (use a-z, 0-9, -, _)")
    return name


def validate_service(name: str) -> str:
    """Return an allowlisted OpenVPN unit name or raise ValidationError."""
    if not isinstance(name, str) or not VPN_SERVICE_RE.fullmatch(name):
        raise ValidationError(f"Invalid service name: {name!r}")
    # Allowlist: only OpenVPN server units. Prevents
    # `systemctl restart <arbitrary>` via the param path.
    if not (name.startswith("openvpn-server@") and name.endswith(".service")):
        raise ValidationError(
            f"Service not allowlisted (want openvpn-server@*.service): {name!r}"
        )
    return name
