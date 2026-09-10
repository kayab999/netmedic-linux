"""R1: internet_ok is TCP/HTTPS only. ICMP is details, never overall_ok."""
from unittest.mock import MagicMock, patch

from netmedic.models import ResultCode
from netmedic.network import NetworkMedic
from netmedic.probes import check_internet_access


def _cmd(success, stdout=""):
    return MagicMock(success=success, stdout=stdout, stderr="", returncode=0 if success else 1)


@patch("netmedic.system.CommandRunner.run")
def test_icmp_ok_tcp_fail_is_not_internet_ok(mock_run):
    def _run(cmd, *a, **kw):
        if cmd and cmd[0] == "curl":
            return _cmd(False)
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


@patch("netmedic.system.CommandRunner.run")
def test_http_success_is_internet_ok(mock_run):
    def _run(cmd, *a, **kw):
        if cmd and cmd[0] == "curl" and "http://1.1.1.1" in cmd:
            return _cmd(True, "HTTP/1.1 200 OK")
        return _cmd(False)

    mock_run.side_effect = _run
    ok, per, label = check_internet_access()
    assert ok is True
    assert per.get("1.1.1.1:80") is True
    assert label == "1.1.1.1:80"


@patch("netmedic.system.CommandRunner.run")
def test_diagnostics_tcp_blocked_icmp_ok_is_partial(mock_run):
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


@patch("netmedic.system.CommandRunner.run")
def test_captive_hint_when_dns_ok_tcp_fail(mock_run):
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
