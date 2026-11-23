"""LUCP Phase 1: capability registry and scope tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from netmedic.action_catalog import ACTIONS
from netmedic.capabilities import (
    AVAILABLE,
    AVAILABILITIES,
    LEVEL_L0,
    LEVEL_L1,
    LEVEL_L2,
    NOT_ATTEMPTED,
    REASON_HELPER_NOT_INSTALLED,
    REASON_POLKIT_PROBE_UNAVAILABLE,
    REASON_TOOL_NOT_FOUND,
    SCHEMA_VERSION,
    UNKNOWN,
    UNAVAILABLE,
    Capability,
    DetectionContext,
    collect_capabilities,
    collect_scope,
)

EXPECTED_PRIVILEGED = sum(1 for spec in ACTIONS if spec.polkit_id and spec.ipc_action)


def _ctx(**overrides):
    values = dict(
        which=lambda _name: None,
        helper_installed=False,
        helper_enabled=False,
        pkexec_present=False,
        polkit_probe_ok=False,
        polkit_actions=frozenset(),
    )
    values.update(overrides)
    return DetectionContext(**values)


def test_schema_and_state_vocabulary():
    assert SCHEMA_VERSION
    assert {AVAILABLE, UNKNOWN, UNAVAILABLE} == AVAILABILITIES
    assert NOT_ATTEMPTED == "NOT_ATTEMPTED"
    assert LEVEL_L0 != LEVEL_L1 != LEVEL_L2


def test_capability_rejects_unknown_states():
    with pytest.raises(ValueError):
        Capability(id="x", level=LEVEL_L0, availability="MAYBE")
    with pytest.raises(ValueError):
        Capability(id="x", level="L9", availability=AVAILABLE)
    with pytest.raises(ValueError):
        Capability(id="x", level=LEVEL_L0, availability=AVAILABLE, outcome="DONE")
    with pytest.raises(ValueError):
        Capability(id="not snake case", level=LEVEL_L0, availability=AVAILABLE)


def test_missing_tools_are_unavailable_not_unknown():
    caps = {cap.id: cap for cap in collect_capabilities(_ctx())}
    for cap_id in (
        "interface_inventory",
        "networkmanager",
        "firewall_admin",
    ):
        assert caps[cap_id].availability == UNAVAILABLE
        assert caps[cap_id].reason_code == REASON_TOOL_NOT_FOUND
        assert caps[cap_id].outcome == NOT_ATTEMPTED


def test_tools_present_are_available_with_backend():
    ctx = _ctx(which=lambda name: f"/usr/bin/{name}")
    caps = {cap.id: cap for cap in collect_capabilities(ctx)}
    assert caps["networkmanager"].availability == AVAILABLE
    assert caps["networkmanager"].backend == "networkmanager"
    assert caps["tcp_connectivity"].availability == AVAILABLE
    assert caps["tcp_connectivity"].backend == "native"


def test_privileged_capabilities_cover_every_polkit_action():
    caps = collect_capabilities(_ctx())
    privileged = [cap for cap in caps if cap.level == LEVEL_L2]
    assert len(privileged) == EXPECTED_PRIVILEGED == 12
    assert {cap.id for cap in privileged} == {
        f"privileged_{spec.ipc_action}"
        for spec in ACTIONS
        if spec.polkit_id and spec.ipc_action
    }
    assert all(cap.availability == UNAVAILABLE for cap in privileged)
    assert all(cap.reason_code == REASON_HELPER_NOT_INSTALLED for cap in privileged)


def test_inconclusive_polkit_probe_is_unknown_not_unavailable():
    ctx = _ctx(
        helper_installed=True,
        helper_enabled=True,
        pkexec_present=True,
        polkit_probe_ok=False,
    )
    caps = {cap.id: cap for cap in collect_capabilities(ctx)}
    assert caps["privileged_flush_dns"].availability == UNKNOWN
    assert caps["privileged_flush_dns"].reason_code == REASON_POLKIT_PROBE_UNAVAILABLE


def test_all_privileged_capabilities_available_when_registered():
    actions = frozenset(
        spec.polkit_id for spec in ACTIONS if spec.polkit_id is not None
    )
    ctx = _ctx(
        helper_installed=True,
        helper_enabled=True,
        pkexec_present=True,
        polkit_probe_ok=True,
        polkit_actions=actions,
    )
    caps = collect_capabilities(ctx)
    privileged = [cap for cap in caps if cap.level == LEVEL_L2]
    assert all(cap.availability == AVAILABLE for cap in privileged)
    assert all(cap.reason_code is None for cap in privileged)


def test_capability_report_is_json_serializable_and_unique():
    ctx = _ctx(which=lambda name: f"/usr/bin/{name}")
    caps = collect_capabilities(ctx)
    payload = json.dumps([cap.to_dict() for cap in caps], sort_keys=True)
    assert payload
    ids = [cap.id for cap in caps]
    assert len(ids) == len(set(ids))
    assert "password" not in payload.lower()
    assert "session_token" not in payload


def test_collect_scope_reads_namespace_and_container_hint(tmp_path: Path):
    ns_link = tmp_path / "netns"
    os.symlink("net:[4026531840]", ns_link)
    marker = tmp_path / ".dockerenv"
    marker.write_text("", encoding="utf-8")
    cgroup = tmp_path / "cgroup"
    cgroup.write_text("12:net_cls,net_prio:/kubepods/burstable/pod1\n", encoding="utf-8")

    scope = collect_scope(
        ns_link=str(ns_link),
        cgroup_path=str(cgroup),
        marker_paths=(str(marker),),
    )

    assert scope.network_namespace == "net:[4026531840]"
    assert scope.container_hint is True
    assert str(marker) in scope.container_sources
    assert "cgroup:kubepods" in scope.container_sources
    assert scope.label == "current network namespace"


def test_collect_scope_missing_sources_is_unknown_not_host_claim(tmp_path: Path):
    scope = collect_scope(
        ns_link=str(tmp_path / "missing"),
        cgroup_path=str(tmp_path / "missing-cgroup"),
        marker_paths=(str(tmp_path / "missing-marker"),),
    )
    assert scope.network_namespace is None
    assert scope.container_hint is False
    assert scope.container_sources == ()
    assert "host" not in scope.label
