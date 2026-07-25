"""Phase B: helper verb validation and dry-run planning (no root)."""

import json
import sys

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
    calls = []

    def fake_run(command, require_root=False, timeout=None):
        calls.append((list(command), require_root))
        from netmedic.models import CommandResult

        return CommandResult(True, 0, "ok", "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))
    res = CommandRunner.run_elevated("flush-dns", {})
    assert res.success is True
    assert calls == [(["resolvectl", "flush-caches"], True)]


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
