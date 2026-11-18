"""Fase 6.1: recoverability contracts for change-dns / restart-adapter.

These tests pin the root-side behaviour without touching real nmcli/ip:
the executor, clock and sysfs root are injectable. Every scenario records
the exact argv/timeout the executor received, so budget regressions fail
here instead of in production.
"""

import subprocess
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from netmedic import helper_main as hm
from netmedic.helper_verbs import plan_to_dict, plan_verb

TOTAL = 30

Call = Tuple[List[str], float]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cp(rc: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _dns_plan(conn: str = "Wired", server: str = "8.8.8.8") -> Any:
    return plan_verb("change-dns", {"connection": conn, "server": server})


def _restart_plan(iface: str = "eth0") -> Any:
    return plan_verb("restart-adapter", {"iface": iface})


def _snapshot_dns(argv: List[str]) -> bool:
    return "-g" in argv and "ipv4.dns" in argv


def _snapshot_ignore(argv: List[str]) -> bool:
    return "-g" in argv and "ipv4.ignore-auto-dns" in argv


def _con_mod(argv: List[str]) -> bool:
    return argv[:3] == ["nmcli", "con", "mod"]


def _con_up(argv: List[str]) -> bool:
    return argv[:3] == ["nmcli", "con", "up"]


def _record(calls: List[Call], clock: Clock, argv: List[str], timeout: Optional[float]) -> None:
    """Every command must fit in the total deadline that is still left."""
    assert timeout is not None
    assert timeout > 0
    remaining_total = TOTAL - clock.now
    assert timeout <= remaining_total + 1e-6, (
        f"command got {timeout:.3f}s but only {remaining_total:.3f}s of the "
        f"verb deadline remained: {argv}"
    )
    calls.append((list(argv), timeout))


def _responder(
    clock: Clock,
    calls: List[Call],
    *,
    prev_dns: str = "1.2.3.4\n",
    prev_ignore: str = "no\n",
    snapshot_rc: int = 0,
    snapshot_timeout: bool = False,
    mod_rc: int = 0,
    mod_timeout: bool = False,
    up_rc: int = 0,
    up_timeout: bool = False,
    restore_rc: int = 0,
    restore_timeout: bool = False,
    cost: float = 0.01,
) -> Callable[[List[str], Optional[float]], subprocess.CompletedProcess[str]]:
    def run(argv: List[str], timeout: Optional[float]) -> subprocess.CompletedProcess[str]:
        _record(calls, clock, argv, timeout)
        assert timeout is not None
        clock.advance(cost)
        if _snapshot_dns(argv):
            if snapshot_timeout:
                clock.advance(timeout)
                raise subprocess.TimeoutExpired(argv, timeout)
            return _cp(snapshot_rc, prev_dns if snapshot_rc == 0 else "")
        if _snapshot_ignore(argv):
            if snapshot_timeout:
                clock.advance(timeout)
                raise subprocess.TimeoutExpired(argv, timeout)
            return _cp(snapshot_rc, prev_ignore if snapshot_rc == 0 else "")
        if _con_mod(argv):
            is_restore = "8.8.8.8" not in argv
            if is_restore:
                if restore_timeout:
                    clock.advance(timeout)
                    raise subprocess.TimeoutExpired(argv, timeout)
                return _cp(restore_rc)
            if mod_timeout:
                clock.advance(timeout)
                raise subprocess.TimeoutExpired(argv, timeout)
            return _cp(mod_rc)
        if _con_up(argv):
            if up_timeout:
                clock.advance(timeout)
                raise subprocess.TimeoutExpired(argv, timeout)
            return _cp(up_rc)
        raise AssertionError(f"unexpected argv: {argv}")

    return run


def _restore_argvs(calls: List[Call]) -> List[List[str]]:
    return [argv for argv, _ in calls if _con_mod(argv) and "8.8.8.8" not in argv]


# ---------------------------------------------------------------------------
# change-dns
# ---------------------------------------------------------------------------


def test_dry_run_commands_are_the_ones_executed() -> None:
    clock = Clock()
    calls: List[Call] = []
    plan = _dns_plan()

    res = hm._execute_change_dns(
        plan, TOTAL, executor=_responder(clock, calls), clock=clock
    )

    assert res["ok"] is True
    assert plan.params == {"connection": "Wired", "server": "8.8.8.8"}
    assert plan_to_dict(plan)["commands"] == plan.commands
    assert [argv for argv, _ in calls[2:]] == plan.commands


def test_change_dns_schedules_every_command_inside_one_deadline() -> None:
    """Regression for #45: each nmcli got the full apply budget."""
    clock = Clock()
    calls: List[Call] = []
    apply_deadline = TOTAL - TOTAL / 3
    phase = {"name": "apply"}

    def run(argv: List[str], timeout: Optional[float]) -> subprocess.CompletedProcess[str]:
        _record(calls, clock, argv, timeout)
        assert timeout is not None
        if phase["name"] == "apply":
            assert timeout <= apply_deadline - clock.now + 1e-6, (
                f"apply command got {timeout:.3f}s beyond apply_deadline: {argv}"
            )
        # Burn 99% of whatever this command was allowed; the next command
        # must still get the (smaller) remainder of the shared deadline.
        clock.advance(timeout * 0.99)
        if _snapshot_dns(argv):
            return _cp(0, "1.2.3.4\n")
        if _snapshot_ignore(argv):
            return _cp(0, "no\n")
        if _con_up(argv):
            phase["name"] = "rollback"
            return _cp(1)
        return _cp(0)

    res = hm._execute_change_dns(_dns_plan(), TOTAL, executor=run, clock=clock)

    assert res["ok"] is False
    assert clock.now <= TOTAL + 1e-6
    assert _restore_argvs(calls), "rollback did not run after apply consumed the budget"
    # Rollback has a reserved slice even when apply exhausted its phase.
    rollback_timeout = next(t for argv, t in calls if _con_mod(argv) and "8.8.8.8" not in argv)
    assert rollback_timeout > 0
    assert rollback_timeout <= TOTAL / 3 + 1e-6


def test_snapshot_returncode_aborts_before_any_modification() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, snapshot_rc=1),
        clock=clock,
    )

    assert res["ok"] is False
    assert "config=unchanged" in str(res["details"])
    assert not any(_con_mod(argv) or _con_up(argv) for argv, _ in calls)
    assert not any("8.8.8.8" in argv for argv, _ in calls)


