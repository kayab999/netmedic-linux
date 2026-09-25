"""Phase B: helper verb validation and dry-run planning (no root)."""

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from netmedic.helper_main import main as helper_main
from netmedic.helper_verbs import (
    ALL_VERBS,
    VerbValidationError,
    plan_verb,
    validate_dns,
    validate_iface,
)
from netmedic.system import CommandRunner


def test_all_core_verbs_plan():
    plan_verb("flush-dns", {})
    plan_verb("renew-ip", {"iface": "wlan0", "mode": "nmcli"})
    plan_verb("change-dns", {"server": "1.1.1.1", "connection": "Wired connection 1"})
    plan_verb("restart-adapter", {"iface": "eth0"})
    plan_verb("reset-stack", {})
    plan_verb("toggle-firewall", {"action": "enable"})
    plan_verb("vpn-list", {})
    plan_verb("vpn-start-service", {})
    plan_verb("vpn-restart-service", {})
    plan_verb("iface-del", {"iface": "medicabcdef"})
    plan_verb("iface-add-dummy", {"iface": "medic000001"})


def test_flush_dns_argv():
    plan = plan_verb("flush-dns")
    assert plan.commands == [["resolvectl", "flush-caches"]]


def test_renew_ip_modes():
    nm = plan_verb("renew-ip", {"iface": "wlan0", "mode": "nmcli"})
    assert nm.commands[0] == ["nmcli", "device", "reapply", "wlan0"]
    dh = plan_verb("renew-ip", {"iface": "wlan0", "mode": "dhclient"})
    assert dh.commands[0] == ["dhclient", "-r", "wlan0"]
    assert dh.commands[1] == ["dhclient", "wlan0"]


def test_iface_del_rejects_eth0():
    with pytest.raises(VerbValidationError, match="non-medic"):
        plan_verb("iface-del", {"iface": "eth0"})


def test_iface_del_accepts_medic():
    plan = plan_verb("iface-del", {"iface": "medicabcdef"})
    assert plan.commands == [["ip", "link", "del", "medicabcdef"]]


def test_dns_validation():
    assert validate_dns("8.8.8.8") == "8.8.8.8"
    with pytest.raises(VerbValidationError):
        validate_dns("not-an-ip")
    with pytest.raises(VerbValidationError):
        plan_verb("change-dns", {"server": "999.1.1.1", "connection": "Home"})


def test_toggle_firewall_requires_action():
    with pytest.raises(VerbValidationError):
        plan_verb("toggle-firewall", {"action": "maybe"})


def test_unknown_verb():
    with pytest.raises(VerbValidationError, match="Unknown verb"):
        plan_verb("rm-rf")


def test_vpn_run_script_validates_sha_and_path():
    with pytest.raises(VerbValidationError):
        plan_verb(
            "vpn-run-script",
            {
                "script": "relative.sh",
                "expected_sha256": "ab" * 32,
                "env": {},
            },
        )
    with pytest.raises(VerbValidationError):
        plan_verb(
            "vpn-run-script",
            {
                "script": "/tmp/x.sh",
                "expected_sha256": "deadbeef",
                "env": {},
            },
        )
    plan = plan_verb(
        "vpn-run-script",
        {
            "script": "/tmp/openvpn-install.sh",
            "expected_sha256": "ab" * 32,
            "env": {"MENU_OPTION": "1", "CLIENT": "laptop"},
        },
    )
    assert plan.commands[0][0] == "__vpn_script__"
    assert "CLIENT=laptop" in plan.commands[0]


def test_cli_dry_run_flush_dns(capsys):
    code = helper_main(["flush-dns", "--dry-run"])
    assert code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["commands"] == [["resolvectl", "flush-caches"]]


def test_cli_bad_args(capsys):
    code = helper_main(["renew-ip", "--dry-run", "--json", "{}"])
    assert code == 2
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False


def test_cli_list_verbs(capsys):
    code = helper_main(["--list-verbs"])
    assert code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert "flush-dns" in out["verbs"]
    assert set(out["verbs"]) == set(ALL_VERBS)


