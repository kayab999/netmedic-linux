"""F1: pkexec must resolve to a fixed, validated root-owned binary (L1)."""

import os
import stat
from pathlib import Path

import pytest

import netmedic.system as system_mod
from netmedic.config import Config
from netmedic.system import CommandRunner


def _stat(mode: int, uid: int) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 0, uid, 0, 0, 0, 0, 0))


def test_pkexec_stat_accepts_root_owned_regular_executable() -> None:
    system_mod._check_pkexec_stat(_stat(stat.S_IFREG | 0o4755, 0), "/usr/bin/pkexec")


@pytest.mark.parametrize(
    "mode,uid",
    [
        (stat.S_IFREG | 0o755, 1000),  # not root-owned
        (stat.S_IFIFO | 0o755, 0),  # not a regular file
        (stat.S_IFLNK | 0o777, 0),  # not a regular file
        (stat.S_IFREG | 0o644, 0),  # not executable
    ],
)
def test_pkexec_stat_rejects_unsafe_binaries(mode: int, uid: int) -> None:
    with pytest.raises(PermissionError):
        system_mod._check_pkexec_stat(_stat(mode, uid), "/usr/bin/pkexec")


def test_validated_pkexec_rejects_missing_binary(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(system_mod, "PKEXEC_PATH", str(tmp_path / "pkexec"))
    with pytest.raises(FileNotFoundError):
        system_mod._validated_pkexec()


def test_helper_invocation_uses_fixed_pkexec_not_path(monkeypatch, tmp_path) -> None:
    """A hostile pkexec earlier in PATH must never be selected."""
    fake = tmp_path / "pkexec"
    fake.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.setattr(system_mod, "_validated_pkexec", lambda: "/usr/bin/pkexec")
    monkeypatch.setattr(
        Config, "get_helper_path", staticmethod(lambda: Path("/usr/libexec/netmedic/helper"))
    )

    argv = CommandRunner._helper_invocation("flush-dns", {}, timeout=5)

    assert argv[0] == "/usr/bin/pkexec"
    assert str(fake) not in argv
