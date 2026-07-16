import json
import logging
import re
import subprocess
from typing import Any, Dict, List

from netmedic.system import CommandRunner

logger = logging.getLogger(__name__)

_VIRTUAL_IFACE_MARKERS = (
    "docker", "br-", "veth", "vnet", "virbr", "tun", "wg", "tailscale", "lo",
)


def _is_physical_interface(name: str) -> bool:
    return not any(marker in name for marker in _VIRTUAL_IFACE_MARKERS)


def _read_resolvers() -> List[str]:
    resolvers: List[str] = []
    try:
        proc = subprocess.run(
            ["resolvectl", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("DNS Servers:") or line.startswith("Current DNS Server:"):
                    for token in line.split(":", 1)[-1].split():
                        if re.match(r"^[\d.]+$", token) or ":" in token:
                            resolvers.append(token)
            if resolvers:
                return resolvers
    except (subprocess.SubprocessError, OSError):
        pass

    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        resolvers.append(parts[1])
    except OSError:
        pass
    return resolvers


def _vpn_status() -> Dict[str, Any]:
    active = CommandRunner.is_service_active("openvpn-server@server.service")
    if not active:
        active = CommandRunner.is_service_active("openvpn@server.service")
    return {
        "active": active,
        "provider": "openvpn" if active else "none",
    }


def _rfkill_blocked() -> bool:
    res = CommandRunner.run(["rfkill", "list", "wifi"])
    if not res.success:
        return False
    return "Soft blocked: yes" in res.stdout or "Hard blocked: yes" in res.stdout


def _nm_active_connection() -> Dict[str, str]:
    res = CommandRunner.run(["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "con", "show", "--active"])
    if not res.success or not res.stdout.strip():
        return {}
    line = res.stdout.splitlines()[0]
    parts = line.split(":")
    if len(parts) >= 3:
        return {"name": parts[0], "device": parts[1], "type": parts[2]}
    return {}


def get_network_snapshot() -> Dict[str, Any]:
    """Collect a compact network snapshot for AI and automation consumers."""
    snapshot: Dict[str, Any] = {
        "ifaces": {},
        "dns": [],
        "vpn": {"active": False, "provider": "none"},
        "latency_ms": 0.0,
        "internet": False,
        "default_iface": None,
        "gateway": None,
        "firewall": "unknown",
        "wifi_blocked": False,
        "nm_connection": {},
    }

    try:
        proc = subprocess.run(
            ["ip", "-j", "link"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        for iface in json.loads(proc.stdout):
            name = iface.get("ifname", "")
            if name:
                snapshot["ifaces"][name] = iface.get("operstate", "unknown")
    except Exception as exc:
        logger.error("Failed to collect interfaces: %s", exc)

    snapshot["dns"] = _read_resolvers()
    snapshot["vpn"] = _vpn_status()
    snapshot["wifi_blocked"] = _rfkill_blocked()
    snapshot["nm_connection"] = _nm_active_connection()

    route_res = CommandRunner.run(["ip", "route", "show", "default"])
    if route_res.success and route_res.stdout:
        parts = route_res.stdout.split()
        try:
            snapshot["gateway"] = parts[parts.index("via") + 1]
            snapshot["default_iface"] = parts[parts.index("dev") + 1]
        except (ValueError, IndexError):
            pass

    if not snapshot["default_iface"]:
        for name, state in snapshot["ifaces"].items():
            if state == "UP" and _is_physical_interface(name):
                snapshot["default_iface"] = name
                break

    try:
        ping_res = subprocess.run(
            ["ping", "-c", "1", "-W", "1", "8.8.8.8"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if ping_res.returncode == 0:
            snapshot["internet"] = True
            match = re.search(r"time[=<]([\d.]+)", ping_res.stdout)
            if match:
                snapshot["latency_ms"] = float(match.group(1))
    except (subprocess.SubprocessError, ValueError, OSError):
        pass

    try:
        from netmedic.network import NetworkMedic

        snapshot["firewall"] = NetworkMedic().get_firewall_status()
    except Exception:
        pass

    return snapshot