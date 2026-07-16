import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NETMEDIC_BIN = REPO_ROOT / "venv" / "bin" / "netmedic"
PYTHON = shutil.which("python3") or sys.executable


def _wait_for(path: Path, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def isolated_state(tmp_path):
    """Uses XDG_STATE_HOME so subprocesses don't touch the user's real state dir."""
    xdg_state = tmp_path / "xdg_state"
    xdg_state.mkdir()
    env = {
        **os.environ,
        "XDG_STATE_HOME": str(xdg_state),
    }
    state_dir = xdg_state / "netmedic"
    return env, state_dir


def _headless_cmd():
    if NETMEDIC_BIN.is_file():
        return [str(NETMEDIC_BIN), "--headless"]
    return [PYTHON, "-m", "netmedic", "--headless"]


def test_crash_resilience(isolated_state):
    env, state_dir = isolated_state
    cmd = _headless_cmd()

    process = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env)
    assert _wait_for(state_dir / "ipc.pid"), "PID file should be created on startup"

    process.kill()
    process.wait()

    process2 = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env)
    try:
        assert _wait_for(state_dir / "ipc.pid"), "App should recover after SIGKILL"
        assert process2.poll() is None, "App should stay running after recovery"
    finally:
        process2.terminate()
        process2.wait(timeout=5)