"""Four-way contract guardian (H-5): IPC schema ↔ action catalog ↔ polkit
policy XML ↔ VERBS.md registry. One test proves all four stay in sync;
pairwise guardians live in test_verbs_doc / test_policy_and_catalog_contract.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from netmedic.action_catalog import (
    POLKIT_ACTION_IDS,
    PRIVILEGED_ACTIONS,
    SAFE_ACTIONS,
    polkit_action_for,
)
from netmedic.ipc_schema import IPC_API_VERSION, export_schema

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "assets" / "com.kayab.netmedic.policy"


def _verbs_registry():
    text = (REPO / "VERBS.md").read_text(encoding="utf-8")
    assert "<!-- netmedic:verbs-registry v1 -->" in text
    m = re.search(r"<!-- netmedic:verbs-registry v1 -->\s*```json\s*\n(.*?)\n```", text, re.DOTALL)
    assert m, "anchored registry block missing"
    return json.loads(m.group(1))


def test_four_way_consistency():
    schema = export_schema()
    assert schema["api_version"] == IPC_API_VERSION
    assert set(schema["actions"]) == set(PRIVILEGED_ACTIONS) | set(SAFE_ACTIONS)

    tree = ET.parse(POLICY)
    policy_ids = {
        el.get("id") for el in tree.getroot().iter() if (el.tag.endswith("action") or el.tag == "action") and el.get("id")
    }

    registry = _verbs_registry()
    doc_priv = {r["ipc_action"] for r in registry if r.get("ipc_action") and r.get("catalog") == "privileged"}
    doc_safe = {r["ipc_action"] for r in registry if r.get("ipc_action") and r.get("catalog") == "safe"}

    for action in PRIVILEGED_ACTIONS:
        entry = schema["actions"][action]
        assert entry["tier"] == "privileged", action
        assert entry["polkit_action"] == polkit_action_for(action) == POLKIT_ACTION_IDS[action]
        assert entry["polkit_action"] in policy_ids, action
        for req in ("confirmed", "session_token"):
            assert req in entry["requires"], (action, req)
        assert action in doc_priv, action
    for action in SAFE_ACTIONS:
        entry = schema["actions"][action]
        assert entry["tier"] == "safe", action
        assert entry["polkit_action"] is None, action
        assert action in doc_safe, action
