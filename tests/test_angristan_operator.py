"""AngristanOperator coverage (F2): vendored script id, markers, errors.

F2 removed the user-space download/hash/seal path: the daemon names a fixed
``script_id`` and the root helper resolves, pins and stages the vendored
installer. These tests assert the operator stays inside that contract.
"""

from unittest.mock import MagicMock

import pytest

from netmedic.helper_verbs import plan_verb, validate_service
from netmedic.models import CommandResult, NetResult, ResultCode
from netmedic.operators.base import OperatorStatus
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.operators.vpn.base import VPNClient


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """Operator with a present install marker."""
    marker = tmp_path / "server.conf"
    marker.write_text("port 1194\n")
    monkeypatch.setattr(AngristanOperator, "INSTALL_MARKER_PATH", str(marker))
    return AngristanOperator()


# --- Metadata + service allowlist integration ---


def test_metadata_and_service_shape():
    op = AngristanOperator()
    assert op.name == "OpenVPN (Angristan)"
    assert op.slug == "vpn-angristan"
    assert op.description
    # Fixed service must stay inside the helper allowlist (guards future renames)
    assert op.get_service_name() == "openvpn-server@server.service"
    assert validate_service(op.get_service_name()) == op.get_service_name()


def test_service_allowlist_rejects_arbitrary():
    for bad in ("ssh.service", "dbus.service", "NetworkManager.service", ""):
        try:
            validate_service(bad)
        except Exception:  # noqa: S112 (test fixture loop; iteration failure is the assertion)
            continue
        raise AssertionError(f"validate_service accepted {bad!r}")


def test_client_name_validation():
    op = AngristanOperator()
    assert op._validate_client_name("laptop-1_x") is True
    assert op._validate_client_name("bad name!") is False
    assert op._validate_client_name("") is False


def test_legacy_download_and_hash_surface_is_gone():
    """F2: no second trust anchor and no remote fetch in the daemon."""
    for attr in ("SCRIPT_URL", "EXPECTED_SHA256", "script_path"):
        assert not hasattr(AngristanOperator, attr), attr
    for attr in ("_download_script", "_execute_verified_script", "_verify_integrity"):
        assert not hasattr(AngristanOperator, attr), attr
    assert AngristanOperator.SCRIPT_ID == "openvpn-install"
    assert plan_verb("vpn-run-script", {"script_id": AngristanOperator.SCRIPT_ID})


# --- Install marker ---


def test_installed_marker_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AngristanOperator, "INSTALL_MARKER_PATH", str(tmp_path / "missing-server.conf")
    )
    assert AngristanOperator()._installed() is False


def test_installed_marker_present(installed):
    assert installed._installed() is True


# --- Helper invocation ---


def test_run_vpn_script_sends_only_id_and_env(monkeypatch):
    seen = {}

    def fake_elevated(verb, args=None, timeout=None, **kwargs):
        seen["verb"] = verb
        seen["args"] = dict(args or {})
        return CommandResult(True, 0, "ok", "", [verb])

    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(fake_elevated),
    )
    res = AngristanOperator()._run_vpn_script(
        ["MENU_OPTION=1", "CLIENT=laptop"], timeout=5
    )

    assert res.success is True
    assert seen["verb"] == "vpn-run-script"
    assert seen["args"] == {
        "script_id": "openvpn-install",
        "env": {"MENU_OPTION": "1", "CLIENT": "laptop"},
    }
    # The plan must accept exactly what the operator sends (no path/hash).
    plan = plan_verb(seen["verb"], seen["args"])
    assert plan.commands[0][:2] == ["__vpn_script__", "openvpn-install"]


def test_run_vpn_script_rejects_bad_env_before_elevation(monkeypatch):
    elevated = MagicMock()
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated", elevated
    )
    res = AngristanOperator()._run_vpn_script(["NOEQUALS"], timeout=5)
    assert res.success is False
    assert res.returncode == 2
    assert "env" in res.stderr.lower()
    elevated.assert_not_called()


# --- Status ---


