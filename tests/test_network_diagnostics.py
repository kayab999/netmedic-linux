"""network.py coverage (P1.2): parsing, diagnostics branches, repair flows.

Strategy: fresh singleton per test (isolated XDG dirs), CommandRunner.run /
run_elevated / is_service_active mocked at netmedic.network, real parsing
logic exercised with fixture outputs.
"""
import json
import os

import pytest

from netmedic.models import CommandResult, ResultCode
from netmedic.network import NetworkMedic, _elevated_is_cancelled


@pytest.fixture
def medic(tmp_path, monkeypatch):
    from netmedic import network as netmod

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    netmod.NetworkMedic._instance = None
    m = netmod.NetworkMedic()
    yield m
    netmod.NetworkMedic._instance = None


def _cmd(success=True, stdout="", stderr="", returncode=None):
    rc = 0 if success else (1 if returncode is None else returncode)
    return CommandResult(success, rc, stdout, stderr, [])


def _run_router(monkeypatch, mapping):
    """Route CommandRunner.run by command prefix; default success-empty."""

    def fake(cmd, timeout=None, **kwargs):
        for key, res in mapping.items():
            if cmd[0] == key:
                return res() if callable(res) else res
        return _cmd(True, "")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake))


# --- Pure helpers ---

def test_elevated_is_cancelled():
    assert _elevated_is_cancelled(_cmd(False, "", "", returncode=126)) is True
    assert _elevated_is_cancelled(_cmd(False, "", "cancelled by user")) is True
    assert _elevated_is_cancelled(_cmd(False, "", "Dismissed")) is True
    assert _elevated_is_cancelled(_cmd(False, "", "denied")) is False
    assert _elevated_is_cancelled(_cmd(True, "ok")) is False


def test_is_medic_virtual_iface():
    assert NetworkMedic.is_medic_virtual_iface("medicabcdef") is True
    assert NetworkMedic.is_medic_virtual_iface("eth0") is False
    assert NetworkMedic.is_medic_virtual_iface("medicXYZ") is False
    assert NetworkMedic.is_medic_virtual_iface(123) is False


def test_sanitize_iface_list():
    assert NetworkMedic._sanitize_iface_list(["medicabcdef", "eth0", 123]) == {"medicabcdef"}
    assert NetworkMedic._sanitize_iface_list("notalist") == set()
    assert NetworkMedic._sanitize_iface_list([]) == set()


def test_init_cleans_residual_ifaces(tmp_path, monkeypatch):
    from netmedic import network as netmod
    from netmedic.config import Config

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    netmod.NetworkMedic._instance = None
    state_dir = Config.get_state_dir()
    (state_dir / f"created_ifaces.{os.getpid()}.json").write_text(
        json.dumps(["medicabcdef"]), encoding="utf-8"
    )
    monkeypatch.setattr(
        netmod.NetworkMedic, "_delete_medic_iface", staticmethod(lambda i: True)
    )
    m = netmod.NetworkMedic()
    assert m._created_ifaces == set()
    netmod.NetworkMedic._instance = None


def test_singleton_reuses_instance(medic):
    from netmedic.network import NetworkMedic

    assert NetworkMedic() is medic
    assert medic._initialized is True


def test_is_process_alive():
    assert NetworkMedic._is_process_alive(os.getpid()) is True
    assert NetworkMedic._is_process_alive(999999999) is False


def test_is_physical_interface(medic):
    assert medic._is_physical_interface("enp3s0") is True
    assert medic._is_physical_interface("wlan0") is True
    assert medic._is_physical_interface("docker0") is False
    assert medic._is_physical_interface("vethabc") is False
    assert medic._is_physical_interface("br-1234") is False
    assert medic._is_physical_interface("lo") is False
    assert medic._is_physical_interface("tun0") is False


def test_check_requirement(medic):
    assert medic._check_requirement("sh") is True
    assert medic._check_requirement("definitely-not-a-binary-xyz") is False


# --- State files ---

def test_state_roundtrip_and_perms(medic):
    medic._created_ifaces = {"medicabcdef"}
    medic._save_state()
    assert medic._state_file.exists()
    assert medic._state_file.stat().st_mode & 0o777 == 0o600
    medic._created_ifaces = set()
    medic._load_state()
    assert medic._created_ifaces == {"medicabcdef"}


