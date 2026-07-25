"""Contract: privileged IPC actions ↔ polkit IDs ↔ helper verbs ↔ policy XML."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from netmedic.action_catalog import (
    POLKIT_ACTION_IDS,
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    is_privileged,
    polkit_action_for,
)
from netmedic.helper_verbs import ALL_VERBS, IPC_TO_VERB

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

    for action_el in actions:
        action_id = action_el.get("id")
        if action_id not in expected_ids:
            continue
        annot_paths = []
        for child in action_el:
            if not (child.tag.endswith("annotate") or child.tag == "annotate"):
                continue
            key = child.get("key") or ""
            if key.endswith("exec.path") or key == "org.freedesktop.policykit.exec.path":
                annot_paths.append((child.text or "").strip())
        assert HELPER_PATH in annot_paths, (
            f"{action_id} missing exec.path annotate → {HELPER_PATH}"
        )


def test_is_privileged_matches_set():
    for action in PRIVILEGED_ACTIONS:
        assert is_privileged(action)
    for action in SAFE_ACTIONS:
        assert not is_privileged(action)