def test_check_status_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AngristanOperator, "INSTALL_MARKER_PATH", str(tmp_path / "missing.conf")
    )
    res = AngristanOperator().check_status()
    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    assert res.message == OperatorStatus.NOT_INSTALLED.value


def test_check_status_running_and_stopped(installed, monkeypatch):
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: True),
    )
    assert installed.check_status().message == OperatorStatus.RUNNING.value
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: False),
    )
    assert installed.check_status().message == OperatorStatus.STOPPED.value


def test_check_status_exception(installed, monkeypatch):
    def boom(_service):
        raise RuntimeError("systemctl boom")

    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active", boom
    )
    res = installed.check_status()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert res.message == OperatorStatus.ERROR.value
    assert "boom" in (res.details or "")


# --- Install ---


def test_install_never_downloads(installed, monkeypatch):
    run = MagicMock()
    monkeypatch.setattr("netmedic.operators.vpn.angristan.CommandRunner.run", run)
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        installed,
        "check_status",
        lambda: NetResult(installed.name, True, OperatorStatus.RUNNING.value),
    )
    installed.install()
    run.assert_not_called()


def test_install_failure(installed, monkeypatch):
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(False, 1, "", "elev fail", []),
    )
    res = installed.install()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Installation failed" in res.message


def test_install_service_down(installed, monkeypatch):
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        installed,
        "check_status",
        lambda: NetResult(installed.name, True, OperatorStatus.STOPPED.value),
    )
    res = installed.install()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "service down" in res.message


def test_install_success(installed, monkeypatch):
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        installed,
        "check_status",
        lambda: NetResult(installed.name, True, OperatorStatus.RUNNING.value),
    )
    res = installed.install()
    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    assert "successful" in res.message


# --- Client list / add / revoke ---


def _pkiresponse(*lines):
    m = MagicMock()
    m.success = True
    m.stdout = "\n".join(lines)
    m.stderr = ""
    return m


def test_list_clients_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AngristanOperator, "INSTALL_MARKER_PATH", str(tmp_path / "missing.conf")
    )
    res = AngristanOperator().list_clients()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "not installed" in res.message.lower()


def test_list_clients_elevate_fail(installed, monkeypatch):
    monkeypatch.setattr(
        installed, "check_status", lambda: NetResult(installed.name, True, OperatorStatus.RUNNING.value)
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(False, 1, "", "denied", [])),
    )
    res = installed.list_clients()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "PKI" in res.message


def test_list_clients_parses_mixed(installed, monkeypatch):
    monkeypatch.setattr(
        installed, "check_status", lambda: NetResult(installed.name, True, OperatorStatus.RUNNING.value)
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(
            lambda verb, args=None, timeout=None, **k: _pkiresponse(
                "V\t0\t\t01\tunknown\t/CN=laptop",
                "R\t0\t\t02\tunknown\t/CN=old",
                "V\t0\t\t03\tunknown\t/CN=server",
                "malformed-line",
                "V\t0\t\t04\tunknown\t/OU=x",
            )
        ),
    )
    res = installed.list_clients()
    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    names = {c.name: c.active for c in res.data}
    assert names == {"laptop": True, "old": False}


def test_list_clients_parse_error(installed, monkeypatch):
    monkeypatch.setattr(
        installed, "check_status", lambda: NetResult(installed.name, True, OperatorStatus.RUNNING.value)
    )
    bad = MagicMock(success=True)
    bad.stdout.splitlines.side_effect = RuntimeError("boom")
    bad.stderr = ""
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: bad),
    )
    res = installed.list_clients()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Parse" in res.message


def test_add_client_invalid_name(installed):
    res = installed.add_client("bad name!")
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Invalid client name" in res.message


def test_add_client_duplicate(installed, monkeypatch):
    existing = NetResult(installed.name, True, "ok", data=[VPNClient(name="laptop", active=True)])
    monkeypatch.setattr(installed, "list_clients", lambda: existing)
    res = installed.add_client("laptop")
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "already exists" in res.message


def test_add_client_execute_fail(installed, monkeypatch):
    monkeypatch.setattr(
        installed, "list_clients", lambda: NetResult(installed.name, True, "ok", data=[])
    )
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(False, 1, "", "elev fail", []),
    )
    res = installed.add_client("laptop")
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Failed to execute" in res.message


