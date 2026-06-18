from unittest.mock import patch, MagicMock

from netmedic.network import NetworkMedic


@patch("netmedic.system.CommandRunner.run")
@patch("netmedic.network.shutil.which", return_value="/usr/bin/nmcli")
def test_change_dns_success(mock_which, mock_run):
    mock_run.side_effect = [
        MagicMock(success=True, stdout="Wired connection 1", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
    ]

    medic = NetworkMedic()
    result = medic.change_dns("1.1.1.1")

    assert result.success is True
    assert "1.1.1.1" in result.message
    assert mock_run.call_count == 3


def test_change_dns_rejects_invalid_ip():
    medic = NetworkMedic()
    result = medic.change_dns("not-an-ip")
    assert result.success is False
    assert "inválido" in result.message.lower()


@patch("netmedic.network.shutil.which", return_value=None)
def test_change_dns_requires_nmcli(mock_which):
    medic = NetworkMedic()
    result = medic.change_dns("8.8.8.8")
    assert result.success is False