"""Privileged IPC execution is serialized to avoid worker-pool exhaustion."""

import os
import threading
import time
from unittest.mock import MagicMock, patch

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_security import IPCSession
from netmedic.models import NetResult

_PEER = {"peer_uid": os.getuid(), "peer_pid": os.getpid()}


def test_second_privileged_call_busy_while_first_runs(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    token = session.issue_token()
    medic = MagicMock()

    started = threading.Event()
    release = threading.Event()

    def slow_flush():
        started.set()
        release.wait(timeout=5)
        return NetResult("Flush DNS", True, "flushed")

    medic.flush_dns.side_effect = slow_flush
    dispatch = create_action_dispatcher(medic, session)

    results = {}

    def worker_a():
        results["a"] = dispatch(
            "flush_dns",
            {"confirmed": True, "session_token": token},
            **_PEER,
        )

    def worker_b():
        started.wait(timeout=5)
        results["b"] = dispatch(
            "renew_ip",
            {"confirmed": True, "session_token": token},
            **_PEER,
        )

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)
    t_a.start()
    assert started.wait(timeout=5)
    t_b.start()
    t_b.join(timeout=5)
    release.set()
    t_a.join(timeout=5)

    assert results["a"]["status"] == "ok"
    assert results["b"]["status"] == "error"
    assert results["b"].get("busy") is True
    assert "already running" in results["b"]["message"].lower()


def test_privileged_slot_released_after_completion(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    token = session.issue_token()
    medic = MagicMock()
    medic.flush_dns.return_value = NetResult("Flush DNS", True, "ok")
    dispatch = create_action_dispatcher(medic, session)

    first = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        **_PEER,
    )
    second = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        **_PEER,
    )
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert medic.flush_dns.call_count == 2