def test_run_elevated_legacy_uses_planned_argv(monkeypatch):
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    monkeypatch.setenv("NETMEDIC_ALLOW_LEGACY_ELEVATION", "1")
    calls = []

    def fake_run(command, require_root=False, timeout=None, _legacy_ok=False):
        calls.append((list(command), require_root, _legacy_ok))
        from netmedic.models import CommandResult

        return CommandResult(True, 0, "ok", "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))
    res = CommandRunner.run_elevated("flush-dns", {})
    assert res.success is True
    assert calls == [(["resolvectl", "flush-caches"], True, True)]


def test_run_elevated_without_helper_or_legacy_fails(monkeypatch):
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    monkeypatch.setenv("NETMEDIC_ALLOW_LEGACY_ELEVATION", "0")
    res = CommandRunner.run_elevated("flush-dns", {})
    assert res.success is False
    assert "helper" in res.stderr.lower()
    assert "install-polkit-policy" in res.stderr.lower()


def test_direct_require_root_blocked_without_legacy(monkeypatch):
    monkeypatch.setenv("NETMEDIC_ALLOW_LEGACY_ELEVATION", "0")
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    res = CommandRunner.run(["resolvectl", "flush-caches"], require_root=True)
    assert res.success is False
    assert "run_elevated" in res.stderr.lower() or "disabled" in res.stderr.lower()


def test_run_elevated_helper_mode_builds_pkexec(monkeypatch):
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pkexec" if name == "pkexec" else None)
    from pathlib import Path

    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("/usr/libexec/netmedic/helper")),
    )
    captured = {}

    def fake_run(command, require_root=False, timeout=None):
        captured["cmd"] = list(command)
        captured["require_root"] = require_root
        from netmedic.models import CommandResult

        payload = json.dumps({"ok": True, "message": "flushed", "details": None})
        return CommandResult(True, 0, payload, "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))
    res = CommandRunner.run_elevated("flush-dns", {})
    assert res.success is True
    assert captured["require_root"] is False
    assert captured["cmd"][0] == "/usr/bin/pkexec"
    assert captured["cmd"][1] == "/usr/libexec/netmedic/helper"
    assert "flush-dns" in captured["cmd"]
    assert "--execute" in captured["cmd"]


def test_run_elevated_helper_surfaces_details_as_stdout(monkeypatch):
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    monkeypatch.setattr("os.geteuid", lambda: 0)
    from pathlib import Path

    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("/usr/libexec/netmedic/helper")),
    )

    def fake_run(command, require_root=False, timeout=None):
        from netmedic.models import CommandResult

        payload = json.dumps(
            {
                "ok": True,
                "message": "read VPN PKI index",
                "details": "V\t0\t\t01\tunknown\t/CN=laptop",
            }
        )
        return CommandResult(True, 0, payload, "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))
    res = CommandRunner.run_elevated("vpn-list", {})
    assert res.success is True
    assert "CN=laptop" in res.stdout


def test_use_helper_auto_when_system_path_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("NETMEDIC_USE_HELPER", raising=False)
    fake = tmp_path / "helper"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr("netmedic.config.Config.SYSTEM_HELPER_PATH", fake)
    from netmedic.config import Config

    assert Config.use_privileged_helper() is True
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    assert Config.use_privileged_helper() is False


def test_run_elevated_rejects_bad_verb():
    res = CommandRunner.run_elevated("not-a-verb", {})
    assert res.success is False
    assert res.returncode == 2


def test_validate_iface():
    assert validate_iface("wlan0") == "wlan0"
    with pytest.raises(VerbValidationError):
        validate_iface("../etc")


def test_service_allowlist_rejects_arbitrary():
    from netmedic.helper_verbs import validate_service

    with pytest.raises(VerbValidationError, match="allowlisted"):
        validate_service("ssh.service")
    with pytest.raises(VerbValidationError, match="allowlisted"):
        validate_service("NetworkManager.service")
    with pytest.raises(VerbValidationError):
        plan_verb("vpn-start-service", {"service": "dbus.service"})


def test_service_allowlist_accepts_openvpn():
    from netmedic.helper_verbs import validate_service

    assert validate_service("openvpn-server@server.service") == "openvpn-server@server.service"
    assert validate_service("openvpn-server@client2.service") == "openvpn-server@client2.service"
    plan = plan_verb("vpn-restart-service", {"service": "openvpn-server@client2.service"})
    assert plan.commands == [["systemctl", "restart", "openvpn-server@client2.service"]]


def test_vpn_run_script_rejects_non_normalized():
    with pytest.raises(VerbValidationError):
        plan_verb(
            "vpn-run-script",
            {"script": "/tmp//x.sh", "expected_sha256": "ab" * 32, "env": {}},
        )
    with pytest.raises(VerbValidationError):
        plan_verb(
            "vpn-run-script",
            {"script": "/tmp/a/../x.sh", "expected_sha256": "ab" * 32, "env": {}},
        )


def test_vpn_run_script_rejects_bad_env_key():
    """Mutation-hardening: env key allowlist must reject shell-ish names."""
    with pytest.raises(VerbValidationError):
        plan_verb(
            "vpn-run-script",
            {
                "script": "/tmp/openvpn-install.sh",
                "expected_sha256": "ab" * 32,
                "env": {"BAD-KEY!": "1"},
            },
        )
    with pytest.raises(VerbValidationError):
        plan_verb(
            "vpn-run-script",
            {
                "script": "/tmp/openvpn-install.sh",
                "expected_sha256": "ab" * 32,
                "env": {"ok_key": "a\nb"},
            },
        )


def test_helper_execute_backdoor_requires_test_mode(monkeypatch):
    from netmedic.helper_main import _allow_test_execute, _should_execute

    monkeypatch.setenv("NETMEDIC_TEST_MODE", "1")
    monkeypatch.setenv("NETMEDIC_HELPER_EXECUTE", "1")
    assert _allow_test_execute() is True
    assert _should_execute(False, False) is True

    monkeypatch.delenv("NETMEDIC_TEST_MODE")
    assert _allow_test_execute() is False

    monkeypatch.delenv("NETMEDIC_HELPER_EXECUTE")
    monkeypatch.setenv("NETMEDIC_TEST_MODE", "1")
    assert _allow_test_execute() is False
    assert _should_execute(True, False) is True
    assert _should_execute(False, True) is False


def _write_source(path, content: bytes):
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_stage_verified_copy_ok(tmp_path):
    from netmedic.helper_main import _stage_verified_copy

    src = tmp_path / "src.sh"
    digest = _write_source(src, b"#!/bin/sh\necho hi\n")
    stage = tmp_path / "stage"
    staged = _stage_verified_copy(str(src), digest, str(stage))
    assert staged.startswith(str(stage) + "/")
    assert staged != str(src)
    assert Path(staged).read_bytes() == b"#!/bin/sh\necho hi\n"
    assert oct(os.stat(staged).st_mode & 0o777) == oct(0o700)
    assert oct(os.stat(stage).st_mode & 0o777) == oct(0o700)
    os.unlink(staged)


def test_stage_rejects_tampered_source(tmp_path):
    from netmedic.helper_main import StagingError, _stage_verified_copy

    src = tmp_path / "src.sh"
    _write_source(src, b"#!/bin/sh\necho hi\n")
    with pytest.raises(StagingError, match="integrity"):
        _stage_verified_copy(str(src), "0" * 64, str(tmp_path / "stage"))


def test_stage_refuses_symlink_and_file(tmp_path):
    from netmedic.helper_main import StagingError, _stage_verified_copy

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    src = tmp_path / "src.sh"
    digest = _write_source(src, b"#!/bin/sh\necho hi\n")
    with pytest.raises(StagingError):
        _stage_verified_copy(str(src), digest, str(link))
    afile = tmp_path / "afile"
    afile.write_text("x")
    with pytest.raises(StagingError):
        _stage_verified_copy(str(src), digest, str(afile))


def test_exec_uses_staged_copy_not_source(tmp_path, monkeypatch):
    from netmedic.helper_main import _execute_vpn_script

    src = tmp_path / "openvpn-install.sh"
    digest = _write_source(src, b"#!/bin/sh\necho staged\n")
    stage = tmp_path / "stage"
    captured = {}

    def fake_run(argv, timeout):
        captured["argv"] = list(argv)
        # Deterministic swap simulation: rewrite SOURCE after staging.
        # Old code exec'd this path; new code must not.
        src.write_bytes(b"#!/bin/sh\necho PWNED\n")
        m = MagicMock()
        m.returncode = 0
        m.stdout = "done"
        m.stderr = ""
        return m

    monkeypatch.setattr("netmedic.helper_main._run_argv", fake_run)
    res = _execute_vpn_script(
        ["__vpn_script__", str(src), digest, "MENU_OPTION=1"],
        timeout=10,
        staging_dir=str(stage),
    )
    assert res["ok"] is True
    target = captured["argv"][-1]
    assert target != str(src)
    assert target.startswith(str(stage) + "/")
    # Staged copy cleaned up after exec
    assert list(stage.glob("sealed-*.sh")) == []


def test_exec_real_harmless_script(tmp_path):
    from netmedic.helper_main import _execute_vpn_script

    src = tmp_path / "openvpn-install.sh"
    digest = _write_source(src, b"#!/bin/sh\necho hello-from-staged\n")
    res = _execute_vpn_script(
        ["__vpn_script__", str(src), digest], timeout=10, staging_dir=str(tmp_path / "stage2")
    )
    assert res["ok"] is True
    assert "hello-from-staged" in (res["details"] or "")
