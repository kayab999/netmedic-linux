"""Tests for netmedic --status and the LUCP readiness separation."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from netmedic import status
from netmedic.action_catalog import POLKIT_ACTION_IDS
from netmedic.capabilities import (
    AVAILABLE,
    NOT_ATTEMPTED,
    REASON_HELPER_NOT_INSTALLED,
    REASON_POLKIT_PROBE_UNAVAILABLE,
    REASON_TOOL_NOT_FOUND,
    UNKNOWN,
    UNAVAILABLE,
)
from netmedic.config import Config
from netmedic.status import collect_status, format_status_text, print_status


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No optional tools, no helper, no Polkit, fresh 0700 state dir."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(status.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        status, "_pkaction_probe", lambda: (None, "pkaction not found")
    )
    monkeypatch.setattr(Config, "SYSTEM_HELPER_PATH", tmp_path / "helper")
    monkeypatch.setattr(Config, "SYSTEM_HELPER_LIB", tmp_path / "lib")
    monkeypatch.setattr(Config, "use_privileged_helper", staticmethod(lambda: False))
    return tmp_path


def _install_fake_helper(root: Path) -> None:
    (root / "helper").write_text("#!/bin/sh\n", encoding="utf-8")
    lib = root / "lib" / "netmedic"
    lib.mkdir(parents=True)
    (lib / "helper_main.py").write_text("", encoding="utf-8")


def test_collect_status_structure() -> None:
    report = collect_status()
    assert report["version"]
    assert report["schema_version"]
    assert "scope" in report
    assert "capabilities" in report
    assert "core_ready" in report
    assert "privileged_ready" in report
    assert "production_ready" in report
    names = {c["name"] for c in report["checks"]}
    assert "python_runtime" in names
    assert "state_dir" in names
    assert "privileged_helper" in names
    assert "pkexec" in names
    assert "polkit_actions" in names
    assert "ipc_daemon" in names


def test_status_is_independent_of_network_availability(
    bare: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing Internet path must not turn the install into a core failure."""

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("status must not execute connectivity probes")

    monkeypatch.setattr("netmedic.probes.check_internet_access", boom)
    monkeypatch.setattr("netmedic.probes.check_dns_resolution", boom)

    report = collect_status()

    assert report["core_ready"] is True
    assert report["overall_ok"] is True
    assert all(c["outcome"] == NOT_ATTEMPTED for c in report["capabilities"])


def test_format_status_text() -> None:
    report = collect_status()
    text = format_status_text(report)
    assert "NetMedic" in text
    assert "core_ready:" in text
    assert "privileged_ready:" in text
    assert "production_ready:" in text
    assert "capabilities:" in text
    assert "checks:" in text


def test_bare_system_keeps_core_ready(bare: Path) -> None:
    report = collect_status()
    assert report["core_ready"] is True
    assert report["overall_ok"] is True
    assert report["privileged_ready"] is False
    # Deprecated alias still points at core health.
    assert report["production_ready"] is True

    caps = {c["id"]: c for c in report["capabilities"]}
    assert caps["networkmanager"]["availability"] == UNAVAILABLE
    assert caps["networkmanager"]["reason_code"] == REASON_TOOL_NOT_FOUND
    assert caps["privileged_flush_dns"]["availability"] == UNAVAILABLE
    assert caps["privileged_flush_dns"]["reason_code"] == REASON_HELPER_NOT_INSTALLED
    assert any("core diagnostics remain available" in h.lower() for h in report["hints"])


def test_print_status_exit_codes_follow_core_and_privileged(
    bare: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert print_status(as_json=True) == 0
    capsys.readouterr()
    assert print_status(as_json=True, require_privileged=True) == 1


def test_polkit_probe_inconclusive_is_unknown(
    bare: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_helper(bare)
    monkeypatch.setattr(Config, "SYSTEM_HELPER_PATH", bare / "helper")
    monkeypatch.setattr(Config, "SYSTEM_HELPER_LIB", bare / "lib")
    monkeypatch.setattr(Config, "use_privileged_helper", staticmethod(lambda: True))
    monkeypatch.setattr(
        status.shutil,
        "which",
        lambda name: "/usr/bin/pkexec" if name == "pkexec" else None,
    )
    monkeypatch.setattr(status, "_pkaction_probe", lambda: (None, "timeout"))

    report = collect_status()
    assert report["core_ready"] is True
    assert report["privileged_ready"] is False
    caps = {c["id"]: c for c in report["capabilities"]}
    assert caps["privileged_flush_dns"]["availability"] == UNKNOWN
    assert (
        caps["privileged_flush_dns"]["reason_code"] == REASON_POLKIT_PROBE_UNAVAILABLE
    )
    polkit = next(c for c in report["checks"] if c["name"] == "polkit_actions")
    assert "inconclusive" in polkit["detail"]


def test_privileged_ready_when_every_action_is_registered(
    bare: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_helper(bare)
    monkeypatch.setattr(Config, "SYSTEM_HELPER_PATH", bare / "helper")
    monkeypatch.setattr(Config, "SYSTEM_HELPER_LIB", bare / "lib")
    monkeypatch.setattr(Config, "use_privileged_helper", staticmethod(lambda: True))
    monkeypatch.setattr(
        status.shutil,
        "which",
        lambda name: "/usr/bin/pkexec" if name == "pkexec" else None,
    )
    monkeypatch.setattr(
        status,
        "_pkaction_probe",
        lambda: (list(POLKIT_ACTION_IDS.values()), "/usr/bin/pkaction"),
    )

    report = collect_status()
    assert report["core_ready"] is True
    assert report["privileged_ready"] is True
    privileged = [c for c in report["capabilities"] if c["level"] == "L2"]
    assert len(privileged) == 12
    assert all(c["availability"] == AVAILABLE for c in privileged)


def test_pkaction_probe_ignores_polkit_0_105_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = "\n".join(POLKIT_ACTION_IDS.values()) + "\n"
    monkeypatch.setattr(
        status.shutil, "which", lambda _name: "/usr/bin/pkaction"
    )
    monkeypatch.setattr(
        status.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 1, stdout, ""),
    )

    ids, detail = status._pkaction_probe()

    assert ids == list(POLKIT_ACTION_IDS.values())
    assert detail == "/usr/bin/pkaction"


def test_pkaction_probe_failure_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        status.shutil, "which", lambda _name: "/usr/bin/pkaction"
    )

    def boom(argv: Any, **_kwargs: Any) -> Any:
        raise OSError("no bus")

    monkeypatch.setattr(status.subprocess, "run", boom)

    ids, detail = status._pkaction_probe()

    assert ids is None
    assert "no bus" in detail


def test_status_json_is_stable_and_sensitive_free(bare: Path) -> None:
    first = json.dumps(collect_status(), sort_keys=True)
    second = json.dumps(collect_status(), sort_keys=True)
    assert first == second
    assert "session_token" not in first
    assert '"artifact"' not in first


def test_production_ready_is_a_deprecated_alias(bare: Path) -> None:
    report = collect_status()
    assert report["production_ready"] == report["core_ready"]
    assert any("deprecated" in item for item in report["deprecations"])


def test_require_privileged_flag_is_parsed() -> None:
    from netmedic.runtime import parse_args

    args = parse_args(["--status", "--require-privileged"])
    assert args.require_privileged is True