def test_state_rejects_poison(medic):
    medic._state_file.write_text(json.dumps(["eth0", "medicabcdef", 123]), encoding="utf-8")
    medic._load_state()
    assert medic._created_ifaces == {"medicabcdef"}


def test_state_bad_json(medic):
    medic._state_file.write_text("not json{{", encoding="utf-8")
    medic._load_state()
    assert medic._created_ifaces == set()


def test_state_save_error(medic, monkeypatch):
    monkeypatch.setattr(os, "open", MagicMock_open_raise())
    medic._created_ifaces = {"medicabcdef"}
    medic._save_state()  # logs, does not raise


def MagicMock_open_raise():
    from unittest.mock import MagicMock

    m = MagicMock(side_effect=OSError("ro"))
    return m


def test_delete_medic_iface_guards(medic, monkeypatch):
    from unittest.mock import MagicMock

    run_elevated = MagicMock(return_value=_cmd(True))
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated", staticmethod(run_elevated)
    )
    assert NetworkMedic._delete_medic_iface("eth0") is False
    run_elevated.assert_not_called()
    assert NetworkMedic._delete_medic_iface("medicabcdef") is True
    run_elevated.reset_mock()
    run_elevated.return_value = _cmd(False, "", "denied")
    assert NetworkMedic._delete_medic_iface("medicabcdef") is False


def test_reap_orphan_state(medic, monkeypatch):
    from netmedic.config import Config

    state_dir = Config.get_state_dir()
    (state_dir / "created_ifaces.notapid.json").write_text("[]", encoding="utf-8")
    (state_dir / f"created_ifaces.{os.getpid()}.json").write_text("[]", encoding="utf-8")
    dead = state_dir / "created_ifaces.999999999.json"
    dead.write_text(json.dumps(["medic111111", "eth0"]), encoding="utf-8")
    corrupt = state_dir / "created_ifaces.999999998.json"
    corrupt.write_text("{bad", encoding="utf-8")

    deleted = []
    monkeypatch.setattr(
        NetworkMedic,
        "_delete_medic_iface",
        staticmethod(lambda iface: deleted.append(iface) or True),
    )
    medic._reap_orphan_iface_state()
    assert deleted == ["medic111111"]
    assert not dead.exists()
    assert (state_dir / "created_ifaces.notapid.json").exists()
    assert (state_dir / f"created_ifaces.{os.getpid()}.json").exists()
    assert corrupt.exists()  # kept on parse error


# --- Discovery parsing ---

def test_get_default_interface_route(medic, monkeypatch):
    _run_router(monkeypatch, {"ip": _cmd(True, "default via 192.168.1.1 dev eth0 proto dhcp")})
    assert medic.get_default_interface() == "eth0"


def test_get_default_interface_bad_route_falls_back(medic, monkeypatch):
    def fake(cmd, timeout=None, **k):
        if cmd[:3] == ["ip", "route", "show"]:
            return _cmd(True, "garbage without route marker")
        return _cmd(True, "2: enp3s0: <BROADCAST> mtu 1500\n")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake))
    assert medic.get_default_interface() == "enp3s0"


def test_get_default_interface_filters_virtual(medic, monkeypatch):
    def fake(cmd, timeout=None, **k):
        if cmd[:3] == ["ip", "route", "show"]:
            return _cmd(False, "")
        return _cmd(True, "junkline\n1: lo: <LOOPBACK>\n3: docker0: <BROADCAST>\n4: wlan0: <BROADCAST>\n")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake))
    assert medic.get_default_interface() == "wlan0"


def test_get_default_interface_none(medic, monkeypatch):
    _run_router(monkeypatch, {"ip": _cmd(False, "")})
    assert medic.get_default_interface() is None


def test_get_gateway_ip(medic, monkeypatch):
    _run_router(monkeypatch, {"ip": _cmd(True, "default via 192.168.1.254 dev eth0")})
    assert medic.get_gateway_ip() == "192.168.1.254"


def test_get_gateway_ip_missing(medic, monkeypatch):
    _run_router(monkeypatch, {"ip": _cmd(True, "default dev eth0 scope link")})
    assert medic.get_gateway_ip() is None
    _run_router(monkeypatch, {"ip": _cmd(False, "")})
    assert medic.get_gateway_ip() is None


