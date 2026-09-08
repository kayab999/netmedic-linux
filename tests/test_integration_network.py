from unittest.mock import patch, MagicMock
from netmedic.network import NetworkMedic


@patch("netmedic.system.CommandRunner.run")
def test_network_medic_diagnostics_integration(mock_run):
    def _run(cmd, *a, **kw):
        return MagicMock(success=True, stdout="test output", stderr="")
    mock_run.side_effect = _run

    medic = NetworkMedic()
    with patch.object(NetworkMedic, "get_gateway_ip", return_value="192.168.1.1"):
        res = medic.run_diagnostics()

    assert res.success is True
    assert "Gateway Reachable" in res.message
    assert "DNS Resolution OK" in res.message
    assert "Internet Access OK" in res.message
    assert mock_run.call_count >= 3


@patch("netmedic.system.CommandRunner.is_service_active", return_value=True)
@patch("netmedic.system.CommandRunner.run_elevated")
def test_network_medic_flush_dns_integration(mock_elevated, mock_active):
    mock_elevated.return_value = MagicMock(success=True, stdout="", stderr="")

    medic = NetworkMedic()
    res = medic.flush_dns()

    assert res.success is True
    mock_elevated.assert_called_once_with("flush-dns")