def test_snapshot_timeout_aborts_before_any_modification() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, snapshot_timeout=True),
        clock=clock,
    )

    assert res["ok"] is False
    assert "config=unchanged" in str(res["details"])
    assert not any(_con_mod(argv) or _con_up(argv) for argv, _ in calls)


def test_invalid_previous_dns_aborts_before_any_modification() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, prev_dns="not-an-ip\n"),
        clock=clock,
    )

    assert res["ok"] is False
    assert "config=unchanged" in str(res["details"])
    assert not any(_con_mod(argv) or _con_up(argv) for argv, _ in calls)
    assert not any("8.8.8.8" in argv for argv, _ in calls)


def test_empty_previous_ignore_auto_dns_aborts_before_any_modification() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, prev_ignore="\n"),
        clock=clock,
    )

    assert res["ok"] is False
    assert "config=unchanged" in str(res["details"])
    assert not any(_con_mod(argv) or _con_up(argv) for argv, _ in calls)


def test_con_mod_failure_restores_previous_config() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, mod_rc=1),
        clock=clock,
    )

    assert res["ok"] is False
    assert "reverted" in res["message"].lower()
    assert "not confirmed" in res["message"].lower()
    assert "reactivation=unconfirmed" in str(res["details"])
    assert _restore_argvs(calls) == [
        [
            "nmcli",
            "con",
            "mod",
            "Wired",
            "ipv4.dns",
            "1.2.3.4",
            "ipv4.ignore-auto-dns",
            "no",
        ]
    ]


def test_con_mod_timeout_restores_previous_config() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, mod_timeout=True),
        clock=clock,
    )

    assert res["ok"] is False
    assert "reverted" in res["message"].lower()
    assert _restore_argvs(calls)


def test_con_up_failure_restores_previous_config() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, up_rc=1),
        clock=clock,
    )

    assert res["ok"] is False
    assert "reverted" in res["message"].lower()
    assert "not confirmed" in res["message"].lower()
    assert _restore_argvs(calls)


def test_con_up_timeout_restores_previous_config() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, up_timeout=True),
        clock=clock,
    )

    assert res["ok"] is False
    assert "reverted" in res["message"].lower()
    assert _restore_argvs(calls)


def test_previous_ignore_auto_dns_no_is_restored_exactly() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, prev_ignore="no\n", up_rc=1),
        clock=clock,
    )

    assert res["ok"] is False
    restore = _restore_argvs(calls)[0]
    assert restore[-2:] == ["ipv4.ignore-auto-dns", "no"]
    assert restore[restore.index("ipv4.dns") + 1] == "1.2.3.4"