def test_get_active_nm_connection(medic, monkeypatch):
    _run_router(monkeypatch, {"nmcli": _cmd(False, "")})
    assert medic._get_active_nm_connection() is None
    _run_router(monkeypatch, {"nmcli": _cmd(True, "")})
    assert medic._get_active_nm_connection() is None
    _run_router(monkeypatch, {"nmcli": _cmd(True, "garbage-no-colon")})
    assert medic._get_active_nm_connection() is None

    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    _run_router(
        monkeypatch,
        {"nmcli": _cmd(True, "Home:eth0\nOther:wlan0\n")},
    )
    assert medic._get_active_nm_connection() == ("Home", "eth0")

    monkeypatch.setattr(medic, "get_default_interface", lambda: None)
    assert medic._get_active_nm_connection() == ("Home", "eth0")


def test_get_iface_ipv4(medic, monkeypatch):
    _run_router(
        monkeypatch, {"ip": _cmd(True, "2: eth0: <UP>\n    inet 192.168.1.10/24 brd x scope global\n")}
    )
    assert medic._get_iface_ipv4("eth0") == "192.168.1.10"
    _run_router(monkeypatch, {"ip": _cmd(True, "2: eth0: <UP> no inet here\n")})
    assert medic._get_iface_ipv4("eth0") is None
    _run_router(monkeypatch, {"ip": _cmd(False, "")})
    assert medic._get_iface_ipv4("eth0") is None


# --- Diagnostics ---

def _diag_mocks(medic, monkeypatch, *, gw="192.168.1.1", ping_ok=True,
                dns=(True, {"google.com": True}, "google.com"),
                net=(True, {"1.1.1.1:80": True}, "1.1.1.1:80"),
                portal=(False, "no portal"), nm=(None, "nm: skipped")):
    monkeypatch.setattr(medic, "get_gateway_ip", lambda: gw)
    monkeypatch.setattr(medic, "_check_dns_resolution_detailed", lambda: dns)
    monkeypatch.setattr(medic, "_check_internet_access_detailed", lambda: net)
    monkeypatch.setattr("netmedic.probes.check_captive_portal", lambda: portal)
    monkeypatch.setattr("netmedic.probes.check_nm_connectivity", lambda: nm)

    def fake_run(cmd, timeout=None, **k):
        if cmd[0] == "ping":
            return _cmd(ping_ok)
        return _cmd(True, "")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake_run))


def test_probe_delegates(medic, monkeypatch):
    monkeypatch.setattr(
        "netmedic.probes.check_dns_resolution", lambda: (True, {"h": True}, "h")
    )
    monkeypatch.setattr(
        "netmedic.probes.check_internet_access", lambda: (True, {"t": True}, "t")
    )
    assert medic._check_dns_resolution() == (True, "h")
    assert medic._check_dns_resolution_detailed() == (True, {"h": True}, "h")
    assert medic._check_internet_access() == (True, "t")
    assert medic._check_internet_access_detailed() == (True, {"t": True}, "t")


def test_diagnostics_all_ok(medic, monkeypatch):
    _diag_mocks(medic, monkeypatch, nm=(True, "nm: full"))
    res = medic.run_diagnostics()
    assert res.success is True
    assert res.code == ResultCode.OK
    assert "Gateway Reachable" in res.message


def test_diagnostics_no_gateway(medic, monkeypatch):
    _diag_mocks(medic, monkeypatch, gw=None)
    res = medic.run_diagnostics()
    assert res.success is False
    assert "Gateway Not Found" in res.message
    assert res.code == ResultCode.FAILED


def test_diagnostics_gw_unreachable(medic, monkeypatch):
    _diag_mocks(medic, monkeypatch, ping_ok=False,
                net=(False, {"1.1.1.1:80": False, "8.8.8.8:icmp": False}, "all fail"))
    res = medic.run_diagnostics()
    assert "Gateway Unreachable" in res.message
    assert res.success is False


