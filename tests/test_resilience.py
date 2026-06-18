import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NETMEDIC_DIR = REPO_ROOT / "netmedic"
PYTHON = REPO_ROOT / "venv" / "bin" / "python"


@pytest.fixture
def isolated_state(tmp_path):
    """Uses XDG_STATE_HOME so subprocesses don't touch the user's real state dir."""
    xdg_state = tmp_path / "xdg_state"
    xdg_state.mkdir()
    env = {
        **os.environ,
        "PYTHONPATH": f"{NETMEDIC_DIR}:{REPO_ROOT}",
        "XDG_STATE_HOME": str(xdg_state),
    }
    state_dir = xdg_state / "netmedic"
    return env, state_dir


def test_crash_resilience(isolated_state):
    env, state_dir = isolated_state

    process = subprocess.Popen(
        [str(PYTHON), "-m", "netmedic", "--headless"],
        cwd=str(NETMEDIC_DIR),
        env=env,
    )
    time.sleep(2)

    assert (state_dir / "ipc.pid").exists(), "PID file should be created on startup"

    process.kill()
    process.wait()

    process2 = subprocess.Popen(
        [str(PYTHON), "-m", "netmedic", "--headless"],
        cwd=str(NETMEDIC_DIR),
        env=env,
    )
    time.sleep(2)

    try:
        assert process2.poll() is None, "App should recover and start after a SIGKILL crash"
    finally:
        process2.terminate()
        process2.wait(timeout=5)