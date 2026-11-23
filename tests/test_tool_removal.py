"""L0 hermetic tests: core must survive removal of optional tools."""
from __future__ import annotations

import shutil

import pytest

from netmedic.capabilities import AVAILABLE, UNAVAILABLE, collect_capabilities, DetectionContext
from netmedic.status import collect_status


OPTIONAL_TOOLS = ["nmcli", "ip", "curl", "getent", "ping", "resolvectl", "dhclient", "ufw"]


def test_core_ready_with_all_tools_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    report = collect_status()
    assert report["core_ready"] is True
    assert report["overall_ok"] is True
    assert report["privileged_ready"] is False


@pytest.mark.parametrize("tool", OPTIONAL_TOOLS)
def test_core_ready_survives_single_tool_removal(
    tool: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing any single optional tool must not break core_ready."""
    real_which = shutil.which

    def fake_which(name: str):
        if name == tool:
            return None
        return real_which(name)

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr("netmedic.status.shutil.which", fake_which)
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    report = collect_status()
    assert report["core_ready"] is True, f"core_ready broke when {tool} was removed"
    assert report["overall_ok"] is True


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
    for cap_id in ("networkmanager", "firewall_admin", "icmp_latency"):
        assert caps[cap_id].availability == UNAVAILABLE, cap_id


def test_native_facts_unchanged_when_tools_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Native facts must be identical with and without optional tools."""
    from netmedic.capabilities import collect_capabilities, DetectionContext

    baseline_ctx = DetectionContext(which=lambda _name: f"/usr/bin/{_name}")
    baseline = {
        c.id: c.availability for c in collect_capabilities(baseline_ctx) if c.backend == "native"
    }

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    removed_ctx = DetectionContext(which=lambda _name: None)
    removed = {
        c.id: c.availability for c in collect_capabilities(removed_ctx) if c.backend == "native"
    }
    assert removed == baseline, "native capabilities changed when tools were removed"