def test_diagnostics_partial_tcp_blocked(medic, monkeypatch):
    _diag_mocks(
        medic, monkeypatch,
        net=(False, {"1.1.1.1:80": False, "8.8.8.8:icmp": True}, "tcp fail icmp ok"),
    )
    res = medic.run_diagnostics()
    assert res.code == ResultCode.PARTIAL
    assert "Partial" in res.message


def test_diagnostics_captive_hint(medic, monkeypatch):
    _diag_mocks(
        medic, monkeypatch,
        net=(False, {"1.1.1.1:80": False}, "wan down"),
        portal=(True, "possible captive portal (redirect detected)"),
    )
    res = medic.run_diagnostics()
    assert res.details["captive_portal_hint"] == "possible captive portal (redirect detected)"
    assert "suggestion" in res.details


def test_diagnostics_nm_divergence(medic, monkeypatch):
    _diag_mocks(
        medic, monkeypatch,
        dns=(False, {"google.com": False}, ""),
        net=(False, {}, "down"),
        nm=(True, "nm: full"),
    )
    res = medic.run_diagnostics()
    assert "nm_divergence" in res.details


def test_diagnostics_nm_divergence_ok_side(medic, monkeypatch):
    _diag_mocks(medic, monkeypatch, nm=(False, "nm: limited"))
    res = medic.run_diagnostics()
    assert res.success is True
    assert "nm_divergence" in res.details


def test_diagnostics_nm_exception(medic, monkeypatch):
    _diag_mocks(medic, monkeypatch)

    def boom():
        raise RuntimeError("nm down")

    monkeypatch.setattr("netmedic.probes.check_nm_connectivity", boom)
    res = medic.run_diagnostics()
    assert res.success is True
    assert res.data["nm"] == "nm: skipped"


# --- Firewall ---

def test_read_firewall_status(medic, monkeypatch):
    _run_router(monkeypatch, {"ufw": _cmd(True, "Status: inactive")})
    assert medic.read_firewall_status() == "OFF"
    assert medic.get_firewall_status() == "OFF"
    _run_router(monkeypatch, {"ufw": _cmd(True, "Status: active")})
    assert medic.read_firewall_status() == "ON"
    _run_router(monkeypatch, {"ufw": _cmd(True, "weird output")})
    assert medic.read_firewall_status() == "Unknown"


def test_toggle_firewall_unknown(medic, monkeypatch):
    _run_router(monkeypatch, {"ufw": _cmd(True, "???")})
    res = medic.toggle_firewall()
    assert res.success is False
    assert "Cannot determine" in res.message


def test_toggle_firewall_enable_ok(medic, monkeypatch):
    states = {"n": 0}

    def fake_status():
        states["n"] += 1
        return "OFF" if states["n"] == 1 else "ON"

    monkeypatch.setattr(medic, "get_firewall_status", fake_status)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True) if (verb, args) == ("toggle-firewall", {"action": "enable"}) else _cmd(False, "", "wrong")),
    )
    res = medic.toggle_firewall()
    assert res.success is True
    assert "ON" in res.message


def test_toggle_firewall_elevate_fail_and_mismatch(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_firewall_status", lambda: "OFF")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "denied")),
    )
    res = medic.toggle_firewall()
    assert res.success is False
    assert "failed" in res.message

    calls = {"n": 0}

    def fake_status():
        calls["n"] += 1
        return "OFF"  # never flips

    monkeypatch.setattr(medic, "get_firewall_status", fake_status)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    res = medic.toggle_firewall()
    assert res.success is False
    assert "Failed to toggle" in res.message


# --- flush_dns ---

def test_flush_dns_no_resolvectl(medic, monkeypatch):
    monkeypatch.setattr(medic, "_check_requirement", lambda b: False)
    res = medic.flush_dns()
    assert res.code == ResultCode.ERROR
    assert "resolvectl" in res.message


def test_flush_dns_inactive_and_cancel(medic, monkeypatch):
    monkeypatch.setattr(medic, "_check_requirement", lambda b: True)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(lambda s: False)
    )
    assert "not active" in medic.flush_dns().message

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(lambda s: True)
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "cancelled", returncode=126)),
    )
    assert medic.flush_dns().code == ResultCode.CANCELLED


