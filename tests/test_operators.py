from unittest.mock import patch, MagicMock
from netmedic.operators.wifi import WifiOperator
from netmedic.operators.vpn.angristan import AngristanOperator

@patch('netmedic.system.CommandRunner.run')
def test_wifi_scan_congestion(mock_run):
    mock_run.return_value = MagicMock(
        success=True,
        stdout=(
            '[{"SSID":"SSID1","CHAN":1},'
            '{"SSID":"SSID2","CHAN":6},'
            '{"SSID":"SSID3","CHAN":1}]'
        ),
        stderr="",
    )

    wifi = WifiOperator()
    res = wifi.scan_congestion()

    assert res.success is True
    assert "Most congested channel: 1" in res.message
    assert res.data["1"] == 2
    assert res.data["6"] == 1

@patch('netmedic.system.CommandRunner.run')
@patch('netmedic.operators.vpn.angristan.AngristanOperator._verify_integrity', return_value=True)
def test_angristan_status_running(mock_verify, mock_run, tmp_path, monkeypatch):
    # Do not patch pathlib.Path.exists globally — that makes Config._ensure_dir
    # skip mkdir then fail on a missing ~/.local/share/netmedic (clean CI homes).
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    script = tmp_path / "netmedic" / "operators" / "openvpn-install.sh"
    script.parent.mkdir(parents=True)
    script.write_bytes(b"#!/bin/sh\n")
    mock_run.return_value = MagicMock(success=True, stdout="active (running)", stderr="")

    vpn = AngristanOperator()
    res = vpn.check_status()

    assert res.success is True
    assert res.message == "running"