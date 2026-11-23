"""L0 hermetic tests: core must survive removal of optional tools."""
from __future__ import annotations

import shutil

import pytest

from netmedic.capabilities import AVAILABLE, UNAVAILABLE, collect_capabilities, DetectionContext
from netmedic.status import collect_status


def test_core_ready_with_all_tools_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    report = collect_status()
    assert report["core_ready"] is True
    assert report["overall_ok"] is True
    assert report["privileged_ready"] is False


def test_native_l0_capabilities_survive_tool_removal() -> None:
    ctx = DetectionContext(which=lambda _name: None)
    caps = {cap.id: cap for cap in collect_capabilities(ctx)}
    for cap_id in (
        "system_name_resolution",
        "tcp_connectivity",
        "http_tls_access",
        "captive_portal_hint",
        "default_route",
    ):
        assert caps[cap_id].availability == AVAILABLE, cap_id
    # Tool-backed L1 capabilities honestly become unavailable.
    for cap_id in ("networkmanager", "firewall_admin", "icmp_latency"):
        assert caps[cap_id].availability == UNAVAILABLE, cap_id