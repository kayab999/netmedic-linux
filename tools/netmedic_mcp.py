#!/usr/bin/env python3
import logging
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_REPO_ROOT, "..", "netmedic"))
sys.path.insert(0, os.path.join(_REPO_ROOT, ".."))

from fastmcp import FastMCP
from netmedic.ipc_sync_client import SyncIPCClient

mcp = FastMCP("NetMedic")
ipc = SyncIPCClient()

MUTATING_ENV = "NETMEDIC_MCP_ALLOW_MUTATING"


def _mutating_allowed() -> bool:
    return os.environ.get(MUTATING_ENV, "").lower() in ("1", "true", "yes")


def _require_mutating(tool_name: str) -> str | None:
    if _mutating_allowed():
        return None
    return (
        f"Blocked: {tool_name} requires mutating access. "
        f"Set {MUTATING_ENV}=1 to enable privileged MCP tools."
    )


def _require_instance() -> str | None:
    if ipc.is_available():
        return None
    return (
        "NetMedic is not running. Start the GUI or run "
        "'netmedic --headless' before using MCP tools."
    )


def _ipc_message(result: dict) -> str:
    if result.get("status") == "ok":
        return result.get("message", "OK")
    return f"Error: {result.get('message', 'Unknown IPC error')}"


@mcp.tool()
def get_vpn_status() -> str:
    """Check if the VPN server (OpenVPN) is installed and running."""
    blocked = _require_instance()
    if blocked:
        return blocked
    res = ipc.request("vpn_status")
    if res.get("status") == "ok":
        return f"Status: {res.get('message')} | Details: {res.get('details') or 'None'}"
    return f"Error: {res.get('message')}"


@mcp.tool()
def list_vpn_clients() -> str:
    """List all configured VPN clients and their active status."""
    blocked = _require_instance()
    if blocked:
        return blocked
    res = ipc.request("vpn_list_clients")
    if res.get("status") != "ok":
        return f"Error: {res.get('message')} ({res.get('details') or 'None'})"

    clients = res.get("data", [])
    if not clients:
        return "No VPN clients found."

    output = ["Current VPN Clients:"]
    for client in clients:
        status = "Active" if client.get("active") else "Revoked"
        output.append(f"- {client.get('name')}: {status}")
    return "\n".join(output)


@mcp.tool()
def create_vpn_client(name: str) -> str:
    """Create a new VPN client profile (requires sudo)."""
    blocked = _require_mutating("create_vpn_client") or _require_instance()
    if blocked:
        return blocked
    res = ipc.request("vpn_create_client", {"name": name}, confirmed=True)
    return f"Result: {'OK' if res.get('status') == 'ok' else 'FAIL'} {res.get('message')}"


@mcp.tool()
def revoke_vpn_client(name: str) -> str:
    """Revoke an existing VPN client profile (requires sudo)."""
    blocked = _require_mutating("revoke_vpn_client") or _require_instance()
    if blocked:
        return blocked
    res = ipc.request("vpn_revoke_client", {"name": name}, confirmed=True)
    return f"Result: {'OK' if res.get('status') == 'ok' else 'FAIL'} {res.get('message')}"


@mcp.tool()
def get_network_status() -> str:
    """Check current connectivity status (Ping, DNS, Internet)."""
    blocked = _require_instance()
    if blocked:
        return blocked
    result = ipc.request("network_status")
    return _ipc_message(result)


@mcp.tool()
def smart_repair() -> str:
    """Run automated non-destructive repairs (DNS flush, IP renewal)."""
    blocked = _require_mutating("smart_repair") or _require_instance()
    if blocked:
        return blocked
    lines = [
        f"DNS Flush: {_ipc_message(ipc.request('flush_dns', confirmed=True))}",
        f"IP Renewal: {_ipc_message(ipc.request('renew_ip', confirmed=True))}",
    ]
    return "\n".join(lines)


@mcp.tool()
def flush_dns_cache() -> str:
    """Flush the system DNS cache (requires sudo)."""
    blocked = _require_mutating("flush_dns_cache") or _require_instance()
    if blocked:
        return blocked
    return _ipc_message(ipc.request("flush_dns", confirmed=True))


@mcp.tool()
def renew_dhcp_lease() -> str:
    """Renew the DHCP lease for the default interface (requires sudo)."""
    blocked = _require_mutating("renew_dhcp_lease") or _require_instance()
    if blocked:
        return blocked
    return _ipc_message(ipc.request("renew_ip", confirmed=True))


@mcp.tool()
def scan_wifi_congestion() -> str:
    """Scan nearby Wi-Fi networks and report congestion levels."""
    blocked = _require_instance()
    if blocked:
        return blocked
    return _ipc_message(ipc.request("wifi_diagnostics"))


@mcp.tool()
def reset_network_stack() -> str:
    """DESTRUCTIVE: Restart NetworkManager service (requires sudo)."""
    blocked = _require_mutating("reset_network_stack") or _require_instance()
    if blocked:
        return blocked
    return _ipc_message(ipc.request("reset_tcp_ip_stack", confirmed=True))


@mcp.tool()
def get_firewall_info() -> str:
    """Check if UFW firewall is active."""
    blocked = _require_instance()
    if blocked:
        return blocked
    from netmedic.network import NetworkMedic

    return f"Firewall Status: {NetworkMedic().get_firewall_status()}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()