import subprocess
from unittest.mock import MagicMock, patch

from netmedic.system import CommandRunner


def _mock_popen(returncode=0, stdout="", stderr=""):
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    proc.pid = 4242
    return proc


@patch("subprocess.Popen")
def test_command_runner_success(mock_popen):
    mock_popen.return_value = _mock_popen(stdout="test output")

    res = CommandRunner.run(["echo", "test"])

    assert res.success is True
    assert res.returncode == 0
    assert res.stdout == "test output"
    mock_popen.assert_called_once()


@patch("subprocess.Popen")
def test_command_runner_failure(mock_popen):
    mock_popen.return_value = _mock_popen(returncode=1, stderr="error")

    res = CommandRunner.run(["ls", "/not-exist"])

    assert res.success is False
    assert res.returncode == 1
    assert res.stderr == "error"


@patch("netmedic.system.CommandRunner._terminate_process_group")
@patch("subprocess.Popen")
def test_command_runner_timeout(mock_popen, mock_kill):
    proc = _mock_popen()
    proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="sleep 10", timeout=5)
    mock_popen.return_value = proc

    res = CommandRunner.run(["sleep", "10"], timeout=1)

    assert res.success is False
    assert res.returncode == -1
    assert "Timeout" in res.stderr
    mock_kill.assert_called_once_with(proc)


@patch("os.geteuid", return_value=1000)
@patch("shutil.which", return_value="/usr/bin/pkexec")
@patch("subprocess.Popen")
def test_command_runner_root_elevation(mock_popen, mock_which, mock_geteuid):
    mock_popen.return_value = _mock_popen(stdout="root")

    res = CommandRunner.run(["whoami"], require_root=True)

    assert res.success is True
    called_cmd = mock_popen.call_args[0][0]
    assert called_cmd[0] == "pkexec"
    assert called_cmd[1] == "whoami"


@patch("os.geteuid", return_value=1000)
@patch("shutil.which", return_value="/usr/bin/pkexec")
@patch("subprocess.Popen")
def test_command_runner_root_cancellation(mock_popen, mock_which, mock_geteuid):
    mock_popen.return_value = _mock_popen(
        returncode=126,
        stderr="Error executing command as another user: Request dismissed",
    )

    res = CommandRunner.run(["whoami"], require_root=True)

    assert res.success is False
    assert res.returncode == 126
    assert "cancel" in res.stderr.lower()