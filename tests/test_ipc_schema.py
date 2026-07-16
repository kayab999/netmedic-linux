from netmedic.action_catalog import PRIVILEGED_ACTIONS, SAFE_ACTIONS
from netmedic.ipc_schema import IPC_API_VERSION, export_schema


def test_export_schema_version_and_actions():
    schema = export_schema()
    assert schema["api_version"] == IPC_API_VERSION
    assert schema["framing"] == "newline_delimited_json"
    assert set(schema["actions"]) == set(PRIVILEGED_ACTIONS) | set(SAFE_ACTIONS)


def test_privileged_actions_declare_polkit():
    schema = export_schema()
    for name in PRIVILEGED_ACTIONS:
        entry = schema["actions"][name]
        assert entry["tier"] == "privileged"
        assert entry["polkit_action"].startswith("com.kayab.netmedic.")
        assert "session_token" in entry["requires"]