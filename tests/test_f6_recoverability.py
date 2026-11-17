"""Fase 6: recoverability of change-dns / restart-adapter (helper side)."""

import subprocess
import netmedic.helper_main as hm
from netmedic.helper_verbs import VerbPlan


def _cp(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def test_change_dns_success(monkeypatch):
    calls = []

    def fake_nmcli(args, timeout):
        calls.append(args)
        if "-g" in args:
            if "ignore-auto-dns" in " ".join(args):
                return _cp(0, "no\n", "")
            return _cp(0, "1.2.3.4\n", "")
        return _cp(0, "ok", "")

    monkeypatch.setattr(hm, "_run_nmcli", fake_nmcli)
    plan = VerbPlan("change-dns", [["nmcli", "con", "mod", "Wired", "ipv4.dns", "8.8.8.8", "ipv4.ignore-auto-dns", "yes"], ["nmcli", "con", "up", "Wired"]])
    res = hm._execute_change_dns(plan, timeout=30)
    assert res["ok"] is True


def test_change_dns_snapshot_invalid_aborts_before_mod(monkeypatch):
    def fake_nmcli(args, timeout):
        if "-g" in args and "ipv4.dns" in args:
            return _cp(0, "not-an-ip\n", "")
        return _cp(0, "no\n", "")

    monkeypatch.setattr(hm, "_run_nmcli", fake_nmcli)
    mod_calls = []

    def tracking_nmcli(args, timeout):
        mod_calls.append(args)
        return fake_nmcli(args, timeout)

    monkeypatch.setattr(hm, "_run_nmcli", tracking_nmcli)
    plan = VerbPlan("change-dns", [["nmcli", "con", "mod", "Wired", "ipv4.dns", "8.8.8.8", "ipv4.ignore-auto-dns", "yes"], ["nmcli", "con", "up", "Wired"]])
    res = hm._execute_change_dns(plan, timeout=30)
    assert res["ok"] is False
    # no con mod should have run (only snapshot calls)
    assert not any("mod" in c for c in mod_calls if c and c[1:2] == ["con"] and len(c) > 2 and c[2] == "mod")


def test_change_dns_empty_prev_dns_ok(monkeypatch):
    def fake_nmcli(args, timeout):
        if "-g" in args and "ipv4.dns" in args:
            return _cp(0, "\n", "")
        if "-g" in args and "ipv4.ignore-auto-dns" in args:
            return _cp(0, "no\n", "")
        return _cp(0, "ok", "")

    monkeypatch.setattr(hm, "_run_nmcli", fake_nmcli)
    plan = VerbPlan("change-dns", [["nmcli", "con", "mod", "Wired", "ipv4.dns", "8.8.8.8", "ipv4.ignore-auto-dns", "yes"], ["nmcli", "con", "up", "Wired"]])
    res = hm._execute_change_dns(plan, timeout=30)
    assert res["ok"] is True


def test_change_dns_rollback_on_up_failure(monkeypatch):
    state = {"mod": 0, "up": 0}

    def fake_nmcli(args, timeout):
        if "-g" in args:
            if "ipv4.dns" in args:
                return _cp(0, "1.2.3.4\n", "")
            return _cp(0, "yes\n", "")
        if "mod" in args:
            state["mod"] += 1
            return _cp(0, "ok", "")
        if "up" in args:
            state["up"] += 1
            if state["up"] == 1:
                return _cp(1, "", "up failed")
            return _cp(0, "ok", "")
        return _cp(0, "ok", "")

    monkeypatch.setattr(hm, "_run_nmcli", fake_nmcli)
    plan = VerbPlan("change-dns", [["nmcli", "con", "mod", "Wired", "ipv4.dns", "8.8.8.8", "ipv4.ignore-auto-dns", "yes"], ["nmcli", "con", "up", "Wired"]])
    res = hm._execute_change_dns(plan, timeout=30)
    assert res["ok"] is False
    assert "reverted" in res["message"].lower() or "rollback" in res["message"].lower()


def test_change_dns_rollback_failure_message(monkeypatch):
    def fake_nmcli(args, timeout):
        if "-g" in args:
            if "ipv4.dns" in args:
                return _cp(0, "1.2.3.4\n", "")
            return _cp(0, "yes\n", "")
        if "mod" in args:
            # first mod (apply) succeeds, restore mod fails
            if "8.8.8.8" in args:
                return _cp(0, "ok", "")
            return _cp(1, "", "restore failed")
        if "up" in args:
            return _cp(1, "", "up failed")
        return _cp(0, "ok", "")

    monkeypatch.setattr(hm, "_run_nmcli", fake_nmcli)
    plan = VerbPlan("change-dns", [["nmcli", "con", "mod", "Wired", "ipv4.dns", "8.8.8.8", "ipv4.ignore-auto-dns", "yes"], ["nmcli", "con", "up", "Wired"]])
    res = hm._execute_change_dns(plan, timeout=30)
    assert res["ok"] is False
    assert "rollback FAILED" in res["message"] or "rollback failed" in res["message"].lower()


def test_restart_adapter_success(monkeypatch, tmp_path):
    iface = "eth0"
    flags_file = tmp_path / "flags"
    flags_file.write_text("0x1003")

    def fake_run_argv(argv, timeout):
        return _cp(0, "", "")

    monkeypatch.setattr(hm, "_run_argv", fake_run_argv)
    monkeypatch.setattr(hm, "Path", lambda p: flags_file if "flags" in p else __import__("pathlib").Path(p))
    plan = VerbPlan("restart-adapter", [["ip", "link", "set", iface, "down"], ["ip", "link", "set", iface, "up"]])
    res = hm._execute_restart_adapter(plan, timeout=30)
    assert res["ok"] is True


def test_restart_adapter_up_retry_and_final_state(monkeypatch, tmp_path):
    iface = "eth0"
    flags_file = tmp_path / "flags"
    flags_file.write_text("0x1002")  # IFF_UP not set

    def fake_run_argv(argv, timeout):
        return _cp(0, "", "")

    monkeypatch.setattr(hm, "_run_argv", fake_run_argv)
    monkeypatch.setattr(hm, "Path", lambda p: flags_file if "flags" in p else __import__("pathlib").Path(p))
    plan = VerbPlan("restart-adapter", [["ip", "link", "set", iface, "down"], ["ip", "link", "set", iface, "up"]])
    res = hm._execute_restart_adapter(plan, timeout=30)
    assert res["ok"] is False
    assert "not UP" in res["message"]
