"""M3: audit append hardening + denial rate-limit + helper journal."""

import json
import os

import pytest

from netmedic import audit_log
from netmedic.audit_log import _reset_denial_state, get_audit_log_path, record, record_intent


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    _reset_denial_state()


def test_symlinked_log_refused(tmp_path, monkeypatch):
    """O_NOFOLLOW: a swapped-in symlink is refused, not followed (fail-closed)."""
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "evil.log"
    (tmp_path / "audit.log").symlink_to(target)
    with pytest.raises(OSError):
        record_intent(action="flush_dns", peer_uid=1, peer_pid=1, params={})
    assert not target.exists()


def test_mode_0600_at_creation_despite_umask(tmp_path, monkeypatch):
    """0600 comes from O_CREAT mode, not a later chmod (umask 022 proof)."""
    _isolate(tmp_path, monkeypatch)
    old = os.umask(0o022)
    try:
        record_intent(action="flush_dns", peer_uid=1, peer_pid=1, params={})
    finally:
        os.umask(old)
    assert get_audit_log_path().stat().st_mode & 0o777 == 0o600


def test_fsync_per_record(tmp_path, monkeypatch):
    """Every record is fsynced before close (no silent loss on crash)."""
    _isolate(tmp_path, monkeypatch)
    calls = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd)))
    record_intent(action="flush_dns", peer_uid=1, peer_pid=1, params={})
    assert len(calls) == 1


def test_denial_burst_writes_once(tmp_path, monkeypatch):
    """Rapid denials: first writes, rest suppressed (rotation-spam guard)."""
    _isolate(tmp_path, monkeypatch)
    kwargs = dict(action="flush_dns", peer_uid=1, peer_pid=1, params={},
                  result={"status": "error"}, duration_ms=1.0, outcome="denied")
    record(**kwargs)
    record(**kwargs)
    record(**kwargs)
    lines = get_audit_log_path().read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["outcome"] == "denied"


def test_denial_suppressed_count_reported(tmp_path, monkeypatch):
    """After the window, the next denial reports how many were suppressed."""
    _isolate(tmp_path, monkeypatch)
    now = [1000.0]
    monkeypatch.setattr(audit_log.time, "monotonic", lambda: now[0])
    kwargs = dict(action="flush_dns", peer_uid=1, peer_pid=1, params={},
                  result={"status": "error"}, duration_ms=1.0, outcome="denied")
    record(**kwargs)
    record(**kwargs)  # suppressed
    now[0] += 30.0  # window (5s) passed
    record(**kwargs)
    lines = get_audit_log_path().read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1]).get("suppressed_denials") == 1


def test_intent_never_rate_limited(tmp_path, monkeypatch):
    """Fail-closed gate: intents always write, even in a burst."""
    _isolate(tmp_path, monkeypatch)
    record_intent(action="flush_dns", peer_uid=1, peer_pid=1, params={})
    record_intent(action="flush_dns", peer_uid=1, peer_pid=1, params={})
    assert len(get_audit_log_path().read_text().strip().splitlines()) == 2


def test_non_denial_outcomes_unaffected(tmp_path, monkeypatch):
    """ok/error completions still write every time (only denied limits)."""
    _isolate(tmp_path, monkeypatch)
    for _ in range(3):
        record(action="flush_dns", peer_uid=1, peer_pid=1, params={},
               result={"status": "ok"}, duration_ms=1.0, outcome="ok")
    assert len(get_audit_log_path().read_text().strip().splitlines()) == 3


def test_helper_journals_every_verb_outcome(monkeypatch):
    """Root side: exactly one journal record per execute_plan call."""
    import netmedic.helper_main as hm
    from netmedic.helper_verbs import VerbPlan

    seen = []
    monkeypatch.setattr(hm, "_journal_result", lambda v, ok, m: seen.append((v, ok, m)))
    # Pin mismatch aborts before any exec — pure logic path, no root needed.
    plan = VerbPlan("vpn-run-script", [["__vpn_script__", "/tmp/x.sh", "00" * 32]])
    res = hm.execute_plan(plan, timeout=5)
    assert res["ok"] is False
    assert seen == [("vpn-run-script", False, res["message"])]


def test_helper_journal_best_effort_on_syslog_failure(monkeypatch):
    """Journal failure never breaks the verb result (nor stdout)."""
    import sys

    import netmedic.helper_main as hm
    from netmedic.helper_verbs import VerbPlan

    class Boom:
        LOG_PID = 0
        LOG_AUTH = 0
        LOG_INFO = 0
        LOG_WARNING = 0

        @staticmethod
        def openlog(*a, **k):
            raise OSError("no journal here")

    monkeypatch.setitem(sys.modules, "syslog", Boom)
    plan = VerbPlan("vpn-run-script", [["__vpn_script__", "/tmp/x.sh", "00" * 32]])
    res = hm.execute_plan(plan, timeout=5)  # must not raise
    assert res["ok"] is False
