import pytest
from unittest.mock import patch, MagicMock
from netmedic.network import NetworkMedic
from netmedic.models import NetResult

@patch('netmedic.system.CommandRunner.run')
def test_diagnostics_success(mock_run):
    # Setup multiple return values for the sequence:
    # 1. get_gateway_ip (ip route show default)
    # 2. ping gateway
    # 3. getent hosts
    # 4. curl http
    
    mock_run.side_effect = [
        MagicMock(success=True, stdout="default via 192.168.1.1 dev eth0"),
        MagicMock(success=True),
        MagicMock(success=True),
        MagicMock(success=True)
    ]
    
    medic = NetworkMedic()
    res = medic.run_diagnostics()
    
    assert res.success is True
    assert "Gateway Reachable" in res.message
    assert "DNS Resolution OK" in res.message

@patch('netmedic.system.CommandRunner.run')
def test_diagnostics_fail_dns(mock_run):
    mock_run.side_effect = [
        MagicMock(success=True, stdout="default via 192.168.1.1 dev eth0"),
        MagicMock(success=True),
        MagicMock(success=False), # DNS resolution fails
        MagicMock(success=True)
    ]
    
    medic = NetworkMedic()
    res = medic.run_diagnostics()
    
    assert res.success is False
    assert "DNS Resolution Failed" in res.message
