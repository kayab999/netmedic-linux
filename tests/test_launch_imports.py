import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_import():
    from netmedic import __version__

    assert __version__ == "1.1.0"


def test_main_window_import():
    from netmedic.ui import MainWindow

    assert MainWindow is not None


def test_netmedic_console_script():
    netmedic_bin = REPO_ROOT / "venv" / "bin" / "netmedic"
    if not netmedic_bin.is_file():
        pytest.skip("venv/bin/netmedic not installed")
    result = subprocess.run(
        [str(netmedic_bin), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0