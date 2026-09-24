"""Property-based tests (P1.4): framing, tokens, catalog, verbs, redaction.

Hypothesis proves these hold for arbitrary inputs, not just fixtures:
no crashes on hostile data, no contract drift, no secret leaks.
"""
import re
import string

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from netmedic import action_catalog as catalog
from netmedic import ipc_schema
from netmedic.audit_log import _sanitize_params
from netmedic.helper_verbs import ALL_VERBS, VerbPlan, VerbValidationError, plan_verb, validate_service
from netmedic.ipc_framing import encode_message, parse_message
from netmedic.models import ResultCode

json_scalar = st.one_of(
    st.text(max_size=30),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
)
json_value = st.recursive(
    json_scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=12), children, max_size=4),
    ),
    max_leaves=6,
)


@settings(max_examples=50, deadline=None)
@given(st.dictionaries(st.text(min_size=1, max_size=20), json_value, max_size=6))
def test_framing_roundtrip(payload):
    assert parse_message(encode_message(payload)) == payload
    assert encode_message(payload).endswith(b"\n")


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=200))
def test_parse_never_crashes_unexpectedly(data):
    """Arbitrary bytes: dict/list/scalar or ValueError — nothing else."""
    try:
        parse_message(data)
    except ValueError:
        pass


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n=st.integers(min_value=2, max_value=20))
def test_tokens_unique_and_shaped(n, tmp_path, monkeypatch):
    from netmedic.ipc_security import IPCSession

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    session = IPCSession()
    tokens = [session.issue_token() for _ in range(n)]
    assert len(set(tokens)) == n
    assert all(re.fullmatch(r"[0-9a-f]{64}", t) for t in tokens)


def test_catalog_disjoint_and_mapped():
    assert not (catalog.PRIVILEGED_ACTIONS & catalog.SAFE_ACTIONS)
    assert catalog.DISRUPTIVE_ACTIONS <= catalog.PRIVILEGED_ACTIONS
    for action in catalog.PRIVILEGED_ACTIONS:
        assert catalog.polkit_action_for(action)
        assert catalog.polkit_action_for(action).startswith("com.kayab.netmedic.")


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=1, max_size=60))
def test_unknown_verbs_rejected(action):
    if action in ALL_VERBS:
        return
    with pytest.raises(VerbValidationError):
        plan_verb(action, {})


json_args = st.dictionaries(
    st.text(min_size=1, max_size=16),
    st.one_of(st.text(max_size=40), st.integers(), st.booleans(), st.none()),
    max_size=6,
)


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.sampled_from(sorted(ALL_VERBS)), json_args)
def test_plan_verb_total(verb, args):
    """Any mapping args: VerbPlan or VerbValidationError — never anything else."""
    try:
        plan = plan_verb(verb, dict(args))
    except VerbValidationError:
        return
    assert isinstance(plan, VerbPlan)
    assert plan.verb == verb
    assert all(isinstance(cmd, list) and cmd for cmd in plan.commands)


@settings(max_examples=100, deadline=None)
@given(st.text(max_size=80))
def test_service_allowlist_decisive(name):
    try:
        out = validate_service(name)
    except VerbValidationError:
        return
    assert out == name
    assert name.startswith("openvpn-server@") and name.endswith(".service")


@settings(max_examples=50, deadline=None)
@given(st.dictionaries(st.text(min_size=1, max_size=20), json_value, max_size=6))
def test_audit_sanitize_shape(params):
    safe = _sanitize_params(dict(params))
    assert set(safe) == set(params)
    for key, value in safe.items():
        kl = key.lower()
        if key == "session_token" or any(
            s in kl for s in ("password", "pass", "token", "key", "secret", "auth")
        ):
            assert value == "<redacted>"
        elif isinstance(value, str):
            assert len(value) <= 500 + len("...[truncated]")


def test_result_code_roundtrip():
    for member in ResultCode:
        assert ResultCode(member.value) is member


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(sorted(catalog.PRIVILEGED_ACTIONS | catalog.SAFE_ACTIONS)))
def test_schema_matches_catalog(action):
    schema = ipc_schema.export_schema()
    assert schema["api_version"] == ipc_schema.IPC_API_VERSION
    entry = schema["actions"][action]
    if action in catalog.PRIVILEGED_ACTIONS:
        assert entry["tier"] == "privileged"
        assert entry["polkit_action"]
        assert "confirmed" in entry["requires"]
    else:
        assert entry["tier"] == "safe"
        assert entry["polkit_action"] is None


@settings(max_examples=30, deadline=None)
@given(st.text(alphabet=string.ascii_letters + string.digits + "@._+-", min_size=1, max_size=40))
def test_iface_names_decisive(name):
    from netmedic.helper_verbs import validate_iface

    try:
        validate_iface(name)
    except VerbValidationError:
        assert not __import__("re").fullmatch(r"[A-Za-z0-9._@+-]+", name)
    else:
        assert __import__("re").fullmatch(r"[A-Za-z0-9._@+-]+", name)
