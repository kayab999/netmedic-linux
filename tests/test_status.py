"""Tests for netmedic --status health report."""

from netmedic.status import collect_status, format_status_text, print_status


def test_collect_status_structure():
    report = collect_status()
    assert "version" in report
    assert "checks" in report
    assert "production_ready" in report
    names = {c["name"] for c in report["checks"]}
    assert "privileged_helper" in names
    assert "pkexec" in names
    assert "polkit_actions" in names
    assert "ipc_daemon" in names


def test_format_status_text():
    report = collect_status()
    text = format_status_text(report)
    assert "NetMedic" in text
    assert "checks:" in text


def test_print_status_exit_code():
    # Exit 0 only when production_ready; still should not raise.
    code = print_status(as_json=True)
    assert code in (0, 1)
