"""Icon / ResultCode contract for repair logs.

The live Smart Repair sequence (pre-diag not counted, post-verify, 2/2 ratio)
is tested in tests/test_ui_elements_wiring.py against ui.MainWindow.

This file used to simulate a 2/3 ratio in isolation — that contract is dead
and must not return. EXECUTED must not render as ✅ (incident lines 2–3).
"""
from netmedic.models import NetResult, ResultCode


def test_executed_log_is_warning_not_check():
    entry = NetResult(
        "Flush DNS", True, "executed (resolvectl) — effect not yet verified",
        code=ResultCode.EXECUTED,
    ).to_log_entry()
    assert "⚠️" in entry
    assert "✅" not in entry


def test_ok_log_is_check():
    entry = NetResult("Diagnostics", True, "all probes ok", code=ResultCode.OK).to_log_entry()
    assert "✅" in entry


def test_partial_log_is_warning():
    entry = NetResult(
        "Diagnostics", False, "TCP blocked, ICMP ok", code=ResultCode.PARTIAL,
    ).to_log_entry()
    assert "⚠️" in entry
    assert "✅" not in entry


def test_failed_log_is_cross():
    entry = NetResult(
        "Smart Repair", False, "repairs 2/2 executed; network NOT recovered",
        code=ResultCode.FAILED,
    ).to_log_entry()
    assert "❌" in entry
    assert "2/3" not in entry


def test_skipped_healthy_is_skip_icon():
    entry = NetResult(
        "Smart Repair", False, "SKIPPED — network healthy, nothing to repair",
        code=ResultCode.SKIPPED,
    ).to_log_entry()
    assert "⏭️" in entry
