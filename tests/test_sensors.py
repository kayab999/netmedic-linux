from unittest.mock import MagicMock, patch

from netmedic.sensors import get_network_snapshot


@patch("netmedic.network.NetworkMedic")
@patch("netmedic.sensors._nm_active_connection")
@patch("netmedic.sensors._rfkill_blocked", return_value=False)
@patch("netmedic.sensors._vpn_status", return_value={"active": True, "provider": "openvpn"})
@patch("netmedic.sensors._read_resolvers", return_value=["1.1.1.1"])
@patch("netmedic.sensors.subprocess.run")
def test_snapshot_includes_enriched_fields(
    mock_proc_run,
    mock_resolvers,
    mock_vpn,
    mock_rfkill,
    mock_nm,
    mock_medic_cls,
):
    mock_proc_run.side_effect = [
        MagicMock(returncode=0, stdout='[{"ifname":"wlan0","operstate":"UP"}]', stderr=""),
        MagicMock(returncode=0, stdout="64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms\n", stderr=""),
    ]
    mock_nm.return_value = {"name": "home", "device": "wlan0", "type": "wifi"}
    mock_medic_cls.return_value.get_firewall_status.return_value = "ON"

    with patch("netmedic.sensors.CommandRunner.run") as mock_cmd:
        mock_cmd.return_value = MagicMock(success=True, stdout="default via 192.168.1.1 dev wlan0", stderr="")
        snapshot = get_network_snapshot()

    assert snapshot["ifaces"]["wlan0"] == "UP"
    assert snapshot["dns"] == ["1.1.1.1"]
    assert snapshot["vpn"]["active"] is True
    assert snapshot["nm_connection"]["name"] == "home"
    assert snapshot["firewall"] == "ON"
    assert snapshot["default_iface"] == "wlan0"