def test_flush_dns_helper_missing_and_failed(medic, monkeypatch):
    monkeypatch.setattr(medic, "_check_requirement", lambda b: True)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(lambda s: True)
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "helper-missing install policy")),
    )
    assert medic.flush_dns().code == ResultCode.ERROR
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "flush failed")),
    )
    assert medic.flush_dns().code == ResultCode.FAILED


def test_flush_dns_post_service_down_and_ok(medic, monkeypatch):
    monkeypatch.setattr(medic, "_check_requirement", lambda b: True)
    states = {"n": 0}

    def fake_active(svc):
        states["n"] += 1
        return states["n"] == 1  # active before flush, down after

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(fake_active)
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    res = medic.flush_dns()
    assert res.code == ResultCode.FAILED
    assert "became inactive" in res.message

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(lambda s: True)
    )
    monkeypatch.setattr(medic, "_check_dns_resolution", lambda: (True, "google.com"))
    res = medic.flush_dns()
    assert res.code == ResultCode.EXECUTED
    assert res.details["post_flush_dns_ok"] is True


# --- change_dns ---

def test_change_dns_guards(medic, monkeypatch):
    res = medic.change_dns("not-an-ip")
    assert res.code == ResultCode.ERROR
    monkeypatch.setattr(medic, "_check_requirement", lambda b: False)
    assert "no disponible" in medic.change_dns("1.1.1.1").message
    monkeypatch.setattr(medic, "_check_requirement", lambda b: True)
    monkeypatch.setattr(medic, "_get_active_nm_connection", lambda: None)
    assert "No active" in medic.change_dns("1.1.1.1").message


def test_change_dns_elevate_and_verify(medic, monkeypatch):
    monkeypatch.setattr(medic, "_check_requirement", lambda b: True)
    monkeypatch.setattr(medic, "_get_active_nm_connection", lambda: ("Home", "eth0"))
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "cancelled", returncode=126)),
    )
    assert medic.change_dns("1.1.1.1").code == ResultCode.CANCELLED
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "nm fail")),
    )
    assert medic.change_dns("1.1.1.1").code == ResultCode.FAILED

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: _cmd(True, "ipv4.dns: 9.9.9.9")),
    )
    res = medic.change_dns("1.1.1.1")
    assert res.code == ResultCode.FAILED
    assert "not in" in res.message

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: _cmd(True, "ipv4.dns: 1.1.1.1")),
    )
    monkeypatch.setattr(medic, "_check_dns_resolution", lambda: (True, "google.com"))
    res = medic.change_dns("1.1.1.1")
    assert res.code == ResultCode.OK
    assert "1.1.1.1" in res.message


# --- renew_ip ---

def test_renew_no_iface_and_invalid(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: None)
    assert medic.renew_ip().code == ResultCode.ERROR
    monkeypatch.setattr(medic, "get_default_interface", lambda: "bad;iface")
    assert "invalid interface" in medic.renew_ip().message.lower()


def test_renew_nmcli_changed_and_retained(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    ips = {"before": "192.168.1.10", "after": "192.168.1.11"}
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: ips["after"] if ips.get("read_after") else ips["before"])
    monkeypatch.setattr("netmedic.network.shutil.which", lambda b: "/usr/bin/" + b)

    def fake_elevated(verb, args=None, timeout=None, **k):
        ips["read_after"] = True
        return _cmd(True)

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated", staticmethod(fake_elevated)
    )
    monkeypatch.setattr(medic, "get_gateway_ip", lambda: None)
    res = medic.renew_ip()
    assert res.code == ResultCode.EXECUTED
    assert "IP changed" in res.message

    ips.update({"before": "192.168.1.10", "after": "192.168.1.10", "read_after": False})
    res = medic.renew_ip()
    assert "retained" in res.message


def test_renew_unverifiable_and_plain_dhclient_missing(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: None)
    monkeypatch.setattr("netmedic.network.shutil.which", lambda b: "/usr/bin/" + b)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(True)),
    )
    monkeypatch.setattr(medic, "get_gateway_ip", lambda: None)
    res = medic.renew_ip()
    assert res.code == ResultCode.EXECUTED
    assert "not verifiable" in res.message

    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: "192.168.1.10")
    monkeypatch.setattr(
        "netmedic.network.shutil.which", lambda b: "/usr/bin/nmcli" if b == "nmcli" else None
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(False, "", "plain boom")),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.ERROR
    assert "DHCP renewal failed" in res.message


