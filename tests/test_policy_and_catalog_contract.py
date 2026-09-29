"""Contract: privileged IPC actions ↔ polkit IDs ↔ helper verbs ↔ policy XML."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from netmedic.action_catalog import (
    ACTIONS,
    DISRUPTIVE_ACTIONS,
    IPC_TO_VERB,
    POLKIT_ACTION_IDS,
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    is_privileged,
    polkit_action_for,
)
from netmedic.helper_verbs import ALL_VERBS

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "assets" / "com.kayab.netmedic.policy"
HELPER_PATH = "/usr/libexec/netmedic/helper"


def test_privileged_and_safe_disjoint():
    assert PRIVILEGED_ACTIONS.isdisjoint(SAFE_ACTIONS)


def test_every_privileged_has_polkit_and_reverse():
    for action in PRIVILEGED_ACTIONS:
        assert polkit_action_for(action) is not None
        assert polkit_action_for(action) in POLKIT_ACTION_IDS.values()
    assert set(POLKIT_ACTION_IDS) == set(PRIVILEGED_ACTIONS)


def test_ipc_to_verb_covers_all_privileged_except_pure_meta():
    # Every privileged IPC action that elevates system state must map to a verb.
    for action in PRIVILEGED_ACTIONS:
        assert action in IPC_TO_VERB, f"missing IPC_TO_VERB for {action}"
        verb = IPC_TO_VERB[action]
        assert verb in ALL_VERBS, f"verb {verb} for {action} not in ALL_VERBS"


def test_policy_xml_well_formed_and_annotated():
    assert POLICY.is_file()
    tree = ET.parse(POLICY)
    root = tree.getroot()
    # ElementTree may expand or keep Clark notation depending on version.
    actions = []
    for elem in root.iter():
        if elem.tag.endswith("action") or elem.tag == "action":
            actions.append(elem)

    policy_ids = {a.get("id") for a in actions if a.get("id")}
    expected_ids = set(POLKIT_ACTION_IDS.values())
    assert expected_ids.issubset(policy_ids), (
        f"policy missing actions: {expected_ids - policy_ids}"
    )

    # F4: helper verb per polkit action (pkexec disambiguates by argv1).
    # Reverse map: polkit ID -> helper verb via IPC_TO_VERB.
    id_to_verb = {}
    for ipc_action, polkit_id in POLKIT_ACTION_IDS.items():
        id_to_verb[polkit_id] = IPC_TO_VERB[ipc_action]
    # M8: retention expectations come from the table, not a hardcoded list.
    # High-risk verbs must not use auth_admin_keep (no retention window).
    no_keep_ids = {
        spec.polkit_id for spec in ACTIONS
        if spec.polkit_id is not None and not spec.keep_auth
    }
    keep_ids = {
        spec.polkit_id for spec in ACTIONS
        if spec.polkit_id is not None and spec.keep_auth
    }

    for action_el in actions:
        action_id = action_el.get("id")
        if action_id not in expected_ids:
            continue
        annot = {}
        allow_active = None
        for child in action_el:
            tag = child.tag
            if tag.endswith("annotate") or tag == "annotate":
                key = child.get("key") or ""
                annot[key] = (child.text or "").strip()
            if tag.endswith("defaults") or tag == "defaults":
                for d in child:
                    if d.tag.endswith("allow_active") or d.tag == "allow_active":
                        allow_active = (d.text or "").strip()
        assert HELPER_PATH in annot.get("org.freedesktop.policykit.exec.path", ""), (
            f"{action_id} missing exec.path annotate → {HELPER_PATH}"
        )
        # F4: argv1 must equal the helper verb for this action.
        expected_verb = id_to_verb[action_id]
        assert annot.get("org.freedesktop.policykit.exec.argv1") == expected_verb, (
            f"{action_id} missing/incorrect exec.argv1 (want {expected_verb})"
        )
        if action_id in no_keep_ids:
            assert allow_active == "auth_admin", f"{action_id} must use auth_admin (no keep)"
        elif action_id in keep_ids:
            assert allow_active == "auth_admin_keep", f"{action_id} must use auth_admin_keep"


def test_action_table_self_consistent():
    """M8: the ACTIONS table upholds every invariant the legacy sets had."""
    seen_ipc = [s.ipc_action for s in ACTIONS if s.ipc_action is not None]
    assert len(seen_ipc) == len(set(seen_ipc)), "duplicate ipc_action rows"
    seen_polkit = [s.polkit_id for s in ACTIONS if s.polkit_id is not None]
    assert len(seen_polkit) == len(set(seen_polkit)), "duplicate polkit_id rows"
    for spec in ACTIONS:
        if spec.tier == "privileged":
            assert spec.ipc_action and spec.helper_verb and spec.polkit_id, spec
        elif spec.tier == "safe":
            assert spec.helper_verb is None and spec.polkit_id is None, spec
        elif spec.tier == "internal":
            assert spec.ipc_action is None and spec.polkit_id is None, spec
        else:
            raise AssertionError(f"unknown tier: {spec}")
    # Derived names match the table (single-source proof).
    assert set(PRIVILEGED_ACTIONS) == {s.ipc_action for s in ACTIONS if s.tier == "privileged"}
    assert set(SAFE_ACTIONS) == {s.ipc_action for s in ACTIONS if s.tier == "safe"}
    assert set(IPC_TO_VERB.items()) == {
        (s.ipc_action, s.helper_verb) for s in ACTIONS
        if s.ipc_action is not None and s.helper_verb is not None
    }
    assert set(DISRUPTIVE_ACTIONS) == {
        s.ipc_action for s in ACTIONS if s.disruptive
    }
    # keep_auth distribution is intentional: 4 low-impact keep, 8 re-prompt.
    keep = {s.polkit_id for s in ACTIONS if s.polkit_id is not None and s.keep_auth}
    no_keep = {s.polkit_id for s in ACTIONS if s.polkit_id is not None and not s.keep_auth}
    assert len(keep) == 4
    assert len(no_keep) == 8


def test_generated_policy_matches_asset():
    """M8: the checked-in policy XML is exactly what the table generates."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_policy.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"policy drifted from table: {proc.stdout}{proc.stderr}"


def test_is_privileged_matches_set():
    for action in PRIVILEGED_ACTIONS:
        assert is_privileged(action)
    for action in SAFE_ACTIONS:
        assert not is_privileged(action)
