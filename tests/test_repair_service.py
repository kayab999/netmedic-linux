"""M8: Smart Repair runs headless (no GTK) via netmedic.repair."""

from netmedic.models import NetResult, ResultCode
from netmedic.repair import RepairCallbacks, RepairDeps, run_smart_repair


def _nr(op="Op", ok=True, code=None, data=None, details=None, msg="m"):
    if code is None:
        code = ResultCode.OK if ok else ResultCode.FAILED
    return NetResult(op, ok, msg, data=data, details=details, code=code)


def _diag(gateway_ok=True, dns_ok=True, net_ok=True):
    return _nr("Diag", gateway_ok and dns_ok and net_ok,
               data={"gateway_ok": gateway_ok, "dns_ok": dns_ok, "internet_ok": net_ok},
               details={"gateway": "gw", "gateway_ok": gateway_ok})


class _Driver:
    """Fake deps recording every call; GTK-free."""

    def __init__(self, states, verify=True):
        self.states = list(states)
        self.calls = []
        self.settles = []
        self.logs = []
        self.deps = RepairDeps(
            diagnose=self._diagnose,
            act=self._act,
            settle=self._settle,
            default_iface=lambda: "eth0",
            verify=verify,
        )
        self.cb = RepairCallbacks(
            log=self.logs.append,
            push_status=lambda _m: None,
            pop_status=lambda: None,
        )

    def _diagnose(self):
        self.calls.append("diagnose")
        return self.states.pop(0)

    def _act(self, action):
        self.calls.append(action)
        return _nr(action, True, code=ResultCode.EXECUTED)

    def _settle(self, iface, timeout):
        self.settles.append((iface, timeout))

    def run(self):
        return run_smart_repair(self.deps, self.cb)


def test_healthy_short_circuits_without_elevation():
    d = _Driver([_diag(True, True, True), _diag(True, True, True)])
    res = d.run()
    assert res.code == ResultCode.SKIPPED
    assert d.calls == ["diagnose", "diagnose"]
    assert "flush_dns" not in d.calls and "renew_ip" not in d.calls


def test_full_repair_verified_ok():
    d = _Driver([_diag(True, False, False), _diag(True, True, True)])
    res = d.run()
    assert res.code == ResultCode.OK
    assert "SUCCESS (verified)" in res.message
    assert d.calls == ["diagnose", "flush_dns", "renew_ip", "diagnose"]
    assert d.settles == [("eth0", 8)]
    assert res.data["repairs_ok"] is True


def test_no_gateway_skips_renew():
    d = _Driver([_diag(False, False, False), _diag(False, False, False)])
    d.run()
    assert "flush_dns" in d.calls
    assert "renew_ip" not in d.calls
    assert any("skipping IP renewal" in m for m in d.logs)


def test_verify_disabled_never_ok():
    d = _Driver([_diag(True, False, False)], verify=False)
    res = d.run()
    assert res.code == ResultCode.EXECUTED
    assert "DISABLED" in res.message
    assert "diagnose" in d.calls and d.calls.count("diagnose") == 1


def test_partial_dns_only():
    d = _Driver([_diag(True, False, False), _diag(True, True, False)])
    res = d.run()
    assert res.code == ResultCode.PARTIAL
    assert "upstream" in res.message


def test_failed_repair_propagates():
    d = _Driver([_diag(True, False, False), _diag(True, False, False)])

    def failing_act(action):
        d.calls.append(action)
        return _nr(action, False, code=ResultCode.FAILED)

    d.deps = RepairDeps(diagnose=d._diagnose, act=failing_act, settle=d._settle,
                        default_iface=lambda: "eth0", verify=True)
    res = run_smart_repair(d.deps, d.cb)
    assert res.code == ResultCode.FAILED
    assert res.data["repairs_ok"] is False


def test_silent_callbacks_for_cli():
    cb = RepairCallbacks.silent()
    cb.log("x")
    cb.push_status("y")
    cb.pop_status()
