"""Guardian: VM evidence tooling must target the shipped release and stay honest."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = ROOT / "scripts" / "runbook_vm_evidence.py"


def test_obsolete_v1_6_verifier_removed() -> None:
    assert not (ROOT / "scripts" / "vm_verify_v1.6.1.sh").exists()


def test_runbook_does_not_return_mocked_results() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for marker in ("MagicMock", "Row 1 PASS", "Row 2 PASS"):
        assert marker not in text, f"runbook still fakes evidence: {marker}"


def test_runbook_checks_current_release_inputs() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for marker in (
        "HELPER_VERSION",
        "PINNED_VPN_INSTALL_SHA256",
        "pkaction",
        "restart-adapter",
        "change-dns",
        "VM_CHECKLIST",
    ):
        assert marker in text, f"runbook does not cover {marker}"


def test_runbook_has_no_unexplained_noqa() -> None:
    for number, line in enumerate(RUNBOOK.read_text(encoding="utf-8").splitlines(), 1):
        if "noqa" not in line:
            continue
        assert "# noqa: E402" not in line or "(" in line, (
            f"line {number}: E402 suppression needs an inline reason"
        )


@pytest.fixture
def runbook() -> Any:
    spec = importlib.util.spec_from_file_location("runbook_vm_evidence_under_test", RUNBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FAILURES.clear()
    module.WARNINGS.clear()
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_fails_on_version_mismatch(runbook: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(runbook, "_read_repo_version", lambda: "1.8.0")
    monkeypatch.setattr(runbook, "_read_pyproject_version", lambda: "1.9.0")
    monkeypatch.setattr(runbook, "HELPER_VERSION", "1.9.0")

    runbook._check_versions()

    out = capsys.readouterr().out
    assert "FAIL: version mismatch: app=1.8.0 package=1.9.0 helper=1.9.0" in out
    assert runbook.FAILURES


def test_fails_on_installed_vpn_hash_mismatch(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_script = _write(tmp_path / "repo" / "openvpn-install.sh", "vendored\n")
    installed_script = _write(tmp_path / "installed" / "openvpn-install.sh", "tampered\n")
    monkeypatch.setattr(runbook, "REPO_VPN_SCRIPT", repo_script)
    monkeypatch.setattr(runbook, "VPN_SCRIPT", installed_script)
    monkeypatch.setattr(runbook, "PINNED_VPN_INSTALL_SHA256", runbook._sha256(repo_script))

    runbook._check_vpn_installer()

    assert any("installed VPN installer hash" in item for item in runbook.FAILURES)


def test_fails_when_run_dir_is_not_0700(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    staged = tmp_path / "netmedic"
    staged.mkdir(mode=0o755)
    staged.chmod(0o755)
    monkeypatch.setattr(runbook, "RUN_DIR", staged)

    runbook._check_run_dir()

    assert any("0700" in item for item in runbook.FAILURES)


def _make_helper_package(tmp_path: Path, *, installed_hash: str | None = None) -> tuple[Path, Path]:
    repo_pkg = tmp_path / "repo" / "netmedic"
    installed_pkg = tmp_path / "installed" / "netmedic"
    contents = {
        "helper_verbs.py": "verbs\n",
        "helper_main.py": "main\n",
        "validators.py": "validators\n",
        "action_catalog.py": "catalog\n",
    }
    for name, text in contents.items():
        _write(repo_pkg / name, text)
        _write(installed_pkg / name, text)
    if installed_hash is not None:
        _write(installed_pkg / "helper_verbs.py", installed_hash)
    _write(installed_pkg / "__init__.py", '__version__ = "1.9.0"\n')
    return repo_pkg, installed_pkg


def test_fails_when_installed_module_differs_from_repo(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_pkg, installed_pkg = _make_helper_package(tmp_path, installed_hash="poisoned\n")
    monkeypatch.setattr(runbook, "REPO_HELPER_PKG", repo_pkg)
    monkeypatch.setattr(runbook, "INSTALLED_HELPER_PKG", installed_pkg)

    runbook._check_helper_modules()

    assert any("helper_verbs.py" in item and "hash" in item for item in runbook.FAILURES)


def test_fails_on_unexpected_python_file_in_helper_dir(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_pkg, installed_pkg = _make_helper_package(tmp_path)
    _write(installed_pkg / "rogue.py", "raise SystemExit\n")
    monkeypatch.setattr(runbook, "REPO_HELPER_PKG", repo_pkg)
    monkeypatch.setattr(runbook, "INSTALLED_HELPER_PKG", installed_pkg)

    runbook._check_helper_modules()

    assert any("rogue.py" in item and "unexpected" in item for item in runbook.FAILURES)


def test_fails_when_helper_is_group_or_world_writable(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    helper = _write(tmp_path / "helper", "#!/bin/sh\n")
    helper.chmod(0o666)
    monkeypatch.setattr(runbook, "HELPER", helper)

    runbook._check_regular_root(helper, "helper")

    assert any("group/world writable" in item for item in runbook.FAILURES)


def test_policy_hash_and_actions_are_checked(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_policy = _write(tmp_path / "assets" / "policy", "<policyconfig/>\n")
    installed_policy = _write(
        tmp_path / "installed" / "policy", "<!-- tampered --><policyconfig/>\n"
    )
    monkeypatch.setattr(runbook, "REPO_POLICY", repo_policy)
    monkeypatch.setattr(runbook, "POLICY", installed_policy)

    runbook._check_policy_hash()

    assert any("policy hash" in item for item in runbook.FAILURES)


def test_pkaction_listing_ignores_polkit_0_105_exit_code(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    stdout = "\n".join(runbook.POLKIT_ACTION_IDS.values()) + "\n"
    monkeypatch.setattr(
        runbook,
        "_run",
        lambda argv: subprocess.CompletedProcess(argv, 1, stdout, ""),
    )

    runbook._check_pkaction_listing()

    out = capsys.readouterr().out
    assert "PASS: pkaction lists all" in out
    assert not runbook.FAILURES


def test_pkaction_listing_fails_when_actions_are_missing(
    runbook: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr(
        runbook,
        "_run",
        lambda argv: subprocess.CompletedProcess(argv, 127, "", "pkaction: not found"),
    )

    runbook._check_pkaction_listing()

    out = capsys.readouterr().out
    assert "FAIL: pkaction missing" in out
    assert runbook.FAILURES


def _f2_block() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("F2 tamper")
    end = text.index("F5 re-prompt", start)
    return text[start:end]


def test_f2_block_requires_integrity_exit_code_and_message() -> None:
    block = _f2_block()

    assert "set -euo pipefail" in block
    assert "[ \"$RC\" -eq 3 ]" in block
    assert "OUT=$(pkexec" in block
    assert "RC=$?" in block
    assert '"ok":false' in block
    assert "Security abort: Script integrity failure." in block

    pass_at = block.index("PASS: helper rejected")
    assert block.index('"ok":false') < pass_at
    assert block.index("Security abort") < pass_at

    assert "INCONCLUSIVE/FAIL: rc=$RC" in block
    for code, label in (
        ("126", "cancelado"),
        ("127", "helper ausente"),
        ("2", "args"),
        ("1", "fallo operativo"),
    ):
        assert code in block
        assert label in block

    assert "VM snapshot" in block
    assert "cp -p" in block
    assert "sha256sum" in block
    assert "dpkg -l openvpn" in block
    assert "DPKG_BEFORE" in block
    assert "DPKG_AFTER" in block
    assert "openvpn package state unchanged" in block
    assert "trap " in block
