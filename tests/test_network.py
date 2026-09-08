from unittest.mock import patch, MagicMock
from netmedic.network import NetworkMedic

@patch('netmedic.system.CommandRunner.run')
def test_diagnostics_success(mock_run):
    def _run(cmd, *a, **kw):
        if cmd[0] == "ip" and "default" in cmd:
            return MagicMock(success=True, stdout="default via 192.168.1.1 dev eth0")
        if cmd[0] == "ping":
            return MagicMock(success=True)
        if cmd[0] == "getent":
            return MagicMock(success=True)
        if cmd[0] == "curl":
            return MagicMock(success=True, stdout="HTTP/1.1 200 OK")
        return MagicMock(success=True)
    mock_run.side_effect = _run
    
    medic = NetworkMedic()
    res = medic.run_diagnostics()
    
    assert res.success is True
    assert "Gateway Reachable" in res.message
    assert "DNS Resolution OK" in res.message

@patch('netmedic.system.CommandRunner.run')
def test_diagnostics_fail_dns(mock_run):
    def _run(cmd, *a, **kw):
        if cmd[0] == "ip" and "default" in cmd:
            return MagicMock(success=True, stdout="default via 192.168.1.1 dev eth0")
        if cmd[0] == "ping":
            return MagicMock(success=True)
        if cmd[0] == "getent":
            return MagicMock(success=False)
        if cmd[0] == "curl":
            return MagicMock(success=True, stdout="HTTP/1.1 200 OK")
        return MagicMock(success=True)
    mock_run.side_effect = _run
    
    medic = NetworkMedic()
    res = medic.run_diagnostics()
    
    assert res.success is False
    assert "DNS Resolution Failed" in res.message
