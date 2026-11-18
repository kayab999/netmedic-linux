"""Fase 6.2: the daemon must surface the helper's own restart-adapter verdict.

The helper already reads IFF_UP and carrier from sysfs. The daemon must not
re-derive the post-condition with `ip link` (operstate) nor replace the
helper's message with a fixed text.
"""

import json

import pytest

from netmedic.models import CommandResult, ResultCode


@pytest.fixture
def medic(tmp_path, monkeypatch):
    from netmedic import network as netmod

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    netmod.NetworkMedic._instance = None
    m = netmod.NetworkMedic()
    yield m
    netmod.NetworkMedic._instance = None


def _helper_result(ok, message, details, *, rc=None):
    """Shape a result like CommandRunner.run_elevated after F6.2."""
    if rc is None:
        rc = 0 if ok else 1
    raw = json.dumps({"ok": ok, "message": message, "details": details})
    return CommandResult(
        ok,
        rc,
        "" if ok else raw,
        "" if ok else message,
        ["restart-adapter"],
        message=message,
        details=details,
    )


def _no_ip_poll(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("daemon must not poll ip/operstate after the helper")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fail))


def test_helper_ok_without_carrier_reaches_the_user(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(
            lambda verb, args=None, **k: _helper_result(
                True,
                "Adapter eth0 is UP (no carrier)",
                "iff_up=up; carrier=down",
            )
        ),
    )
    _no_ip_poll(monkeypatch)

    res = medic.restart_adapter()

    assert res.code == ResultCode.OK
    assert "no carrier" in res.message
    assert res.message == "Adapter eth0 is UP (no carrier)"
    assert res.details == "iff_up=up; carrier=down"


def test_loopback_is_ok_without_operstate(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "lo")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(
            lambda verb, args=None, **k: _helper_result(
                True,
                "Adapter lo is UP (carrier unknown)",
                "iff_up=up; carrier=unknown",
            )
        ),
    )
    _no_ip_poll(monkeypatch)

    res = medic.restart_adapter()

    assert res.code == ResultCode.OK
    assert "carrier unknown" in res.message
    assert res.details == "iff_up=up; carrier=unknown"


def test_helper_not_up_is_failed_and_message_is_propagated(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(
            lambda verb, args=None, **k: _helper_result(
                False,
                "Adapter eth0 not UP after restart",
                "iff_up=down; carrier=down",
            )
        ),
    )
    _no_ip_poll(monkeypatch)

    res = medic.restart_adapter()

    assert res.code == ResultCode.FAILED
    assert res.message == "Adapter eth0 not UP after restart"
    assert "not UP after restart" in res.message
    assert res.details == "iff_up=down; carrier=down"


def test_ip_link_text_cannot_turn_failure_into_success(medic, monkeypatch):
    """Old daemon fallback matched "UP" inside <NO-CARRIER,...,UP> state DOWN."""
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(
            lambda verb, args=None, **k: _helper_result(
                False,
                "Adapter eth0 not UP after restart",
                "iff_up=down; carrier=down",
            )
        ),
    )
    calls = []

    def fake_ip(cmd, timeout=None, **k):
        calls.append(list(cmd))
        return CommandResult(
            True,
            0,
            "2: eth0: <NO-CARRIER,BROADCAST,MULTICAST,UP> state DOWN mtu 1500",
            "",
            list(cmd),
        )

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake_ip))

    res = medic.restart_adapter()

    assert res.code == ResultCode.FAILED
    assert res.message == "Adapter eth0 not UP after restart"
    assert calls == []  # the "UP" substring in <...,UP> is never consulted


def test_run_elevated_exposes_helper_message_and_details(medic, monkeypatch, tmp_path):
    from pathlib import Path

    from netmedic.system import CommandRunner

    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("/usr/libexec/netmedic/helper")),
    )
    monkeypatch.setattr(CommandRunner, "_check_helper_version", staticmethod(lambda: None))

    def fake_run(command, require_root=False, timeout=None):
        payload = json.dumps(
            {
                "ok": True,
                "message": "Adapter eth0 is UP (no carrier)",
                "details": "iff_up=up; carrier=down",
            }
        )
        return CommandResult(True, 0, payload, "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))

    res = CommandRunner.run_elevated("restart-adapter", {"iface": "eth0"})

    assert res.success is True
    assert res.message == "Adapter eth0 is UP (no carrier)"
    assert res.details == "iff_up=up; carrier=down"


def test_run_elevated_exposes_helper_failure_verdict(medic, monkeypatch):
    from pathlib import Path

    from netmedic.system import CommandRunner

    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("/usr/libexec/netmedic/helper")),
    )
    monkeypatch.setattr(CommandRunner, "_check_helper_version", staticmethod(lambda: None))

    def fake_run(command, require_root=False, timeout=None):
        payload = json.dumps(
            {
                "ok": False,
                "message": "Adapter eth0 not UP after restart",
                "details": "iff_up=down; carrier=down",
            }
        )
        return CommandResult(False, 1, payload, "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))

    res = CommandRunner.run_elevated("restart-adapter", {"iface": "eth0"})

    assert res.success is False
    assert res.message == "Adapter eth0 not UP after restart"
    assert res.details == "iff_up=down; carrier=down"
    assert res.stderr == "Adapter eth0 not UP after restart"
