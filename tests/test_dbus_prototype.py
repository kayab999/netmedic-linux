"""D-Bus v2.0 prototype contract (design track; no system bus needed)."""

import json

from tools.dbus_prototype.service import (
    CallerSubject,
    FakeAuthority,
    HelperService,
)

SUBJECT = CallerSubject(unique_name=":1.42", pid=4242, uid=1000,
                        unit="app-netmedic.service")


def _service(allowed=frozenset(), **kwargs):
    return HelperService(FakeAuthority(allowed), **kwargs)


def test_malformed_verb_never_reaches_authority():
    auth = FakeAuthority(frozenset({"com.kayab.netmedic.flush-dns"}))
    svc = HelperService(auth)
    res = svc.execute("rm-rf", "{}", SUBJECT)
    assert res["ok"] is False
    assert auth.calls == []


def test_bad_json_rejected():
    svc = _service()
    res = svc.execute("flush-dns", "{nope", SUBJECT)
    assert res["ok"] is False
    assert "JSON" in res["message"]


def test_allowed_verb_authorizes_exact_polkit_id(monkeypatch):
    from netmedic.action_catalog import POLKIT_ACTION_IDS
    seen = {}

    def fake_execute(plan):
        seen["verb"] = plan.verb
        return {"ok": True, "message": "ok", "details": None}

    monkeypatch.setattr("netmedic.helper_main.execute_plan", fake_execute)
    auth = FakeAuthority(frozenset({POLKIT_ACTION_IDS["flush_dns"]}))
    svc = HelperService(auth)
    res = svc.execute("flush-dns", "{}", SUBJECT)
    assert res["ok"] is True
    assert seen["verb"] == "flush-dns"
    assert auth.calls == [(SUBJECT.unique_name, POLKIT_ACTION_IDS["flush_dns"])]


def test_denied_verb_never_executes(monkeypatch):
    def boom(plan):  # pragma: no cover - must not run
        raise AssertionError("denied verb executed")

    monkeypatch.setattr("netmedic.helper_main.execute_plan", boom)
    svc = _service()
    res = svc.execute("flush-dns", "{}", SUBJECT)
    assert res["ok"] is False
    assert "Denied" in res["message"]


def test_shared_verb_denied_as_ambiguous():
    """vpn-run-script maps 1:3 — deny until the M8b verb split lands."""
    auth = FakeAuthority(frozenset({
        "com.kayab.netmedic.vpn-install",
        "com.kayab.netmedic.vpn-create",
        "com.kayab.netmedic.vpn-revoke",
    }))
    from netmedic.helper_verbs import PINNED_VPN_INSTALL_SHA256
    svc = HelperService(auth)
    res = svc.execute("vpn-run-script", json.dumps({
        "script_id": "openvpn-install",
        "script": "/tmp/x.sh",  # noqa: S108 (attacker-path fixture string; never created)
        "expected_sha256": PINNED_VPN_INSTALL_SHA256,
        "env": {},
    }), SUBJECT)
    assert res["ok"] is False
    assert "no unique polkit action" in res["message"]
    assert auth.calls == []


def test_every_unique_verb_resolves(monkeypatch):
    """Each 1:1 table row authorizes its own polkit ID (no bus)."""
    from netmedic.action_catalog import ACTIONS

    monkeypatch.setattr("netmedic.helper_main.execute_plan",
                        lambda plan: {"ok": True, "message": "ok", "details": None})
    uniques = {}
    for spec in ACTIONS:
        if spec.helper_verb and spec.polkit_id:
            uniques.setdefault(spec.helper_verb, []).append(spec.polkit_id)
    unambiguous = {v: ids[0] for v, ids in uniques.items() if len(ids) == 1}
    assert len(unambiguous) >= 9  # all except the shared vpn-run-script
    auth = FakeAuthority(frozenset(unambiguous.values()))
    svc = HelperService(auth)
    for verb, pid in unambiguous.items():
        assert svc.execute(verb, _minimal_args(verb), SUBJECT)["ok"] is True
        assert auth.calls[-1] == (SUBJECT.unique_name, pid), verb


def _minimal_args(verb):
    if verb == "renew-ip":
        return json.dumps({"iface": "eth0", "mode": "nmcli"})
    if verb == "change-dns":
        return json.dumps({"server": "1.1.1.1", "connection": "Home"})
    if verb in ("restart-adapter",):
        return json.dumps({"iface": "eth0"})
    if verb == "toggle-firewall":
        return json.dumps({"action": "enable"})
    if verb in ("vpn-start-service", "vpn-restart-service"):
        return json.dumps({})
    if verb == "iface-del":
        return json.dumps({"iface": "medicabcdef"})
    if verb == "iface-add-dummy":
        return json.dumps({"iface": "medic000001"})
    return json.dumps({})


def test_result_hook_best_effort(monkeypatch):
    monkeypatch.setattr("netmedic.helper_main.execute_plan",
                        lambda plan: {"ok": True, "message": "ok", "details": None})
    seen = []
    svc = HelperService(FakeAuthority(), on_result=lambda v, r: seen.append(v))
    svc.execute("rm-rf", "{}", SUBJECT)
    assert seen == []  # validation rejections don't emit

    def bad_hook(v, r):
        raise RuntimeError("hook boom")

    svc2 = HelperService(FakeAuthority(frozenset({"com.kayab.netmedic.flush-dns"})),
                         on_result=bad_hook)
    res = svc2.execute("flush-dns", "{}", SUBJECT)
    assert res["ok"] is True  # hook failure never breaks the result
