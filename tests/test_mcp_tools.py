import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"


def _load_mcp_functions():
    """Load netmedic_mcp tool functions without requiring fastmcp."""
    mock_ipc = MagicMock()
    mock_fastmcp = ModuleType("fastmcp")

    class _FakeMCP:
        def __init__(self, _name):
            self._tools = {}

        def tool(self):
            def decorator(fn):
                self._tools[fn.__name__] = fn
                return fn
            return decorator

        def run(self):
            pass

    mock_fastmcp.FastMCP = _FakeMCP

    repo_root = str(TOOLS_DIR.parent)
    netmedic_pkg = str(Path(repo_root) / "netmedic")
    saved = sys.modules.copy()
    try:
        sys.modules["fastmcp"] = mock_fastmcp
        sys.path.insert(0, str(TOOLS_DIR))
        sys.path.insert(0, netmedic_pkg)
        sys.path.insert(0, repo_root)
        import importlib

        mcp = importlib.import_module("netmedic_mcp")
        mcp.ipc = mock_ipc
        return mcp, mock_ipc
    finally:
        for name in list(sys.modules):
            if name not in saved:
                del sys.modules[name]


def test_get_firewall_info_routes_ipc():
    mcp, mock_ipc = _load_mcp_functions()
    mock_ipc.is_available.return_value = True
    mock_ipc.request.return_value = {"status": "ok", "message": "ON"}

    result = mcp.get_firewall_info()
    assert "ON" in result
    mock_ipc.request.assert_called_once_with("firewall_status")


def test_create_vpn_blocked_without_mutating_flag():
    mcp, mock_ipc = _load_mcp_functions()
    env = os.environ.copy()
    env.pop("NETMEDIC_MCP_ALLOW_MUTATING", None)
    with patch.dict(os.environ, env, clear=True):
        result = mcp.create_vpn_client("test-client")
    assert "Blocked" in result
    mock_ipc.request.assert_not_called()