def test_empty_previous_dns_is_valid_and_restored() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, prev_dns="\n", up_rc=1),
        clock=clock,
    )

    assert res["ok"] is False
    restore = _restore_argvs(calls)[0]
    assert restore[restore.index("ipv4.dns") + 1] == ""


def test_rollback_failure_reports_exact_manual_command() -> None:
    clock = Clock()
    calls: List[Call] = []

    res = hm._execute_change_dns(
        _dns_plan(),
        TOTAL,
        executor=_responder(clock, calls, up_rc=1, restore_rc=1),
        clock=clock,
    )

    assert res["ok"] is False
    assert "rollback FAILED" in res["message"]
    assert "nmcli con mod" in res["message"]
    assert "1.2.3.4" in res["message"]
    assert "ipv4.ignore-auto-dns no" in res["message"]
    assert "config=not-restored" in str(res["details"])


def test_budget_exhausted_during_rollback_is_reported_truthfully() -> None:
    clock = Clock()
    calls: List[Call] = []

    def run(argv: List[str], timeout: Optional[float]) -> subprocess.CompletedProcess[str]:
        _record(calls, clock, argv, timeout)
        assert timeout is not None
        if _snapshot_dns(argv):
            clock.advance(0.01)
            return _cp(0, "1.2.3.4\n")
        if _snapshot_ignore(argv):
            clock.advance(0.01)
            return _cp(0, "no\n")
        if _con_mod(argv) and "8.8.8.8" in argv:
            # Consume the entire apply slice.
            clock.advance(timeout)
            return _cp(0)
        if _con_mod(argv):
            # Rollback restore consumes its whole reserved slice and times out.
            clock.advance(timeout)
            raise subprocess.TimeoutExpired(argv, timeout)
        raise AssertionError(f"unexpected argv: {argv}")

    res = hm._execute_change_dns(_dns_plan(), TOTAL, executor=run, clock=clock)

    assert res["ok"] is False
    assert "rollback FAILED" in res["message"]
    assert clock.now <= TOTAL + 1e-6
    # No rollback `con up` attempt is made once the reserved slice is gone.
    assert not any(_con_up(argv) for argv, _ in calls)


class _CapturingSyslog:
    LOG_PID = 0
    LOG_AUTH = 0
    LOG_INFO = 0
    LOG_WARNING = 0

    def __init__(self) -> None:
        self.lines: List[str] = []

    def openlog(self, *args: object, **kwargs: object) -> None:
        pass

    def closelog(self) -> None:
        pass

    def syslog(self, level: int, message: str) -> None:
        self.lines.append(message)


def test_one_journal_entry_per_attempt_and_one_per_rollback(
    monkeypatch: Any,
) -> None:
    import sys

    journal = _CapturingSyslog()
    monkeypatch.setitem(sys.modules, "syslog", journal)
    monkeypatch.setenv("PKEXEC_UID", "1000")
    clock = Clock()
    calls: List[Call] = []
    monkeypatch.setattr(hm.time, "monotonic", clock)
    monkeypatch.setattr(hm, "_run_argv", _responder(clock, calls, up_rc=1))

    res = hm.execute_plan(_dns_plan(), timeout=TOTAL)

    assert res["ok"] is False
    assert len(journal.lines) == 2
    assert all("pkexec_uid=1000" in line for line in journal.lines)
    rollback = [line for line in journal.lines if line.startswith("verb=change-dns-rollback ")]
    attempt = [line for line in journal.lines if line.startswith("verb=change-dns ok=0 ")]
    assert len(rollback) == 1
    assert len(attempt) == 1
    assert "reactivation unconfirmed" in rollback[0]


def test_plan_verb_is_pure(monkeypatch: Any) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("plan_verb executed a command")

    monkeypatch.setattr(hm.subprocess, "Popen", boom)
    plan = _dns_plan()
    assert plan.commands[0][0] == "nmcli"


# ---------------------------------------------------------------------------
# restart-adapter
# ---------------------------------------------------------------------------


def _sysfs(tmp_path: Path, iface: str, flags: str, carrier: Optional[str]) -> Path:
    root = tmp_path / "net"
    dev = root / iface
    dev.mkdir(parents=True)
    (dev / "flags").write_text(flags + "\n")
    if carrier is not None:
        (dev / "carrier").write_text(carrier + "\n")
    return root