def test_renew_gateway_ping_fail(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: "192.168.1.10")
    monkeypatch.setattr("netmedic.network.shutil.which", lambda b: "/usr/bin/" + b)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(True)),
    )
    monkeypatch.setattr(medic, "get_gateway_ip", lambda: "192.168.1.1")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: _cmd(False, "")),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.EXECUTED
    assert res.details["gateway_ok"] is False


def test_renew_ip_lost_and_cancel(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr("netmedic.network.shutil.which", lambda b: "/usr/bin/" + b)
    reads = {"n": 0}

    def fake_ip(iface):
        reads["n"] += 1
        return "192.168.1.10" if reads["n"] == 1 else None

    monkeypatch.setattr(medic, "_get_iface_ipv4", fake_ip)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.FAILED
    assert "no IPv4" in res.message

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "cancelled", returncode=126)),
    )
    assert medic.renew_ip().code == ResultCode.CANCELLED


def test_renew_dhclient_paths(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: "192.168.1.10")
    # nmcli present but helper missing + no dhclient binary
    monkeypatch.setattr(
        "netmedic.network.shutil.which", lambda b: "/usr/bin/nmcli" if b == "nmcli" else None
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(False, "", "helper-missing policy")),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.ERROR
    assert "helper" in res.message.lower()

    # dhclient present + success
    monkeypatch.setattr(
        "netmedic.network.shutil.which", lambda b: "/sbin/dhclient" if b == "dhclient" else None
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(True)),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.EXECUTED
    assert "renewed" in res.message.lower()

    # dhclient reports failure
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(False, "", "dhcp nak")),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.FAILED


def test_renew_dhclient_cancel_helper_lost(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: "192.168.1.10")
    monkeypatch.setattr(
        "netmedic.network.shutil.which", lambda b: "/sbin/dhclient" if b == "dhclient" else None
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(False, "", "cancelled", returncode=126)),
    )
    assert medic.renew_ip().code == ResultCode.CANCELLED

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(False, "", "helper-missing policy")),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.ERROR
    assert "helper" in res.message.lower()

    reads = {"n": 0}

    def fake_ip(iface):
        reads["n"] += 1
        return "192.168.1.10" if reads["n"] == 1 else None

    monkeypatch.setattr(medic, "_get_iface_ipv4", fake_ip)
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, timeout=None, **k: _cmd(True)),
    )
    res = medic.renew_ip()
    assert res.code == ResultCode.FAILED
    assert "no IPv4" in res.message


# --- reset / restart ---

def test_reset_stack_paths(medic, monkeypatch):
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "cancelled", returncode=126)),
    )
    assert medic.reset_tcp_ip_stack().code == ResultCode.CANCELLED
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "failed")),
    )
    assert medic.reset_tcp_ip_stack().code == ResultCode.FAILED

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(lambda s: True)
    )
    assert medic.reset_tcp_ip_stack().code == ResultCode.OK

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.is_service_active", staticmethod(lambda s: False)
    )
    monkeypatch.setattr("time.sleep", lambda s: None)
    res = medic.reset_tcp_ip_stack()
    assert res.code == ResultCode.FAILED
    assert "not active" in res.message


def test_restart_adapter_guards(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: None)
    assert medic.restart_adapter().code == ResultCode.ERROR
    monkeypatch.setattr(medic, "get_default_interface", lambda: "bad iface!")
    assert "invalid" in medic.restart_adapter().message.lower()


def test_restart_adapter_elevate_and_poll(medic, monkeypatch):
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "cancelled", returncode=126)),
    )
    assert medic.restart_adapter().code == ResultCode.CANCELLED
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "down fail")),
    )
    assert medic.restart_adapter().code == ResultCode.FAILED

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: _cmd(True, json.dumps([{"operstate": "UP"}]))),
    )
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: "192.168.1.10")
    res = medic.restart_adapter()
    assert res.code == ResultCode.OK
    assert res.details["operstate"] == "UP"


