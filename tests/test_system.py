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

    res = CommandRunner.run(["ip", "link", "show"], require_root=True)

    assert res.success is True
    called_cmd = mock_popen.call_args[0][0]
    assert called_cmd[0] == "pkexec"
    assert called_cmd[1] == "ip"


@patch("os.geteuid", return_value=1000)
@patch("shutil.which", return_value="/usr/bin/pkexec")
@patch("subprocess.Popen")
def test_command_runner_root_cancellation(mock_popen, mock_which, mock_geteuid):
    mock_popen.return_value = _mock_popen(
        returncode=126,
        stderr="Error executing command as another user: Request dismissed",
    )

    res = CommandRunner.run(["ip", "link", "show"], require_root=True)

    assert res.success is False
    assert res.returncode == 126
    assert "cancel" in res.stderr.lower()


def test_hanging_command_bounded_by_timeout():
    """C-9: a hung child (no polkit agent, stuck pkexec) must surface as a
    structured timeout, never a hang. Real subprocess, wall-clock asserted."""
    import time

    start = time.monotonic()
    res = CommandRunner.run(["sleep", "30"], timeout=1)
    elapsed = time.monotonic() - start
    assert res.success is False
    assert res.returncode == -1
    assert "Timeout" in res.stderr
    assert elapsed < 10


def test_run_elevated_timeout_never_escapes(monkeypatch):
    """C-9: even if run() itself raised TimeoutExpired, run_elevated must
    return a CommandResult, not propagate a traceback (headless safety)."""

    def raising_run(command, require_root=False, timeout=None, _legacy_ok=False):
        raise subprocess.TimeoutExpired(command, timeout or 1)

    monkeypatch.setattr(CommandRunner, "run", staticmethod(raising_run))
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    res = CommandRunner.run_elevated("flush-dns", {})
    assert res.success is False
    assert "Timeout" in res.stderr


def test_run_elevated_legacy_timeout_never_escapes(monkeypatch):
    def raising_run(command, require_root=False, timeout=None, _legacy_ok=False):
        raise subprocess.TimeoutExpired(command, timeout or 1)

    monkeypatch.setattr(CommandRunner, "run", staticmethod(raising_run))
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "0")
    monkeypatch.setenv("NETMEDIC_ALLOW_LEGACY_ELEVATION", "1")
    res = CommandRunner.run_elevated("flush-dns", {})
    assert res.success is False
    assert "Timeout" in res.stderr


@patch("os.geteuid", return_value=1000)
@patch("shutil.which", return_value=None)
def test_pkexec_missing_fails_fast(mock_which, mock_geteuid):
    res = CommandRunner.run(["ip", "link", "show"], require_root=True, _legacy_ok=True)
    assert res.success is False
    assert res.returncode == 127
    assert "pkexec" in res.stderr.lower()