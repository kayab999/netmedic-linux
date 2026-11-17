"""F2: root-side read of the vendored VPN installer.

The helper must open the fixed root-owned path with ``O_NOFOLLOW``, reject
non-regular files, foreign owners, writable modes and oversized content,
verify the pin over the bytes it read, stage them in ``/run/netmedic`` and
execute only the staged copy.
"""

import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import netmedic.helper_main as hm

CONTENT = b"#!/bin/bash\necho staged\n"


def _install(tmp_path, monkeypatch, content: bytes = CONTENT) -> tuple[Path, str]:
    """Place a fake installer at the fixed-path mapping and pin its bytes."""
    path = tmp_path / "openvpn-install.sh"
    path.write_bytes(content)
    path.chmod(0o644)
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(hm, "PINNED_VPN_INSTALL_SHA256", digest)
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(path))
    return path, digest


# --------------------------------------------------------------------------
# _read_vpn_script: fixed path, secure open, pin check
# --------------------------------------------------------------------------


def test_read_vpn_script_returns_verified_bytes(tmp_path, monkeypatch) -> None:
    _, digest = _install(tmp_path, monkeypatch)
    assert hm._read_vpn_script("openvpn-install") == CONTENT
    assert digest == hashlib.sha256(CONTENT).hexdigest()


def test_read_vpn_script_rejects_unknown_id(monkeypatch) -> None:
    with pytest.raises(hm.StagingError, match="script_id"):
        hm._read_vpn_script("evil")


def test_read_vpn_script_refuses_symlink(tmp_path, monkeypatch) -> None:
    real = tmp_path / "real.sh"
    real.write_bytes(CONTENT)
    link = tmp_path / "openvpn-install.sh"
    link.symlink_to(real)
    monkeypatch.setattr(
        hm, "PINNED_VPN_INSTALL_SHA256", hashlib.sha256(CONTENT).hexdigest()
    )
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(link))
    with pytest.raises(hm.StagingError):
        hm._read_vpn_script("openvpn-install")


def test_read_vpn_script_refuses_non_regular_file(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "openvpn-install.sh"
    directory.mkdir()
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(directory))
    with pytest.raises(hm.StagingError, match="regular file"):
        hm._read_vpn_script("openvpn-install")


