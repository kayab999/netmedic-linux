from unittest.mock import patch

from netmedic.sensors import get_network_snapshot


@patch("netmedic.network.NetworkMedic.read_firewall_status", return_value="OFF")
def test_firewall_snapshot_avoids_singleton_init(mock_read):
    snapshot = get_network_snapshot()
    mock_read.assert_called_once()
    assert snapshot["firewall"] == "OFF"