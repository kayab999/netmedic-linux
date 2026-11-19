"""Regression: a malformed helper version probe must block elevation."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from netmedic import system
from netmedic.helper_verbs import HELPER_VERSION
from netmedic.system import CommandRunner

PROBE_ERR = "install-polkit-policy"


@pytest.fixture
def helper_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("/usr/libexec/netmedic/helper")),
    )


def _probe(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rc: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(argv), rc, stdout, stderr)

    monkeypatch.setattr(system.subprocess, "run", fake_run)


def test_probe_accepts_exact_version(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, stdout=json.dumps({"ok": True, "version": HELPER_VERSION}))
    assert CommandRunner._check_helper_version() is None


def test_probe_blocks_version_mismatch(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, stdout=json.dumps({"ok": True, "version": "0.0.0-stale"}))
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "version mismatch" in error
    assert PROBE_ERR in error


def test_probe_blocks_nonzero_exit(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, rc=2, stderr="unknown option --version")
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "rc=2" in error
    assert PROBE_ERR in error


def test_probe_blocks_invalid_json(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, stdout="not json")
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "invalid JSON" in error
    assert PROBE_ERR in error


def test_probe_blocks_non_object_json(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, stdout="[]")
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "invalid payload" in error


def test_probe_blocks_ok_false(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, stdout=json.dumps({"ok": False, "version": HELPER_VERSION}))
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "ok=true" in error


@pytest.mark.parametrize("payload", [{}, {"ok": True}, {"ok": True, "version": ""}])
def test_probe_blocks_missing_version(
    helper_env: None, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    _probe(monkeypatch, stdout=json.dumps(payload))
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "version" in error


def test_probe_blocks_empty_output(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, stdout="")
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "no output" in error


def test_probe_blocks_os_error(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raising_run(argv: list[str], **kwargs: Any) -> None:
        raise OSError("no such helper")

    monkeypatch.setattr(system.subprocess, "run", raising_run)
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "probe failed" in error
    assert PROBE_ERR in error


def test_probe_blocks_timeout(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raising_run(argv: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(argv, 5)

    monkeypatch.setattr(system.subprocess, "run", raising_run)
    error = CommandRunner._check_helper_version()
    assert error is not None
    assert "timed out" in error
    assert PROBE_ERR in error


def test_dev_module_path_keeps_explicit_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("python3|-m|netmedic.helper_main")),
    )
    assert CommandRunner._check_helper_version() is None


def test_malformed_probe_blocks_elevation(
    helper_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _probe(monkeypatch, rc=0, stdout=json.dumps({"ok": True}))
    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")

    def must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("elevation must not start after a bad version probe")

    monkeypatch.setattr(CommandRunner, "run", staticmethod(must_not_run))
    result = CommandRunner.run_elevated("flush-dns", {})
    assert result.success is False
    assert result.returncode == 127
    assert "version" in result.stderr
    assert PROBE_ERR in result.stderr
