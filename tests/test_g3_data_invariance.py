"""G3: diagnostic facts must be invariant when optional tools are removed."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from netmedic.network import NetworkMedic


def _cmd(success, stdout=""):
    return MagicMock(success=success, stdout=stdout, stderr="", returncode=0 if success else 1)


def _native_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin native sources so run_diagnostics is fully hermetic."""
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [(socket.AF_INET, 0, 0, "", ("93.184.216.34", 0))])
    monkeypatch.setattr("socket.create_connection", lambda address, timeout=None: MagicMock())

    import netmedic.topology as topo
    import netmedic.rtnetlink as rtnl

    monkeypatch.setattr(topo, "collect_default_gateways_v4", lambda: [{"iface": "eth0", "gateway": "192.168.1.254", "metric": 100, "flags": 3}])
    monkeypatch.setattr(rtnl, "collect_default_routes", lambda: None)


def _run_router(monkeypatch, mapping):
    def _run(cmd, *a, **k):
        if not cmd:
            return _cmd(False)
        for prefix, result in mapping.items():
            if cmd[0] == prefix:
                return result
        return _cmd(False)

    monkeypatch.setattr("netmedic.system.CommandRunner.run", lambda cmd, *a, **k: _run(cmd, *a, **k))


def test_diagnostic_native_facts_invariant_to_tool_removal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing all optional tools must not change native diagnostic facts."""
    _native_mocks(monkeypatch)

    def router(cmd, *a, **k):
        if cmd and cmd[0] == "ip" and "default" in cmd:
            return _cmd(True, "default via 192.168.1.254 dev eth0")
        if cmd and cmd[0] == "ping":
            return _cmd(True)
        if cmd and cmd[0] == "nmcli":
            return _cmd(False)
        return _cmd(False)

    monkeypatch.setattr("netmedic.system.CommandRunner.run", lambda cmd, *a, **k: router(cmd, *a, **k))

    # Patch check_captive_portal to avoid real network.
    monkeypatch.setattr("netmedic.probes.check_captive_portal", lambda: (False, "no portal (200)"))
    monkeypatch.setattr("netmedic.probes._http_probe", lambda url, timeout=5.0: {
        "status": 200, "headers": {}, "body": "NetworkManager is online",
        "error": None, "tcp_ok": True, "http_ok": True, "tls_ok": None, "reason_code": "ok",
    })

    # Baseline with all tools present.
    monkeypatch.setattr("shutil.which", lambda _name: f"/usr/bin/{_name}")
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    baseline = NetworkMedic().run_diagnostics()

    # Remove all optional tools.
    monkeypatch.setattr("shutil.which", lambda _name: None)
    removed = NetworkMedic().run_diagnostics()

    # Native facts must be identical.
    assert baseline.details["per_probe"]["gw_ok"] == removed.details["per_probe"]["gw_ok"]
    assert baseline.details["per_probe"]["dns_ok"] == removed.details["per_probe"]["dns_ok"]
    assert baseline.details["per_probe"]["internet_ok"] == removed.details["per_probe"]["internet_ok"]
    assert baseline.details["per_probe"]["dns_per"] == removed.details["per_probe"]["dns_per"]
    # net_per native TCP keys must match (icmp is tool-dependent, excluded).
    baseline_tcp = {k: v for k, v in baseline.details["per_probe"]["net_per"].items() if "icmp" not in k}
    removed_tcp = {k: v for k, v in removed.details["per_probe"]["net_per"].items() if "icmp" not in k}
    assert baseline_tcp == removed_tcp
    assert baseline.code == removed.code