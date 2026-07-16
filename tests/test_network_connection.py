from unittest.mock import MagicMock, patch

from netmedic.network import NetworkMedic


@patch("netmedic.network.CommandRunner.run")
def test_get_active_nm_connection_prefers_default_iface(mock_run):
    medic = NetworkMedic()
    mock_run.side_effect = [
        MagicMock(
            success=True,
            stdout="docker0:docker0:bridge\nhome:wlan0:802-11-wireless\n",
            stderr="",
        ),
        MagicMock(success=True, stdout="default via 192.168.1.1 dev wlan0", stderr=""),
    ]

    with patch.object(medic, "get_default_interface", return_value="wlan0"):
        active = medic._get_active_nm_connection()
    assert active == ("home", "wlan0")