def _restart_runner(
    clock: Clock,
    calls: List[Call],
    *,
    up_results: Optional[List[Any]] = None,
) -> Callable[[List[str], Optional[float]], subprocess.CompletedProcess[str]]:
    pending = list(up_results or [("rc", 0)])

    def run(argv: List[str], timeout: Optional[float]) -> subprocess.CompletedProcess[str]:
        _record(calls, clock, argv, timeout)
        assert timeout is not None
        if argv[-1] == "up":
            action = pending.pop(0) if pending else ("rc", 0)
            if action[0] == "timeout":
                clock.advance(timeout)
                raise subprocess.TimeoutExpired(argv, timeout)
            clock.advance(0.01)
            return _cp(int(action[1]))
        clock.advance(0.01)
        return _cp(0)

    return run


def test_restart_adapter_executes_planned_commands(tmp_path: Path) -> None:
    clock = Clock()
    calls: List[Call] = []
    root = _sysfs(tmp_path, "eth0", "0x1003", "1")

    res = hm._execute_restart_adapter(
        _restart_plan(),
        TOTAL,
        executor=_restart_runner(clock, calls),
        clock=clock,
        sysfs_root=root,
    )

    assert res["ok"] is True
    assert "carrier detected" in res["message"]
    assert [argv for argv, _ in calls] == _restart_plan().commands


def test_restart_adapter_up_timeout_gets_a_final_attempt(tmp_path: Path) -> None:
    clock = Clock()
    calls: List[Call] = []
    root = _sysfs(tmp_path, "eth0", "0x1003", "1")

    res = hm._execute_restart_adapter(
        _restart_plan(),
        TOTAL,
        executor=_restart_runner(clock, calls, up_results=[("timeout", None), ("rc", 0)]),
        clock=clock,
        sysfs_root=root,
    )

    assert res["ok"] is True
    assert sum(1 for argv, _ in calls if argv[-1] == "up") == 2
    assert clock.now <= TOTAL + 1e-6


def test_restart_adapter_loopback_unknown_is_not_a_failure(tmp_path: Path) -> None:
    clock = Clock()
    calls: List[Call] = []
    root = _sysfs(tmp_path, "lo", "0x9", None)

    res = hm._execute_restart_adapter(
        _restart_plan("lo"),
        TOTAL,
        executor=_restart_runner(clock, calls),
        clock=clock,
        sysfs_root=root,
    )

    assert res["ok"] is True
    assert "carrier unknown" in res["message"]


def test_restart_adapter_up_without_carrier_is_distinguished(tmp_path: Path) -> None:
    clock = Clock()
    calls: List[Call] = []
    root = _sysfs(tmp_path, "eth0", "0x1003", "0")

    res = hm._execute_restart_adapter(
        _restart_plan(),
        TOTAL,
        executor=_restart_runner(clock, calls),
        clock=clock,
        sysfs_root=root,
    )

    assert res["ok"] is True
    assert "no carrier" in res["message"]


def test_restart_adapter_stays_down_is_reported(tmp_path: Path) -> None:
    clock = Clock()
    calls: List[Call] = []
    root = _sysfs(tmp_path, "eth0", "0x1002", "0")

    res = hm._execute_restart_adapter(
        _restart_plan(),
        TOTAL,
        executor=_restart_runner(clock, calls),
        clock=clock,
        sysfs_root=root,
    )

    assert res["ok"] is False
    assert "not UP" in res["message"]
    assert "iff_up=down" in str(res["details"])
    assert "carrier=down" in str(res["details"])


def test_restart_adapter_both_up_timeouts_report_final_state(tmp_path: Path) -> None:
    clock = Clock()
    calls: List[Call] = []
    root = _sysfs(tmp_path, "eth0", "0x1002", "0")

    res = hm._execute_restart_adapter(
        _restart_plan(),
        TOTAL,
        executor=_restart_runner(
            clock, calls, up_results=[("timeout", None), ("timeout", None)]
        ),
        clock=clock,
        sysfs_root=root,
    )

    assert res["ok"] is False
    assert sum(1 for argv, _ in calls if argv[-1] == "up") == 2
    assert clock.now <= TOTAL + 1e-6
    assert "not UP" in res["message"]


def test_helper_timeout_help_describes_total_deadline() -> None:
    help_text = hm.build_parser().format_help().lower()
    assert "total" in help_text
    assert "deadline" in help_text
