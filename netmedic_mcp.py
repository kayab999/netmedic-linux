#!/home/carlos/ockhamRazr/.venv/bin/python3
import sys
import os
# Add netmedic to path so we can import it BEFORE from netmedic import ...
sys.path.append(os.path.join(os.path.dirname(__file__), "netmedic"))

import logging
from fastmcp import FastMCP
from netmedic.network import NetworkMedic
from netmedic.operators.wifi import WifiOperator
from netmedic.operators.vpn.angristan import AngristanOperator

# Initialize MCP Server
mcp = FastMCP("NetMedic")
medic = NetworkMedic()
wifi_op = WifiOperator()
vpn_op = AngristanOperator()

@mcp.tool()
def get_vpn_status() -> str:
    """Check if the VPN server (OpenVPN) is installed and running."""
    res = vpn_op.check_status()
    return f"Status: {res.message} | Details: {res.details or 'None'}"

@mcp.tool()
def list_vpn_clients() -> str:
    """List all configured VPN clients and their active status."""
    res = vpn_op.list_clients()
    if not res.success:
        return f"Error: {res.message} ({res.details})"
    
    clients = res.data
    if not clients:
        return "No VPN clients found."
    
    output = ["Current VPN Clients:"]
    for c in clients:
        status = "✅ Active" if c.active else "❌ Revoked"
        output.append(f"- {c.name}: {status}")
    return "\n".join(output)

@mcp.tool()
def create_vpn_client(name: str) -> str:
    """Create a new VPN client profile (requires sudo)."""
    res = vpn_op.add_client(name)
    return f"Result: {'✅' if res.success else '❌'} {res.message}"

@mcp.tool()
def revoke_vpn_client(name: str) -> str:
    """Revoke an existing VPN client profile (requires sudo)."""
    res = vpn_op.revoke_client(name)
    return f"Result: {'✅' if res.success else '❌'} {res.message}"

@mcp.tool()
def get_network_status() -> str:
    """Check current connectivity status (Ping, DNS, Internet)."""
    res = medic.run_diagnostics()
    return f"Status: {'✅ OK' if res.success else '❌ ISSUE'} | Details: {res.message}"

@mcp.tool()
def smart_repair() -> str:
    """Run automated non-destructive repairs (DNS flush, IP renewal)."""
    results = []
    results.append(f"DNS Flush: {medic.flush_dns().message}")
    results.append(f"IP Renewal: {medic.renew_ip().message}")
    return "\n".join(results)

@mcp.tool()
def flush_dns_cache() -> str:
    """Flush the system DNS cache (requires sudo)."""
    res = medic.flush_dns()
    return f"Result: {'✅' if res.success else '❌'} {res.message}"

@mcp.tool()
def renew_dhcp_lease() -> str:
    """Renew the DHCP lease for the default interface (requires sudo)."""
    res = medic.renew_ip()
    return f"Result: {'✅' if res.success else '❌'} {res.message}"

@mcp.tool()
def scan_wifi_congestion() -> str:
    """Scan nearby Wi-Fi networks and report congestion levels."""
    res = wifi_op.scan_congestion()
    return f"Result: {'✅' if res.success else '❌'} {res.message}"

@mcp.tool()
def reset_network_stack() -> str:
    """RESTRUCTIVE: Restart NetworkManager service (requires sudo). Use only if connectivity is lost."""
    res = medic.reset_tcp_ip_stack()
    return f"Result: {'✅' if res.success else '❌'} {res.message}"

@mcp.tool()
def get_firewall_info() -> str:
    """Check if UFW firewall is active."""
    status = medic.get_firewall_status()
    return f"Firewall Status: {status}"

if __name__ == "__main__":
    mcp.run()
