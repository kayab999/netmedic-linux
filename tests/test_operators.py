import pytest
from unittest.mock import patch, MagicMock
from netmedic.operators.wifi import WifiOperator
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.models import NetResult

@patch('netmedic.system.CommandRunner.run')
def test_wifi_scan_congestion(mock_run):
    # Mock nmcli response
    mock_run.return_value = MagicMock(
        success=True, 
        stdout="SSID1:1:100\nSSID2:6:50\nSSID3:1:80",
        stderr=""
    )
    
    wifi = WifiOperator()
    res = wifi.scan_congestion()
    
    assert res.success is True
    assert "Canal más congestionado: 1" in res.message
    assert res.data['1'] == 2
    assert res.data['6'] == 1

@patch('netmedic.system.CommandRunner.run')
@patch('netmedic.operators.vpn.angristan.AngristanOperator._verify_integrity', return_value=True)
@patch('pathlib.Path.exists', return_value=True)
def test_angristan_status_running(mock_exists, mock_verify, mock_run):
    # Mock systemctl response
    mock_run.return_value = MagicMock(success=True, stdout="active (running)", stderr="")
    
    vpn = AngristanOperator()
    res = vpn.check_status()
    
    assert res.success is True
    assert res.message == "running"