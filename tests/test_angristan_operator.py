"""AngristanOperator coverage (P1.1): service allowlist, TLS, XDG, integrity, errors.

NOTE on API mapping (read from operators/vpn/angristan.py):
- There is no `op._validate_service` / `op._validate_script_path`. Service + path
  validation lives in `helper_verbs.validate_service` / `plan_verb("vpn-run-script")`.
  These tests assert the operator stays inside that allowlist (service shape +
  sealed-path shape) instead of inventing operator-level validators.
"""
import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock

from netmedic.helper_verbs import plan_verb, validate_service
from netmedic.models import CommandResult, NetResult
from netmedic.operators.base import OperatorStatus
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.operators.vpn.base import VPNClient


def _op_with_script(tmp_path, monkeypatch, content=b"#!/bin/bash\nfake installer\n"):
    """Operator whose script_path is a real file under isolated XDG_DATA_HOME."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    script = tmp_path / "netmedic" / "operators" / "openvpn-install.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(content)
    return AngristanOperator(), script


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
        except Exception:
            continue
        raise AssertionError(f"validate_service accepted {bad!r}")


def test_client_name_validation():
    op = AngristanOperator()
    assert op._validate_client_name("laptop-1_x") is True
    assert op._validate_client_name("bad name!") is False
    assert op._validate_client_name("") is False


# --- Hash + integrity ---

def test_hash_file_fd_roundtrip(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc123")
    op = AngristanOperator()
    fd = os.open(str(p), os.O_RDONLY)
    try:
        assert op._hash_file_fd(fd) == hashlib.sha256(b"abc123").hexdigest()
    finally:
        os.close(fd)


def test_verify_integrity_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert AngristanOperator()._verify_integrity() is False


def test_verify_integrity_match(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nreal\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    assert op._verify_integrity() is True


def test_verify_integrity_mismatch(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\ntampered\n")
    assert op._verify_integrity() is False


# --- Download (TLS + branches) ---

def test_download_uses_tls_flags(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, script = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    seen = {}

    def fake_run(cmd, timeout=None, **kwargs):
        seen["cmd"] = list(cmd)
        script.write_bytes(content)
        return CommandResult(True, 0, "", "", list(cmd))

    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(fake_run),
    )
    res = op._download_script()
    assert res.success is True
    assert "--proto=https" in seen["cmd"]
    assert "--tlsv1.2" in seen["cmd"]
    assert "--retry" in seen["cmd"]
    assert op.SCRIPT_URL.startswith("https://")
    assert "http://" not in op.SCRIPT_URL.replace("https://", "")


def test_download_failure(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: CommandResult(False, 1, "", "conn refused", list(cmd))),
    )
    res = op._download_script()
    assert res.success is False
    assert "Download failed" in res.message


def test_download_empty_file(tmp_path, monkeypatch):
    op, script = _op_with_script(tmp_path, monkeypatch, b"")
    script.write_bytes(b"")
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: CommandResult(True, 0, "", "", list(cmd))),
    )
    res = op._download_script()
    assert res.success is False
    assert "Empty" in res.message


def test_download_integrity_failure(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\ntampered\n")
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: CommandResult(True, 0, "", "", list(cmd))),
    )
    res = op._download_script()
    assert res.success is False
    assert "Integrity" in res.message


def test_download_bad_header(tmp_path, monkeypatch):
    content = b"#!/bin/sh\nno bash here\n"
    op, script = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: CommandResult(True, 0, "", "", list(cmd))),
    )
    res = op._download_script()
    assert res.success is False
    assert "header" in res.message.lower()


def test_download_validation_error(tmp_path, monkeypatch):
    import builtins

    content = b"#!/bin/bash\nok\n"
    op, script = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: CommandResult(True, 0, "", "", list(cmd))),
    )
    real_open = builtins.open

    def fake_open(p, *a, **k):
        if str(p) == str(script):
            raise OSError("ro")
        return real_open(p, *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    res = op._download_script()
    assert res.success is False
    assert "Validation failed" in res.message


def test_download_success_sets_exec(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, script = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: CommandResult(True, 0, "", "", list(cmd))),
    )
    res = op._download_script()
    assert res.success is True
    assert oct(script.stat().st_mode & 0o777) == oct(0o500)


# --- Sealed execution (XDG, integrity, env) ---

def test_execute_cannot_open_script(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    res = AngristanOperator()._execute_verified_script(["A=1"], timeout=5)
    assert res.success is False
    assert "Cannot open script" in res.stderr


def test_execute_integrity_failure(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\ntampered\n")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    res = op._execute_verified_script(["A=1"], timeout=5)
    assert res.success is False
    assert res.returncode == 126
    assert "integrity" in res.stderr.lower()


def test_execute_refuses_without_xdg(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    res = op._execute_verified_script(["A=1"], timeout=5)
    assert res.success is False
    assert res.returncode == 2
    assert "XDG_RUNTIME_DIR" in res.stderr


def test_execute_rejects_bad_env(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    res = op._execute_verified_script(["NOEQUALS"], timeout=5)
    assert res.success is False
    assert res.returncode == 2
    assert "env" in res.stderr.lower()


def test_execute_success_sealed_copy(tmp_path, monkeypatch):
    content = b"#!/bin/bash\necho hi\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    seen = {}

    def fake_elevated(verb, args=None, timeout=None, **k):
        seen["verb"] = verb
        seen["args"] = dict(args or {})
        # Sealed path handed to helper must be absolute + normalized
        assert seen["args"]["script"].startswith(str(runtime))
        assert "//" not in seen["args"]["script"]
        plan = plan_verb(verb, seen["args"])
        assert plan.commands[0][0] == "__vpn_script__"
        return CommandResult(True, 0, "ok", "", [verb])

    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(fake_elevated),
    )
    res = op._execute_verified_script(["MENU_OPTION=1", "CLIENT=laptop"], timeout=5)
    assert res.success is True
    assert seen["verb"] == "vpn-run-script"
    assert seen["args"]["env"] == {"MENU_OPTION": "1", "CLIENT": "laptop"}
    # Sealed copy cleaned up
    leftovers = list((runtime / "netmedic").glob("openvpn-install.*.sh"))
    assert leftovers == []


def test_execute_sealed_rehash_failure(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    calls = {"n": 0}
    real_hash = AngristanOperator._hash_file_fd.__get__(op)

    def flaky(fd):
        calls["n"] += 1
        if calls["n"] == 1:
            return AngristanOperator.EXPECTED_SHA256
        return "0" * 64

    monkeypatch.setattr(op, "_hash_file_fd", flaky)
    assert real_hash  # keep reference to real hasher for lint-cleanliness
    res = op._execute_verified_script(["A=1"], timeout=5)
    assert res.success is False
    assert "Sealed" in res.stderr


# --- Status / install ---

def test_check_status_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    res = AngristanOperator().check_status()
    assert res.success is True
    assert res.message == OperatorStatus.NOT_INSTALLED.value


def test_check_status_integrity_fail(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\ntampered\n")
    res = op.check_status()
    assert res.success is False
    assert "integrity" in (res.details or "").lower()


def test_check_status_running_and_stopped(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: True),
    )
    assert op.check_status().message == OperatorStatus.RUNNING.value
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: False),
    )
    assert op.check_status().message == OperatorStatus.STOPPED.value


def test_check_status_exception(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")

    def boom():
        raise RuntimeError("stat boom")

    monkeypatch.setattr(op, "_verify_integrity", boom)
    res = op.check_status()
    assert res.success is False
    assert res.message == OperatorStatus.ERROR.value


def test_install_dl_failure(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    bad = NetResult("Download Script", False, "Download failed")
    monkeypatch.setattr(op, "_download_script", lambda: bad)
    res = op.install()
    assert res.success is False
    assert res.message == "Download failed"


def test_install_execute_failure(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(
        op, "_download_script", lambda: NetResult("Download Script", True, "ok")
    )
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(False, 1, "", "elev fail", []),
    )
    res = op.install()
    assert res.success is False
    assert "Installation failed" in res.message


def test_install_service_down(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(
        op, "_download_script", lambda: NetResult("Download Script", True, "ok")
    )
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        op,
        "check_status",
        lambda: NetResult(op.name, True, OperatorStatus.STOPPED.value),
    )
    res = op.install()
    assert res.success is False
    assert "service down" in res.message


def test_install_success(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(
        op, "_download_script", lambda: NetResult("Download Script", True, "ok")
    )
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        op,
        "check_status",
        lambda: NetResult(op.name, True, OperatorStatus.RUNNING.value),
    )
    res = op.install()
    assert res.success is True
    assert "successful" in res.message


# --- Client list / add / revoke ---

def _pkiresponse(*lines):
    m = MagicMock()
    m.success = True
    m.stdout = "\n".join(lines)
    m.stderr = ""
    return m


def test_list_clients_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    res = AngristanOperator().list_clients()
    assert res.success is False
    assert "not installed" in res.message.lower()


def test_list_clients_elevate_fail(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(b"#!/bin/bash\nok\n").hexdigest()
    )
    monkeypatch.setattr(
        op, "check_status", lambda: NetResult(op.name, True, OperatorStatus.RUNNING.value)
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(False, 1, "", "denied", [])),
    )
    res = op.list_clients()
    assert res.success is False
    assert "PKI" in res.message


def test_list_clients_parses_mixed(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(b"#!/bin/bash\nok\n").hexdigest()
    )
    monkeypatch.setattr(
        op, "check_status", lambda: NetResult(op.name, True, OperatorStatus.RUNNING.value)
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
    res = op.list_clients()
    assert res.success is True
    names = {c.name: c.active for c in res.data}
    assert names == {"laptop": True, "old": False}


def test_list_clients_parse_error(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(b"#!/bin/bash\nok\n").hexdigest()
    )
    monkeypatch.setattr(
        op, "check_status", lambda: NetResult(op.name, True, OperatorStatus.RUNNING.value)
    )
    bad = MagicMock(success=True)
    bad.stdout.splitlines.side_effect = RuntimeError("boom")
    bad.stderr = ""
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: bad),
    )
    res = op.list_clients()
    assert res.success is False
    assert "Parse" in res.message


def test_add_client_invalid_name(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    res = op.add_client("bad name!")
    assert res.success is False
    assert "Invalid client name" in res.message


def test_add_client_duplicate(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    existing = NetResult(op.name, True, "ok", data=[VPNClient(name="laptop", active=True)])
    monkeypatch.setattr(op, "list_clients", lambda: existing)
    res = op.add_client("laptop")
    assert res.success is False
    assert "already exists" in res.message


def test_add_client_execute_fail(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    monkeypatch.setattr(
        op, "list_clients", lambda: NetResult(op.name, True, "ok", data=[])
    )
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(False, 1, "", "elev fail", []),
    )
    res = op.add_client("laptop")
    assert res.success is False
    assert "Failed to execute" in res.message


def test_add_client_success_verified(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    empty = NetResult(op.name, True, "ok", data=[])
    found = NetResult(op.name, True, "ok", data=[VPNClient(name="laptop", active=True)])
    calls = {"n": 0}

    def fake_list():
        calls["n"] += 1
        return empty if calls["n"] == 1 else found

    monkeypatch.setattr(op, "list_clients", fake_list)
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    res = op.add_client("laptop")
    assert res.success is True
    assert "verified" in res.message


def test_add_client_not_found_after_exec(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    monkeypatch.setattr(
        op, "list_clients", lambda: NetResult(op.name, True, "ok", data=[])
    )
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    res = op.add_client("ghost")
    assert res.success is False
    assert "not found in PKI" in res.message


def test_revoke_invalid_and_fail(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    assert op.revoke_client("bad!").success is False
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(False, 1, "", "elev fail", []),
    )
    res = op.revoke_client("laptop")
    assert res.success is False
    assert "Failed to revoke" in res.message


def test_revoke_success_verified(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        op,
        "list_clients",
        lambda: NetResult(op.name, True, "ok", data=[VPNClient(name="laptop", active=False)]),
    )
    res = op.revoke_client("laptop")
    assert res.success is True
    assert "revoked and verified" in res.message


def test_revoke_not_marked(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
    monkeypatch.setattr(
        op,
        "_execute_verified_script",
        lambda env, timeout: CommandResult(True, 0, "", "", []),
    )
    monkeypatch.setattr(
        op,
        "list_clients",
        lambda: NetResult(op.name, True, "ok", data=[VPNClient(name="laptop", active=True)]),
    )
    res = op.revoke_client("laptop")
    assert res.success is False
    assert "not marked revoked" in res.message


# --- Service control + stop ---

def _op_installed_ok(tmp_path, monkeypatch, content=b"#!/bin/bash\nok\n"):
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    return op


def test_start_service_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    res = AngristanOperator().start_service()
    assert res.success is False
    assert "NOT_INSTALLED" in res.message or "not" in res.message.lower()

    op = _op_installed_ok(tmp_path, monkeypatch)
    monkeypatch.setattr(op, "_verify_integrity", lambda: False)
    assert "integrity" in op.start_service().details.lower()

    monkeypatch.setattr(op, "_verify_integrity", lambda: True)
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(True, 0, "", "", [])),
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: True),
    )
    assert op.start_service().success is True
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: False),
    )
    res = op.start_service()
    assert res.success is False
    assert "Failed to start" in res.message


def test_restart_service_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    res = AngristanOperator().restart_service()
    assert res.success is False

    op = _op_installed_ok(tmp_path, monkeypatch)
    monkeypatch.setattr(op, "_verify_integrity", lambda: False)
    assert "integrity" in op.restart_service().details.lower()

    monkeypatch.setattr(op, "_verify_integrity", lambda: True)
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(True, 0, "", "", [])),
    )
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: True),
    )
    assert op.restart_service().success is True
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.is_service_active",
        staticmethod(lambda svc: False),
    )
    assert op.restart_service().success is False


def test_stop_is_app_local_only(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"")
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


def test_verify_integrity_open_error(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(os, "open", MagicMock(side_effect=OSError("denied")))
    assert op._verify_integrity() is False


def test_verify_integrity_hash_error(tmp_path, monkeypatch):
    op, _ = _op_with_script(tmp_path, monkeypatch, b"#!/bin/bash\nok\n")
    monkeypatch.setattr(op, "_hash_file_fd", MagicMock(side_effect=RuntimeError("boom")))
    assert op._verify_integrity() is False


def test_verify_integrity_close_error_tolerated(tmp_path, monkeypatch):
    content = b"#!/bin/bash\nok\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    real_close = os.close
    monkeypatch.setattr(os, "close", MagicMock(side_effect=OSError("ro")))
    try:
        assert op._verify_integrity() is True
    finally:
        monkeypatch.setattr(os, "close", real_close)


def test_execute_chmod_error_tolerated(tmp_path, monkeypatch):
    content = b"#!/bin/bash\necho hi\n"
    op, _ = _op_with_script(tmp_path, monkeypatch, content)
    monkeypatch.setattr(
        AngristanOperator, "EXPECTED_SHA256", hashlib.sha256(content).hexdigest()
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    real_chmod = os.chmod

    def fake_chmod(path, mode):
        # Fail only the sealed-dir chmod (line 117-118); data-dir setup uses real chmod
        if str(path) == str(runtime / "netmedic"):
            raise OSError("ro")
        return real_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", fake_chmod)
    monkeypatch.setattr(
        "netmedic.operators.vpn.angristan.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: CommandResult(True, 0, "ok", "", [verb])),
    )
    res = op._execute_verified_script(["A=1"], timeout=5)
    assert res.success is True
    assert real_chmod  # keep reference for lint-cleanliness


def test_script_constants():
    assert AngristanOperator.SCRIPT_URL.startswith("https://")
    assert len(AngristanOperator.EXPECTED_SHA256) == 64
    assert Path(AngristanOperator.INDEX_TXT_PATH).is_absolute()