def test_read_vpn_script_refuses_foreign_owner(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    monkeypatch.setattr(hm.os, "geteuid", lambda: 4242)
    with pytest.raises(hm.StagingError, match="owned"):
        hm._read_vpn_script("openvpn-install")


def test_read_vpn_script_refuses_writable_file(tmp_path, monkeypatch) -> None:
    path, _ = _install(tmp_path, monkeypatch)
    path.chmod(0o666)
    with pytest.raises(hm.StagingError, match="writable"):
        hm._read_vpn_script("openvpn-install")


def test_read_vpn_script_refuses_empty_file(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch, b"")
    with pytest.raises(hm.StagingError, match="empty"):
        hm._read_vpn_script("openvpn-install")


def test_read_vpn_script_refuses_oversized_file(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch, b"x" * (hm.VPN_SCRIPT_MAX_BYTES + 1))
    with pytest.raises(hm.StagingError, match="too large"):
        hm._read_vpn_script("openvpn-install")


def test_read_vpn_script_refuses_pin_mismatch(tmp_path, monkeypatch) -> None:
    path, _ = _install(tmp_path, monkeypatch)
    path.write_bytes(b"#!/bin/bash\ntampered\n")
    with pytest.raises(hm.StagingError, match="integrity"):
        hm._read_vpn_script("openvpn-install")


# --------------------------------------------------------------------------
# _stage_verified_bytes: sealed staging in a root-owned directory
# --------------------------------------------------------------------------


def test_stage_verified_bytes_ok(tmp_path) -> None:
    digest = hashlib.sha256(CONTENT).hexdigest()
    stage = tmp_path / "stage"
    staged = hm._stage_verified_bytes(CONTENT, digest, str(stage))
    assert staged.startswith(str(stage) + "/")
    assert Path(staged).read_bytes() == CONTENT
    assert oct(os.stat(staged).st_mode & 0o777) == oct(0o700)
    assert oct(os.stat(stage).st_mode & 0o777) == oct(0o700)
    os.unlink(staged)


def test_stage_rejects_tampered_bytes(tmp_path) -> None:
    with pytest.raises(hm.StagingError, match="integrity"):
        hm._stage_verified_bytes(CONTENT, "0" * 64, str(tmp_path / "stage"))


def test_stage_refuses_symlink_and_file_dirs(tmp_path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    digest = hashlib.sha256(CONTENT).hexdigest()
    with pytest.raises(hm.StagingError):
        hm._stage_verified_bytes(CONTENT, digest, str(link))
    afile = tmp_path / "afile"
    afile.write_text("x")
    with pytest.raises(hm.StagingError):
        hm._stage_verified_bytes(CONTENT, digest, str(afile))


# --------------------------------------------------------------------------
# _execute_vpn_script: marker carries an id, never a caller path
# --------------------------------------------------------------------------


def test_exec_uses_staged_copy_not_source(tmp_path, monkeypatch) -> None:
    src, _ = _install(tmp_path, monkeypatch)
    stage = tmp_path / "stage"
    captured = {}

    def fake_run(argv, timeout):
        captured["argv"] = list(argv)
        # Deterministic swap simulation: rewrite SOURCE after the secure read.
        src.write_bytes(b"#!/bin/bash\necho PWNED\n")
        result = MagicMock()
        result.returncode = 0
        result.stdout = "done"
        result.stderr = ""
        return result

    monkeypatch.setattr(hm, "_run_argv", fake_run)
    res = hm._execute_vpn_script(
        ["__vpn_script__", "openvpn-install", "MENU_OPTION=1"],
        timeout=10,
        staging_dir=str(stage),
    )
    assert res["ok"] is True
    target = captured["argv"][-1]
    assert target != str(src)
    assert target.startswith(str(stage) + "/")
    assert captured["argv"][:3] == ["env", "-i", captured["argv"][2]]
    assert "/bin/bash" in captured["argv"]
    assert list(stage.glob("sealed-*.sh")) == []


def test_exec_rejects_pin_mismatch(tmp_path, monkeypatch) -> None:
    src = tmp_path / "openvpn-install.sh"
    src.write_bytes(b"#!/bin/bash\nnot-the-pin\n")
    src.chmod(0o644)
    monkeypatch.setitem(hm.VPN_SCRIPT_PATHS, "openvpn-install", str(src))
    # Do NOT patch the pin: these bytes are not the vendored installer.
    res = hm._execute_vpn_script(
        ["__vpn_script__", "openvpn-install"], timeout=10, staging_dir=str(tmp_path / "stageX")
    )
    assert res["ok"] is False
    assert "security abort" in res["message"].lower() or "integrity" in res["message"].lower()


def test_exec_real_harmless_script(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch, b"#!/bin/sh\necho hello-from-staged\n")
    res = hm._execute_vpn_script(
        ["__vpn_script__", "openvpn-install"], timeout=10, staging_dir=str(tmp_path / "stage2")
    )
    assert res["ok"] is True
    assert "hello-from-staged" in (res["details"] or "")


def test_exec_rejects_unknown_script_id(monkeypatch) -> None:
    res = hm._execute_vpn_script(["__vpn_script__", "evil"], timeout=10)
    assert res["ok"] is False
    assert "script_id" in res["message"]


def test_exec_rejects_malformed_marker() -> None:
    res = hm._execute_vpn_script(["__vpn_script__"], timeout=10)
    assert res["ok"] is False
    assert "malformed" in res["message"].lower()


@pytest.mark.parametrize(
    "pair",
    ["PATH=/tmp", "LD_PRELOAD=/tmp/x.so", "BASH_ENV=/tmp/x", "CLIENT=a\nb", "PASS=-secret"],
)
def test_exec_revalidates_env_pairs_at_root(tmp_path, monkeypatch, pair: str) -> None:
    """A plan-bypassing caller cannot inject env(1) flags or wrappers."""
    _install(tmp_path, monkeypatch)
    res = hm._execute_vpn_script(
        ["__vpn_script__", "openvpn-install", pair],
        timeout=10,
        staging_dir=str(tmp_path / "stage3"),
    )
    assert res["ok"] is False
    assert "env" in res["message"].lower()
