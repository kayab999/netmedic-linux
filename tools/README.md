# Optional Tools

## MCP Server (`netmedic_mcp.py`)

Exposes NetMedic operations as MCP tools for AI assistant integration.

**Requirements:** `pip install fastmcp`

```bash
PYTHONPATH="netmedic:." python tools/netmedic_mcp.py
```

Available tools: VPN status/clients, network diagnostics, DNS flush, DHCP renewal, Wi-Fi scan, firewall status.