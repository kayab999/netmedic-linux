from unittest.mock import patch, MagicMock
from netmedic.models import ResultCode
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

    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    assert "Most congested channel: 1" in res.message
    assert res.data["1"] == 2
    assert res.data["6"] == 1

@patch('netmedic.system.CommandRunner.run')
def test_angristan_status_running(mock_run, tmp_path, monkeypatch):
    # F2: installed-ness is the server config marker, not a downloaded copy.
    marker = tmp_path / "server.conf"
    marker.write_text("port 1194\n")
    monkeypatch.setattr(AngristanOperator, "INSTALL_MARKER_PATH", str(marker))
    mock_run.return_value = MagicMock(success=True, stdout="active (running)", stderr="")

    vpn = AngristanOperator()
    res = vpn.check_status()

    assert res.code in (ResultCode.OK, ResultCode.EXECUTED)
    assert res.message == "running"