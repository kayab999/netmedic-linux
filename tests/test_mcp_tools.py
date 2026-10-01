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


def _allow_mutating(monkeypatch):
    monkeypatch.setenv("NETMEDIC_MCP_ALLOW_MUTATING", "1")


def _ok_response(message="ok", **kw):
    response = {"status": "ok", "success": True, "message": message, "code": "ok"}
    response.update(kw)
    return response


def test_smart_repair_uses_headless_service():
    """N1: smart_repair delegates to run_smart_repair, not a manual chain."""
    source_path = Path(__file__).resolve().parent.parent / "tools" / "netmedic_mcp.py"
    source = source_path.read_text(encoding="utf-8")
    assert "run_smart_repair" in source
    assert "RepairCallbacks.silent()" in source


def test_smart_repair_healthy_skips_elevation(monkeypatch):
    """Healthy network: SKIPPED renders success-with-note, no flush/renew."""
    _allow_mutating(monkeypatch)
    mcp, mock_ipc = _load_mcp_functions()
    mock_ipc.is_available.return_value = True
    healthy = _ok_response(
        "healthy",
        data={"gateway_ok": True, "dns_ok": True, "internet_ok": True},
    )
    mock_ipc.request.side_effect = lambda action, *a, **k: dict(healthy)
    result = mcp.smart_repair()
    assert "Healthy" in result
    called = [c.args[0] for c in mock_ipc.request.call_args_list]
    assert called == ["network_status", "network_status"]


def test_smart_repair_unhealthy_runs_full_flow(monkeypatch):
    """Unhealthy: diagnose, flush, renew, verify (post healthy)."""
    _allow_mutating(monkeypatch)
    mcp, mock_ipc = _load_mcp_functions()
    mock_ipc.is_available.return_value = True
    unhealthy = {
        "status": "error",
        "success": False,
        "message": "issues",
        "data": {"gateway_ok": True, "dns_ok": False, "internet_ok": False},
        "code": "failed",
    }
    healthy = _ok_response(
        "healthy",
        data={"gateway_ok": True, "dns_ok": True, "internet_ok": True},
    )
    executed = {"status": "ok", "success": True, "message": "done", "code": "executed"}
    calls = {"n": 0}

    def fake_request(action, *args, **kwargs):
        if action == "network_status":
            calls["n"] += 1
            return dict(healthy if calls["n"] > 1 else unhealthy)
        return dict(executed)

    mock_ipc.request.side_effect = fake_request
    result = mcp.smart_repair()
    assert "SUCCESS (verified)" in result
    called = [c.args[0] for c in mock_ipc.request.call_args_list]
    assert called == ["network_status", "flush_dns", "renew_ip", "network_status"]


def test_smart_repair_no_gateway_skips_renew(monkeypatch):
    """No gateway: flush only; renew skipped like the GUI flow."""
    _allow_mutating(monkeypatch)
    mcp, mock_ipc = _load_mcp_functions()
    mock_ipc.is_available.return_value = True
    no_gw = _ok_response(
        "no gateway",
        data={"gateway_ok": False, "dns_ok": False, "internet_ok": False},
        details={"gateway": None, "gateway_ok": False},
    )
    executed = {"status": "ok", "success": True, "message": "done", "code": "executed"}
    states = {"n": 0}

    def fake_request(action, *args, **kwargs):
        if action == "network_status":
            states["n"] += 1
            return dict(no_gw)
        return dict(executed)

    mock_ipc.request.side_effect = fake_request
    mcp.smart_repair()
    called = [c.args[0] for c in mock_ipc.request.call_args_list]
    assert "flush_dns" in called
    assert "renew_ip" not in called


def test_smart_repair_blocked_without_mutating_flag(monkeypatch):
    mcp, mock_ipc = _load_mcp_functions()
    mock_ipc.is_available.return_value = True
    env = os.environ.copy()
    env.pop("NETMEDIC_MCP_ALLOW_MUTATING", None)
    with patch.dict(os.environ, env, clear=True):
        result = mcp.smart_repair()
    assert "Blocked" in result
    mock_ipc.request.assert_not_called()