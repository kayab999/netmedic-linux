"""R1: internet_ok is TCP/HTTPS only. ICMP is details, never overall_ok."""
import socket
import time
from unittest.mock import MagicMock, patch

from netmedic.models import ResultCode
from netmedic.network import NetworkMedic
from netmedic.probes import (
    check_dns_resolution,
    check_dns_resolution_detailed,
    check_internet_access,
)


def _cmd(success, stdout=""):
    return MagicMock(success=success, stdout=stdout, stderr="", returncode=0 if success else 1)


@patch("netmedic.system.CommandRunner.run")
@patch("socket.create_connection", side_effect=ConnectionRefusedError("refused"))
def test_icmp_ok_tcp_fail_is_not_internet_ok(mock_connect, mock_run):
    def _run(cmd, *a, **kw):
        if cmd and cmd[0] == "ping":
            return _cmd(True)
        return _cmd(False)

    mock_run.side_effect = _run
    ok, per, _label = check_internet_access()
    assert ok is False
    assert per.get("1.1.1.1:80") is False
    assert per.get("8.8.8.8:80") is False
    assert per.get("1.1.1.1:443") is False
    assert per.get("8.8.8.8:icmp") is True


@patch("socket.create_connection")
def test_http_success_is_internet_ok(mock_connect):
    def _connect(address, timeout=None):
        if address == ("1.1.1.1", 80):
            return MagicMock()
        raise ConnectionRefusedError("refused")

    mock_connect.side_effect = _connect
    ok, per, label = check_internet_access()
    assert ok is True
    assert per.get("1.1.1.1:80") is True
    assert label == "1.1.1.1:80"


@patch("netmedic.probes._http_probe", return_value={"status": 204, "headers": {}, "body": "", "error": None, "tcp_ok": True, "http_ok": True, "tls_ok": None, "reason_code": "ok"})
@patch("socket.create_connection", side_effect=ConnectionRefusedError("refused"))
@patch("netmedic.probes.check_dns_resolution", lambda: (True, {"google.com": True}, "google.com"))
@patch("netmedic.system.CommandRunner.run")
def test_diagnostics_tcp_blocked_icmp_ok_is_partial(mock_run, mock_connect, mock_http):
    def _run(cmd, *a, **kw):
        if cmd[0] == "ip" and "default" in cmd:
            return _cmd(True, "default via 192.168.1.1 dev eth0")
        if cmd[0] == "getent":
            return _cmd(True, "1.1.1.1 cloudflare.com")
        if cmd[0] == "curl":
            return _cmd(False)
        if cmd[0] == "ping":
            return _cmd(True)
        if cmd[0] == "nmcli":
            return _cmd(False)
        return _cmd(False)

    mock_run.side_effect = _run
    res = NetworkMedic().run_diagnostics()
    assert res.data["internet_ok"] is False
    assert res.data["dns_ok"] is True
    assert res.data["gateway_ok"] is True
    assert res.code == ResultCode.PARTIAL
    assert res.details["per_probe"]["net_per"].get("8.8.8.8:icmp") is True
    assert "TCP blocked" in res.message


@patch("netmedic.probes._http_probe", return_value={"status": 302, "headers": {"Location": "http://portal.local/"}, "body": "", "error": None, "tcp_ok": True, "http_ok": True, "tls_ok": None, "reason_code": "ok"})
@patch("socket.create_connection", side_effect=ConnectionRefusedError("refused"))
@patch("netmedic.probes.check_dns_resolution", lambda: (True, {"google.com": True}, "google.com"))
@patch("netmedic.system.CommandRunner.run")
def test_captive_hint_when_dns_ok_tcp_fail(mock_run, mock_connect, mock_http):
    def _run(cmd, *a, **kw):
        if cmd[0] == "ip" and "default" in cmd:
            return _cmd(True, "default via 192.168.1.1 dev eth0")
        if cmd[0] == "getent":
            return _cmd(True, "1.1.1.1 cloudflare.com")
        if cmd[0] == "curl":
            url = " ".join(cmd)
            if "connectivity-check" in url:
                return _cmd(True, "HTTP/1.1 302 Found\nLocation: http://portal.local/")
            return _cmd(False)
        if cmd[0] == "ping":
            return _cmd(True)
        if cmd[0] == "nmcli":
            return _cmd(False)
        return _cmd(False)

    mock_run.side_effect = _run
    res = NetworkMedic().run_diagnostics()
    assert res.data["dns_ok"] is True
    assert res.data["internet_ok"] is False
    assert res.details.get("captive_portal_hint")
    assert "portal" in str(res.details.get("captive_portal_hint")).lower()


def test_dns_resolution_native_success(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, per, host = check_dns_resolution()
    assert ok is True
    assert all(per.values())
    assert host in per


def test_dns_resolution_detailed_reports_addresses_and_family(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "google.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("142.250.0.1", 0))]
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, detailed, host = check_dns_resolution_detailed()
    assert ok is True
    assert detailed["google.com"]["success"] is True
    assert detailed["google.com"]["addresses"] == ["142.250.0.1"]
    assert "ipv4" in detailed["google.com"]["families"]
    assert detailed["cloudflare.com"]["success"] is False
    assert detailed["cloudflare.com"]["reason_code"] == "eai_noname"
    assert host == "google.com"


def test_dns_resolution_reports_eai_again(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        raise socket.gaierror(socket.EAI_AGAIN, "Temporary failure")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, per, host = check_dns_resolution()
    assert ok is False
    assert all(value is False for value in per.values())
    assert host == ""


def test_dns_resolution_timeout_is_bounded(monkeypatch):
    import netmedic.probes as probes_mod

    probes_mod._DNS_TIMEOUT = 0.05

    def slow_getaddrinfo(host, port, *args, **kwargs):
        time.sleep(1.0)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", slow_getaddrinfo)
    start = time.monotonic()
    ok, per, host = check_dns_resolution()
    elapsed = time.monotonic() - start
    assert ok is False
    assert elapsed < 1.0
    assert all(value is False for value in per.values())
