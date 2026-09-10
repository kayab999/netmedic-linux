import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_import():
    from netmedic import __version__

    assert __version__ == "1.6.0"


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


def test_desktop_template_exec_is_console_script():
    template = (REPO_ROOT / "assets" / "netmedic.desktop.in").read_text(encoding="utf-8")
    installer = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "Exec=@EXEC@" in template
    assert "Terminal=false" in template
    assert "${REPO_ROOT}/venv/bin/netmedic" in installer
    assert "editable_mode=strict" in installer


def test_strict_snapshot_contains_all_source_modules():
    """editable_mode=strict only exposes files present at pip install time."""
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    if not venv_python.is_file():
        pytest.skip("venv/bin/python not installed")
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import netmedic, pathlib, sys\n"
            f"source = pathlib.Path({str(REPO_ROOT / 'netmedic' / 'netmedic')!r})\n"
            "pkg = pathlib.Path(netmedic.__file__).resolve().parent\n"
            "missing = []\n"
            "for path in source.rglob('*.py'):\n"
            "    if '__pycache__' in path.parts:\n"
            "        continue\n"
            "    rel = path.relative_to(source)\n"
            "    if not (pkg / rel).exists():\n"
            "        missing.append(str(rel))\n"
            "if missing:\n"
            "    print('\\n'.join(sorted(missing)), file=sys.stderr)\n"
            "    sys.exit(1)\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_installed_interpreter_imports_dock_stack():
    """venv/bin/netmedic (desktop Exec) must import GUI without PYTHONPATH."""
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    if not venv_python.is_file():
        pytest.skip("venv/bin/python not installed")
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import netmedic.constants, netmedic.probes, netmedic.canary_shim_prod, netmedic.gui",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_show_error_dialog_importable_when_ui_missing():
    """Startup dialog must load even if MainWindow/ui import fails (dock path)."""
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    if not venv_python.is_file():
        pytest.skip("venv/bin/python not installed")
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import sys\n"
            "sys.modules['netmedic.ui'] = None\n"
            "import netmedic.gui\n"
            "assert callable(netmedic.gui.show_error_dialog)\n"
            "assert 'MainWindow' not in dir(netmedic.gui)\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout