import pytest
from unittest.mock import patch, MagicMock
from netmedic.system import CommandRunner
from netmedic.models import CommandResult

@patch('subprocess.run')
def test_command_runner_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="test output", stderr="")
    
    res = CommandRunner.run(["echo", "test"])
    
    assert res.success is True
    assert res.returncode == 0
    assert res.stdout == "test output"
    mock_run.assert_called_once()

@patch('subprocess.run')
def test_command_runner_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
    
    res = CommandRunner.run(["ls", "/not-exist"])
    
    assert res.success is False
    assert res.returncode == 1
    assert res.stderr == "error"

@patch('subprocess.run')
import subprocess
def test_command_runner_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 10", timeout=5)
    
    res = CommandRunner.run(["sleep", "10"], timeout=1)
    
    assert res.success is False
    assert res.returncode == -1
    assert "Timeout" in res.stderr

@patch('os.geteuid', return_value=1000)
@patch('shutil.which', return_value="/usr/bin/pkexec")
@patch('subprocess.run')
def test_command_runner_root_elevation(mock_run, mock_which, mock_geteuid):
    mock_run.return_value = MagicMock(returncode=0, stdout="root", stderr="")
    
    res = CommandRunner.run(["whoami"], require_root=True)
    
    assert res.success is True
    # Verify pkexec was prepended
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd[0] == "pkexec"
    assert called_cmd[1] == "whoami"

@patch('os.geteuid', return_value=1000)
@patch('shutil.which', return_value="/usr/bin/pkexec")
@patch('subprocess.run')
def test_command_runner_root_cancellation(mock_run, mock_which, mock_geteuid):
    # Simulate user cancelling pkexec dialog
    mock_run.return_value = MagicMock(returncode=126, stdout="", stderr="Error executing command as another user: Request dismissed")
    
    res = CommandRunner.run(["whoami"], require_root=True)
    
    assert res.success is False
    assert res.returncode == 126
    assert "cancelada" in res.stderr.lower()
