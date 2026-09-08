from unittest.mock import MagicMock, patch

from netmedic.network import NetworkMedic


@patch("netmedic.network.CommandRunner.run_elevated")
@patch("netmedic.network.CommandRunner.run")
@patch("netmedic.network.shutil.which", return_value="/usr/bin/nmcli")
def test_change_dns_success(mock_which, mock_run, mock_elevated):
    def _run(cmd, *a, **kw):
        if cmd[:3] == ["nmcli", "-t", "-f"]:
            return MagicMock(success=True, stdout="docker0:docker0:bridge\nhome:wlan0:802-11-wireless\n", stderr="")
        if cmd[:3] == ["nmcli", "con", "show"]:
            return MagicMock(success=True, stdout="connection.id: home\nipv4.dns: 1.1.1.1\n", stderr="")
        if cmd[0] == "getent":
            return MagicMock(success=True)
        if cmd[0] == "curl":
            return MagicMock(success=True)
        return MagicMock(success=True)
    mock_run.side_effect = _run
    mock_elevated.return_value = MagicMock(success=True, stdout="", stderr="")

    medic = NetworkMedic()
    with patch.object(medic, "get_default_interface", return_value="wlan0"):
        result = medic.change_dns("1.1.1.1")

    assert result.success is True
    assert "home" in result.message
    assert "1.1.1.1" in result.message
    mock_elevated.assert_called_once_with(
        "change-dns",
        {"server": "1.1.1.1", "connection": "home"},
    )


def test_change_dns_rejects_invalid_ip():
    medic = NetworkMedic()
    result = medic.change_dns("not-an-ip")
    assert result.success is False
    assert "invalid" in result.message.lower() or "inválido" in result.message.lower()


@patch("netmedic.network.shutil.which", return_value=None)
def test_change_dns_requires_nmcli(mock_which):
    medic = NetworkMedic()
    result = medic.change_dns("8.8.8.8")
    assert result.success is False