def test_restart_adapter_text_fallback_and_timeout(medic, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )

    def fake_run(cmd, timeout=None, **k):
        if "-j" in cmd:
            return _cmd(True, "not-json{{{")
        return _cmd(True, "2: eth0: <UP> state UP mtu 1500")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake_run))
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    res = medic.restart_adapter()
    assert res.code == ResultCode.OK

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run",
        staticmethod(lambda cmd, timeout=None, **k: _cmd(False, "")),
    )
    res = medic.restart_adapter()
    assert res.code == ResultCode.FAILED
    assert "not UP" in res.message


def test_restart_adapter_down_then_details(medic, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(medic, "get_default_interface", lambda: "eth0")
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )

    def fake_run(cmd, timeout=None, **k):
        if "-j" in cmd:
            return _cmd(True, json.dumps([{"operstate": "DOWN"}]))
        return _cmd(True, "2: eth0: <DOWN> state DOWN mtu 1500")

    monkeypatch.setattr("netmedic.network.CommandRunner.run", staticmethod(fake_run))
    monkeypatch.setattr(medic, "_get_iface_ipv4", lambda iface: None)
    res = medic.restart_adapter()
    assert res.code == ResultCode.FAILED
    assert "not UP" in res.message
    assert "DOWN" in (res.details or "")


# --- cleanup / virtual adapter ---

def test_cleanup_paths(medic, monkeypatch):
    res = medic.cleanup()
    assert res.success is True
    assert "Nothing to clean" in res.message

    medic._created_ifaces = {"medicabcdef", "medic123456"}
    monkeypatch.setattr(NetworkMedic, "_delete_medic_iface", staticmethod(lambda i: True))
    res = medic.cleanup()
    assert res.success is True
    assert medic._created_ifaces == set()

    medic._created_ifaces = {"medicabcdef", "medic123456"}
    monkeypatch.setattr(
        NetworkMedic, "_delete_medic_iface", staticmethod(lambda i: i == "medicabcdef")
    )
    res = medic.cleanup()
    assert res.success is False
    assert "Failed on" in res.message
    assert medic._created_ifaces == {"medic123456"}


def test_create_virtual_adapter(medic, monkeypatch):
    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(True)),
    )
    res = medic.create_virtual_adapter()
    assert res.success is True
    assert len(medic._created_ifaces) == 1
    assert medic._state_file.exists()

    monkeypatch.setattr(
        "netmedic.network.CommandRunner.run_elevated",
        staticmethod(lambda verb, args=None, **k: _cmd(False, "", "denied")),
    )
    assert medic.create_virtual_adapter().success is False


def test_diagnostics_portal_hijack_not_healthy(medic, monkeypatch):
    """B-1: TCP success behind a portal must not report healthy."""
    _diag_mocks(
        medic, monkeypatch,
        net=(True, {"1.1.1.1:80": True}, "1.1.1.1:80"),
        portal=(True, "possible captive portal (redirect detected)"),
    )
    res = medic.run_diagnostics()
    assert res.success is False
    assert res.code == ResultCode.PARTIAL
    assert "Portal detected" in res.message
    assert res.details["captive_portal_hint"] == "possible captive portal (redirect detected)"
    # Raw probe facts stay honest: TCP was reachable, verdict is portal.
    assert res.data["internet_ok"] is True


def test_diagnostics_no_portal_stays_healthy(medic, monkeypatch):
    _diag_mocks(medic, monkeypatch, portal=(False, "no portal (204)"))
    res = medic.run_diagnostics()
    assert res.success is True
    assert res.code == ResultCode.OK


def test_portal_url_override(monkeypatch):
    from netmedic import probes as probes_mod

    monkeypatch.delenv("NETMEDIC_PORTAL_URL", raising=False)
    assert "connectivity-check.ubuntu.com" in probes_mod._portal_url()
    monkeypatch.setenv("NETMEDIC_PORTAL_URL", "http://portal.corp.example/generate_204")
    assert probes_mod._portal_url() == "http://portal.corp.example/generate_204"

    seen = {}

    def fake_run(cmd, timeout=None, **kwargs):
        seen["url"] = cmd[-1]
        return _cmd(True, "HTTP/1.1 204 No Content")

    monkeypatch.setattr(probes_mod.CommandRunner, "run", staticmethod(fake_run))
    ok, msg = probes_mod.check_captive_portal()
    assert seen["url"] == "http://portal.corp.example/generate_204"
    assert ok is False
    assert "204" in msg
