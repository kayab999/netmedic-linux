from unittest.mock import patch, MagicMock
from netmedic.network import NetworkMedic

@patch('netmedic.system.CommandRunner.run')
def test_network_medic_diagnostics_integration(mock_run):
    # Mock network tools output (ping, getent, curl)
    mock_run.side_effect = [
        MagicMock(success=True, stdout="test output", stderr=""), # ping
        MagicMock(success=True, stdout="test output", stderr=""), # getent
        MagicMock(success=True, stdout="test output", stderr=""), # curl
    ]
    
    medic = NetworkMedic()
    # Need to bypass actual gateway lookup or mock it
    with patch.object(NetworkMedic, 'get_gateway_ip', return_value="192.168.1.1"):
        res = medic.run_diagnostics()
        
    assert res.success is True
    assert "Gateway Reachable" in res.message
    assert "DNS Resolution OK" in res.message
    assert "Internet Access OK" in res.message
    assert mock_run.call_count == 3

@patch('netmedic.system.CommandRunner.run')
def test_network_medic_flush_dns_integration(mock_run):
    mock_run.return_value = MagicMock(success=True, stdout="", stderr="")
    
    medic = NetworkMedic()
    res = medic.flush_dns()
    
    assert res.success is True
    # Verify it calls systemd-resolve or similar
    called_cmd = mock_run.call_args[0][0]
    assert "resolvectl" in called_cmd or "systemd-resolve" in called_cmd
