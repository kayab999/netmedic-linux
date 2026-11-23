"""M7: installer/packaging regression guards (static, repo style)."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_installer_installs_system_helper():
    """install.sh must call install-polkit-policy.sh (was policy-XML-only → 127)."""
    text = _read("install.sh")
    assert "./scripts/install-polkit-policy.sh" in text
    # Failure must be loud, not a silent "Installation complete".
    assert "system helper install failed" in text


def test_installer_pins_dev_tools():
    """Dev tools in the venv must be pinned (were unpinned latest)."""
    text = _read("install.sh")
    lock = _read("requirements-dev.lock")
    for pin in ("pytest==9.1.0", "pytest-cov==7.1.0", "ruff==0.15.12", "hypothesis==6.168.1"):
        assert pin in lock, f"lock missing {pin}"
        assert f'"{pin}"' in text or pin in text, f"installer must pin {pin}"
    assert "pip install --upgrade pip wheel setuptools pytest " not in text


def test_installer_yes_is_noninteractive():
    """--yes must suppress prompts (was a no-op for INSTALL_AI)."""
    text = _read("install.sh")
    assert "NONINTERACTIVE=1" in text
    assert 'NONINTERACTIVE" -eq 0' in text or "NONINTERACTIVE -eq 0" in text


def test_installer_fedora_polkit_name():
    """Fedora package is 'polkit' — 'policykit' does not exist there."""
    text = _read("install.sh")
    assert "iputils policykit\"" not in text
    assert "gtk3 NetworkManager polkit" in text


def test_no_removed_policykit_1_package():
    """policykit-1 has no candidate on Ubuntu 24.04+; use polkitd + pkexec."""
    for rel in (
        "install.sh",
        "packaging/debian/control",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ):
        # Comments may explain the rename; only executable lines matter.
        code = "\n".join(
            line for line in _read(rel).splitlines() if not line.lstrip().startswith("#")
        )
        assert "policykit-1" not in code, (
            f"{rel}: policykit-1 was split into polkitd/pkexec on Ubuntu 24.04"
        )
    installer = _read("install.sh")
    assert " polkitd " in installer and " pkexec" in installer


def test_installer_fails_on_unsupported_distro():
    """Unknown distros must fail loudly, not continue via install_cmd=true."""
    text = _read("install.sh")
    assert 'install_cmd="true"' not in text
    assert "Unsupported distro" in text


def test_launcher_exec_quoted():
    """Repo checkouts with spaces in the path need a quoted Exec."""
    text = _read("install.sh")
    assert '@EXEC@|\\"' in text or '@EXEC@|"' in text


def test_uninstall_covers_install_artifacts():
    """Every install.sh artifact class must have an uninstall.sh removal."""
    uninstall = _read("scripts/uninstall.sh")
    for artifact in (
        "netmedic-headless.service",
        "netmedic.desktop",
        "apps/netmedic.png",
        "$REPO_ROOT/venv",
        "com.kayab.netmedic.policy",
        "/usr/libexec/netmedic/helper",
        "/usr/lib/netmedic",
    ):
        assert artifact in uninstall, f"uninstall missing {artifact}"


def test_python_ceiling_allows_313():
    """requires-python must admit 3.13 (venv here runs 3.13; M7 load-bearing)."""
    text = _read("netmedic/pyproject.toml")
    m = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
    assert m, "requires-python missing"
    spec = m.group(1)
    assert "<3.14" in spec or ">=3.13" in spec or "<4" in spec, spec
    assert "<3.13" not in spec


def test_pillow_not_runtime_dep():
    """Pillow is used only by scripts/generate_icon.py (dev-time asset)."""
    text = _read("netmedic/pyproject.toml")
    deps = text.split("dependencies = [", 1)[1].split("]", 1)[0].lower()
    assert "pillow" not in deps
    # And no runtime module imports it.
    for path in (REPO / "netmedic" / "netmedic").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        assert "from PIL" not in src and "import PIL" not in src, path


def test_installer_supports_headless_profile():
    """install.sh must offer an explicit headless profile."""
    text = _read("install.sh")
    assert "--headless" in text
    assert "--profile=" in text
    assert 'PROFILE="headless"' in text
    assert 'install_cmd=""' in text
    assert "Skipping automatic system package installation." in text


def test_check_deps_supports_profiles():
    """check-deps.sh must distinguish desktop and headless requirements."""
    text = _read("scripts/check-deps.sh")
    assert "--profile=" in text
    assert "headless" in text
    assert "GUI (GTK3/PyGObject): not required for headless profile" in text
    """Release, package and helper versions must be one value (1.9.0)."""
    app_version = re.search(
        r'^__version__ = "([^"]+)"', _read("netmedic/netmedic/__init__.py"), re.M
    ).group(1)
    package_version = re.search(
        r'^version = "([^"]+)"', _read("netmedic/pyproject.toml"), re.M
    ).group(1)
    helper_version = re.search(
        r'^HELPER_VERSION = "([^"]+)"',
        _read("netmedic/netmedic/helper_verbs.py"),
        re.M,
    ).group(1)

    assert app_version == package_version == "1.10.0"
    assert helper_version == "1.9.0"
