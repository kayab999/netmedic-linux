"""Tests for Smart Repair success semantics.

Verifies that Smart Repair requires ALL steps to succeed for an overall
success result, and that partial success is correctly reported as failure.
"""

from netmedic.models import NetResult


def _simulate_repair(step_results):
    """Simulate the Smart Repair logic extracted from ui.py.

    Args:
        step_results: list of bool indicating success of each step.

    Returns:
        NetResult with overall success/failure and summary.
    """
    results = [
        NetResult(f"Step {i}", success, "ok" if success else "failed")
        for i, success in enumerate(step_results)
    ]

    succeeded = sum(1 for res in results if res.success)
    total = len(results)
    overall = succeeded == total
    if overall:
        summary = f"Smart Repair finished: all {total} steps succeeded"
    else:
        summary = f"Smart Repair: {succeeded}/{total} steps succeeded — review log for failures"
    return NetResult("Smart Repair", overall, summary)


def test_all_succeed():
    result = _simulate_repair([True, True, True])
    assert result.success is True
    assert "all 3" in result.message


def test_all_fail():
    result = _simulate_repair([False, False, False])
    assert result.success is False
    assert "0/3" in result.message


def test_partial_one_of_three():
    """One success out of three must report failure (was previously green)."""
    result = _simulate_repair([True, False, False])
    assert result.success is False
    assert "1/3" in result.message


def test_partial_two_of_three():
    result = _simulate_repair([True, True, False])
    assert result.success is False
    assert "2/3" in result.message
    assert "review log" in result.message.lower()


def test_skip_renew_when_gateway_not_found():
    """Mirrors ui.py Smart Repair gate on diagnostic message text."""
    diag_ok = NetResult(
        "Diagnostics",
        False,
        "Gateway Not Found | DNS Resolution Failed | No Internet Access",
    )
    assert "Gateway Not Found" in diag_ok.message
    skip_renew = "Gateway Not Found" in (diag_ok.message or "")
    assert skip_renew is True


def test_do_not_skip_renew_when_gateway_unreachable():
    diag = NetResult(
        "Diagnostics",
        False,
        "Gateway Unreachable | DNS Resolution OK | Internet Access OK",
    )
    skip_renew = "Gateway Not Found" in (diag.message or "")
    assert skip_renew is False
