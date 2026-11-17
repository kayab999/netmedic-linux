"""F1: the root journal record is attributable and injection-proof (L3)."""

import sys

import pytest

import netmedic.helper_main as hm


class _CapturingSyslog:
    LOG_PID = 0
    LOG_AUTH = 0
    LOG_INFO = 0
    LOG_WARNING = 0

    def __init__(self) -> None:
        self.lines: list[str] = []

    def openlog(self, *args: object, **kwargs: object) -> None:
        pass

    def closelog(self) -> None:
        pass

    def syslog(self, level: int, message: str) -> None:
        self.lines.append(message)


@pytest.fixture
def captured_journal(monkeypatch) -> _CapturingSyslog:
    fake = _CapturingSyslog()
    monkeypatch.setitem(sys.modules, "syslog", fake)
    return fake


def test_journal_records_validated_pkexec_uid(captured_journal, monkeypatch) -> None:
    monkeypatch.setenv("PKEXEC_UID", "1000")
    hm._journal_result("flush-dns", True, "ok")
    assert "pkexec_uid=1000" in captured_journal.lines[-1]


@pytest.mark.parametrize("value", ["", "abc", "-1", "1.5", "1000x"])
def test_journal_reports_unknown_uid(captured_journal, monkeypatch, value: str) -> None:
    monkeypatch.setenv("PKEXEC_UID", value)
    hm._journal_result("flush-dns", False, "boom")
    assert "pkexec_uid=unknown" in captured_journal.lines[-1]


def test_journal_reports_unknown_uid_when_unset(captured_journal, monkeypatch) -> None:
    monkeypatch.delenv("PKEXEC_UID", raising=False)
    hm._journal_result("flush-dns", True, "ok")
    assert "pkexec_uid=unknown" in captured_journal.lines[-1]


def test_journal_flattens_log_injection(captured_journal, monkeypatch) -> None:
    """A newline in a failure message must not forge a second syslog record."""
    monkeypatch.setenv("PKEXEC_UID", "1000")
    hm._journal_result("flush-dns", False, "boom\nverb=evil ok=1\r\x00\x1b[31m")
    line = captured_journal.lines[-1]

    assert "\n" not in line and "\r" not in line
    assert "\x00" not in line and "\x1b" not in line
    assert line.startswith("verb=flush-dns ok=0 pkexec_uid=1000 ")


def test_journal_truncates_long_messages(captured_journal, monkeypatch) -> None:
    monkeypatch.setenv("PKEXEC_UID", "1000")
    hm._journal_result("flush-dns", True, "A" * 5000)
    line = captured_journal.lines[-1]
    assert len(line) <= len("verb=flush-dns ok=1 pkexec_uid=1000 ") + 300


def test_journal_never_serializes_verb_args(captured_journal, monkeypatch) -> None:
    """Secrets passed as verb args must not reach the root journal."""
    from netmedic.helper_verbs import VerbPlan

    monkeypatch.setenv("PKEXEC_UID", "1000")
    script = "/tmp/x.sh"  # noqa: S108 (fixture path; never opened: pin mismatch aborts first)
    plan = VerbPlan("vpn-run-script", [["__vpn_script__", script, "00" * 32, "PASS=hunter2"]])
    hm.execute_plan(plan, timeout=5)
    assert "hunter2" not in captured_journal.lines[-1]