def test_add_client_success_verified(installed, monkeypatch):
    empty = NetResult(installed.name, True, "ok", data=[])
    found = NetResult(installed.name, True, "ok", data=[VPNClient(name="laptop", active=True)])
    calls = {"n": 0}

    def fake_list():
        calls["n"] += 1
        return empty if calls["n"] == 1 else found

    monkeypatch.setattr(installed, "list_clients", fake_list)
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    res = installed.add_client("laptop")
    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    assert "verified" in res.message


def test_add_client_not_found_after_exec(installed, monkeypatch):
    monkeypatch.setattr(
        installed, "list_clients", lambda: NetResult(installed.name, True, "ok", data=[])
    )
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    res = installed.add_client("ghost")
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "not found in PKI" in res.message


def test_revoke_invalid_and_fail(installed, monkeypatch):
    assert installed.revoke_client("bad!").code not in (ResultCode.OK, ResultCode.EXECUTED)
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(False, 1, "", "elev fail", []),
    )
    res = installed.revoke_client("laptop")
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Failed to revoke" in res.message


def test_revoke_success_verified(installed, monkeypatch):
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        installed,
        "list_clients",
        lambda: NetResult(installed.name, True, "ok", data=[VPNClient(name="laptop", active=False)]),
    )
    res = installed.revoke_client("laptop")
    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    assert "revoked and verified" in res.message


def test_revoke_not_marked(installed, monkeypatch):
    monkeypatch.setattr(
        installed,
        "_run_vpn_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        installed,
        "list_clients",
        lambda: NetResult(installed.name, True, "ok", data=[VPNClient(name="laptop", active=True)]),
    )
    res = installed.revoke_client("laptop")
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "not marked revoked" in res.message


# --- Service control + stop ---


def test_start_service_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AngristanOperator, "INSTALL_MARKER_PATH", str(tmp_path / "missing.conf")
    )
    res = AngristanOperator().start_service()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "NOT_INSTALLED" in res.message or "not" in res.message.lower()

    op = AngristanOperator()
    marker = tmp_path / "server.conf"
    marker.write_text("port 1194\n")
    monkeypatch.setattr(AngristanOperator, "INSTALL_MARKER_PATH", str(marker))
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(True, 0, "", "", [])),
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: True),
    )
    assert op.start_service().code in (ResultCode.OK, ResultCode.EXECUTED)
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: False),
    )
    res = op.start_service()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Failed to start" in res.message


def test_restart_service_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AngristanOperator, "INSTALL_MARKER_PATH", str(tmp_path / "missing.conf")
    )
    res = AngristanOperator().restart_service()
    assert res.code not in (ResultCode.OK, ResultCode.EXECUTED)

    op = AngristanOperator()
    marker = tmp_path / "server.conf"
    marker.write_text("port 1194\n")
    monkeypatch.setattr(AngristanOperator, "INSTALL_MARKER_PATH", str(marker))
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(True, 0, "", "", [])),
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: True),
    )
    assert op.restart_service().code in (ResultCode.OK, ResultCode.EXECUTED)
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: False),
    )
    assert op.restart_service().code not in (ResultCode.OK, ResultCode.EXECUTED)


def test_stop_is_app_local_only(tmp_path, monkeypatch):
    op = AngristanOperator()
    run = MagicMock()
    elevated = MagicMock()
    active = MagicMock()
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run", run
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated", elevated
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active", active
    )
    assert op.stop() is None
    run.assert_not_called()
    elevated.assert_not_called()
    active.assert_not_called()


def test_script_constants():
    assert AngristanOperator.SCRIPT_ID == "openvpn-install"
    assert len(AngristanOperator.PIN_COMMIT) >= 7
    assert AngristanOperator.REPIN_HINT
    assert AngristanOperator.INDEX_TXT_PATH.startswith("/etc/openvpn/")
    assert AngristanOperator.INSTALL_MARKER_PATH == "/etc/openvpn/server/server.conf"
