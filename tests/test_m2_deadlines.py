"""M2: process-group deadline enforcement (no orphaned root children)."""

import os
import signal
import stat
import subprocess
import time

from netmedic.helper_main import (
    DeadlineResult,
    _kill_process_group,
    _run_argv,
    execute_with_deadline,
)


def _sleep_pids():
    try:
        out = subprocess.run(
            ["pgrep", "sleep"], capture_output=True, text=True, timeout=2
        )
    except Exception:
        return set()
    if out.returncode != 0:
        return set()
    return {p for p in out.stdout.split() if p.strip()}


def test_fast_command_no_timeout():
    res = execute_with_deadline(["echo", "m2-ok"], deadline=5.0)
    assert isinstance(res, DeadlineResult)
    assert res.stdout.strip() == "m2-ok"
    assert res.timeout is False
    assert res.exit_code == 0
    assert res.process_group_killed is False
    assert res.to_dict()["timeout"] is False


def test_slow_command_group_killed():
    before = _sleep_pids()
    start = time.time()
    res = execute_with_deadline(["sleep", "100"], deadline=0.5)
    elapsed = time.time() - start
    assert res.timeout is True
    assert res.process_group_killed is True
    assert res.exit_code == -signal.SIGKILL
    assert elapsed < 5.0
    assert "Deadline exceeded" in res.stderr
    time.sleep(0.3)
    assert set(_sleep_pids()) <= before


def test_spawned_children_die_with_group(tmp_path):
    """Parent + backgrounded children must all die (the M2 core case)."""
    script = tmp_path / "fork.sh"
    script.write_text("#!/bin/sh\nsleep 60 &\nsleep 60\n")
    os.chmod(script, 0o700)
    before = _sleep_pids()
    res = execute_with_deadline(["/bin/sh", str(script)], deadline=0.5)
    assert res.timeout is True
    time.sleep(0.5)
    orphans = set(_sleep_pids()) - before
    assert orphans == set(), f"orphaned sleepers: {orphans}"


def test_run_argv_kills_group_on_timeout():
    """_run_argv keeps its signature but now killpgs before re-raising."""
    before = _sleep_pids()
    try:
        _run_argv(["sleep", "100"], timeout=1)
    except subprocess.TimeoutExpired:
        pass
    else:
        raise AssertionError("expected TimeoutExpired")
    time.sleep(0.3)
    assert set(_sleep_pids()) <= before


def test_kill_process_group_dead_proc_no_raise():
    proc = subprocess.Popen(["true"])
    proc.wait()
    _kill_process_group(proc)  # must not raise


def test_grandchild_processes_killed(tmp_path):
    """Parent -> child -> grandchild chain all die (nested groups)."""
    script = tmp_path / "nested.sh"
    script.write_text("#!/bin/sh\nsh -c 'sleep 60' &\nsleep 60\n")
    os.chmod(script, 0o700)
    before = _sleep_pids()
    res = execute_with_deadline(["/bin/sh", str(script)], deadline=0.5)
    assert res.timeout is True
    time.sleep(0.5)
    assert set(_sleep_pids()) - before == set()


def test_concurrent_run_argv_isolated():
    """Two simultaneous calls: timeout on one must not kill the other."""
    import threading

    results = {}

    def slow():
        try:
            _run_argv(["sleep", "100"], timeout=1)
        except subprocess.TimeoutExpired:
            results["slow"] = "timeout"
        else:
            results["slow"] = "unexpected-ok"

    def fast():
        proc = _run_argv(["echo", "alive"], timeout=5)
        results["fast"] = proc.stdout.strip()

    t_slow = threading.Thread(target=slow)
    t_fast = threading.Thread(target=fast)
    t_slow.start()
    time.sleep(0.2)  # let the slow call own its group first
    t_fast.start()
    t_slow.join(timeout=10)
    t_fast.join(timeout=10)
    assert results.get("slow") == "timeout"
    assert results.get("fast") == "alive"


def test_no_signal_handlers_installed():
    """M2 installs no process-global handlers (thread-safe by design)."""
    before = signal.getsignal(signal.SIGALRM)
    execute_with_deadline(["echo", "hi"], deadline=5.0)
    try:
        _run_argv(["echo", "hi"], timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError("echo should not time out") from exc
    assert signal.getsignal(signal.SIGALRM) == before


def test_partial_output_captured_on_timeout(tmp_path):
    """Buffered stdout before the hang is returned, not lost."""
    script = tmp_path / "partial.sh"
    script.write_text("#!/bin/sh\necho m2-partial\nsleep 60\n")
    os.chmod(script, 0o700)
    res = execute_with_deadline(["/bin/sh", str(script)], deadline=0.5)
    assert res.timeout is True
    assert "m2-partial" in res.stdout


def test_kill_process_group_stat_modes_untouched(tmp_path):
    # Sanity: helper staging perms unaffected by M2 (regression guard).
    from netmedic.helper_main import _stage_verified_copy
    import hashlib

    src = tmp_path / "s.sh"
    src.write_bytes(b"#!/bin/sh\necho hi\n")
    digest = hashlib.sha256(b"#!/bin/sh\necho hi\n").hexdigest()
    staged = _stage_verified_copy(str(src), digest, str(tmp_path / "st"))
    assert oct(os.stat(staged).st_mode & 0o777) == oct(0o700)
    assert oct(os.stat(tmp_path / "st").st_mode & 0o777) == oct(0o700)
    os.unlink(staged)
    assert stat.S_IMODE(os.stat(tmp_path / "st").st_mode) == 0o700


def test_daemon_uses_helper_deadline_plus_margin(monkeypatch):
    """Daemon passes bare deadline to helper, waits deadline+margin."""
    from netmedic.system import CommandRunner
    from netmedic.models import CommandResult
    import json

    monkeypatch.setenv("NETMEDIC_USE_HELPER", "1")
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/pkexec")
    from pathlib import Path

    monkeypatch.setattr(
        "netmedic.config.Config.get_helper_path",
        staticmethod(lambda: Path("/usr/libexec/netmedic/helper")),
    )
    monkeypatch.setattr(
        CommandRunner, "_check_helper_version", staticmethod(lambda: None)
    )
    seen = {}

    def fake_run(command, require_root=False, timeout=None):
        seen["timeout"] = timeout
        seen["cmd"] = list(command)
        payload = json.dumps({"ok": True, "message": "ok", "details": None})
        return CommandResult(True, 0, payload, "", list(command))

    monkeypatch.setattr(CommandRunner, "run", staticmethod(fake_run))
    res = CommandRunner.run_elevated("flush-dns", {}, timeout=30)
    assert res.success is True
    # Helper argv carries the bare deadline...
    assert "--timeout" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--timeout") + 1] == "30"
    # ...while the daemon waits deadline + IPC margin.
    assert seen["timeout"] == 30 + CommandRunner._IPC_MARGIN


def test_ipc_stop_does_not_block_on_inflight(monkeypatch):
    """stop() must not join behind an in-flight elevated call."""
    import netmedic.ipc_bridge as bridge

    class FakePool:
        def __init__(self):
            self.kwargs = None

        def shutdown(self, **kwargs):
            self.kwargs = kwargs
            # Simulate a slow in-flight task: with wait=True this would hang.
            if kwargs.get("wait"):
                time.sleep(30)

    server = bridge.NetMedicIPCServer.__new__(bridge.NetMedicIPCServer)
    server.running = True
    server._pool = FakePool()
    server.thread = None
    server.server = None
    start = time.time()
    server.stop()
    assert time.time() - start < 5.0
    assert server._pool.kwargs.get("wait") is False
