"""Headless Smart Repair orchestration (M8: extracted from ui.py).

The repair *flow* (diagnose → conditional flush/renew → verify → delta
verdict) lives here with zero GTK imports, so headless, MCP and AI paths
can drive it. The UI (and any other frontend) supplies progress callbacks
and IPC-bound callables. Privileged steps go through the caller's `act`
— in the UI that is `_ipc_action`, so polkit + audit cover the path.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from netmedic.models import NetResult, ResultCode
from netmedic.system import CommandRunner

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RepairCallbacks:
    """Progress sinks. UI wires these to GLib.idle_add; headless collects."""

    log: Callable[[str], None]
    push_status: Callable[[str], None]
    pop_status: Callable[[], None]

    @staticmethod
    def silent() -> "RepairCallbacks":
        """No-op sinks for headless/CLI use."""
        return RepairCallbacks(log=lambda _m: None, push_status=lambda _m: None,
                               pop_status=lambda: None)


@dataclasses.dataclass(frozen=True)
class RepairDeps:
    """Repair flow inputs. All side effects enter through these."""

    diagnose: Callable[[], NetResult]
    act: Callable[[str], NetResult]
    settle: Callable[[Optional[str], int], None]
    default_iface: Callable[[], Optional[str]]
    verify: bool = True


def verify_enabled_from_env() -> bool:
    """POST_REPAIR_VERIFY flag (default ON); debug escape hatch only."""
    return os.environ.get("NETMEDIC_POST_REPAIR_VERIFY", "1").lower() not in ("0", "false", "no")


def wait_for_settle(iface: Optional[str], timeout: int = 8) -> None:
    """Poll settle instead of blind sleep. Checks IP + NM activated state."""
    start = time.monotonic()
    if not iface:
        # No iface to wait for; short sleep
        time.sleep(1)
        logger.info("settle: no iface, slept 1s")
        return
    for _i in range(max(1, timeout)):
        # Check IPv4 present
        res = CommandRunner.run(["ip", "-4", "addr", "show", iface])
        has_ip = res.success and "inet " in (res.stdout or "")
        # Check NM device state activated (best-effort)
        nm = CommandRunner.run(["nmcli", "-t", "-f", "GENERAL.STATE", "device", "show", iface])
        nm_ok = nm.success and "activated" in (nm.stdout or "").lower()
        if has_ip and (nm_ok or not nm.success):
            # If nmcli not available, has_ip alone is enough
            logger.info("settle: iface %s ready after %ss (has_ip=%s nm_ok=%s)",
                        iface, round(time.monotonic() - start, 2), has_ip, nm_ok)
            return
        time.sleep(1)
    logger.info("settle: iface %s timeout after %ss", iface, round(time.monotonic() - start, 2))
    # Timeout: don't fail, just proceed to post-check


def _is_ok_or_executed(result: NetResult) -> bool:
    code = result.code
    if isinstance(code, str):
        try:
            code = ResultCode(code)
        except ValueError:
            return False
    return code in (ResultCode.OK, ResultCode.EXECUTED)


@dataclasses.dataclass
class _RepairState:
    """Mutable flow state threaded through the repair phases (N2)."""

    diag: Optional[NetResult] = None
    post: Optional[NetResult] = None
    repairs: List[NetResult] = dataclasses.field(default_factory=list)
    skip_renew: bool = False
    iface: Optional[str] = None


def _pre_diagnose(deps: RepairDeps, callbacks: RepairCallbacks, state: _RepairState) -> None:
    """Step 1: pre-repair diagnostics + skip analysis (never a repair)."""
    callbacks.push_status("Diagnosing...")
    try:
        state.diag = deps.diagnose()
        callbacks.log(state.diag.to_log_entry())
        if state.diag.details:
            callbacks.log(f"  ↳ {state.diag.details}")
    finally:
        callbacks.pop_status()
    # Structured skip check: no gateway => gateway_ok false
    diag = state.diag
    if diag is not None:
        if diag.data and isinstance(diag.data, dict):
            state.skip_renew = not diag.data.get("gateway_ok", False)
            if diag.details and isinstance(diag.details, dict):
                gw = diag.details.get("gateway")
                state.skip_renew = gw in (None, "none") or not diag.details.get("gateway_ok", False)
        else:
            state.skip_renew = "Gateway Not Found" in (diag.message or "")
        try:
            state.iface = deps.default_iface()
        except Exception:
            state.iface = None
    if state.skip_renew:
        callbacks.log("Smart Repair: skipping IP renewal (no default gateway detected).")


def _is_healthy(diag: Optional[NetResult]) -> bool:
    """R4 short-circuit predicate: healthy networks are never elevated."""
    if diag and diag.data and isinstance(diag.data, dict):
        return bool(diag.data.get("gateway_ok") and diag.data.get("dns_ok")
                    and diag.data.get("internet_ok"))
    if diag:
        return diag.code == ResultCode.OK
    return False


def _run_one_action(deps: RepairDeps, callbacks: RepairCallbacks,
                    state: _RepairState, label: str, action: str) -> None:
    callbacks.push_status(label)
    try:
        res = deps.act(action)
        state.repairs.append(res)
        callbacks.log(res.to_log_entry())
        if res.details:
            callbacks.log(f"  ↳ {res.details}")
    finally:
        callbacks.pop_status()


def _do_repairs(deps: RepairDeps, callbacks: RepairCallbacks, state: _RepairState) -> None:
    """Steps 2-3: flush DNS always, renew IP unless the gateway is missing."""
    _run_one_action(deps, callbacks, state, "Flushing DNS...", "flush_dns")
    if not state.skip_renew:
        _run_one_action(deps, callbacks, state, "Renewing IP...", "renew_ip")


def _verify(deps: RepairDeps, callbacks: RepairCallbacks, state: _RepairState) -> None:
    """Step 4: settle, re-diagnose, log post-repair state."""
    callbacks.push_status("Verifying repair...")
    try:
        deps.settle(state.iface, 8)
        state.post = deps.diagnose()
        callbacks.log(f"[Post-Repair] {state.post.to_log_entry()}")
        if state.post.details:
            callbacks.log(f"  ↳ {state.post.details}")
            if isinstance(state.post.details, dict) and state.post.details.get("captive_portal_hint"):
                callbacks.log(f"  ↳ Hint: {state.post.details.get('captive_portal_hint')}")
    finally:
        callbacks.pop_status()


def _verdict_skipped(diag: Optional[NetResult], post: Optional[NetResult]) -> NetResult:
    return NetResult("Smart Repair", False, "SKIPPED — network healthy, nothing to repair",
                     data={"pre": diag.data if diag else None,
                           "post": post.data if post else None},
                     code=ResultCode.SKIPPED)


def _verdict_unverified(repairs_ok: bool, total: int, succeeded: int) -> NetResult:
    # Debug escape hatch only. Never present unverified repairs as OK.
    code = ResultCode.EXECUTED if repairs_ok else ResultCode.FAILED
    return NetResult(
        "Smart Repair", False,
        f"Smart Repair: repairs {succeeded}/{total} executed; "
        "post-repair verification DISABLED "
        "(NETMEDIC_POST_REPAIR_VERIFY=0, debug only). "
        "Re-run with the flag unset before treating this as recovery.",
        data={"pre": None, "post": None, "repairs_ok": repairs_ok},
        code=code,
    )


def _verdict_recovered(pre_ok: bool, total: int, succeeded: int) -> NetResult:
    if not pre_ok:
        summary = f"Smart Repair: SUCCESS (verified) — repairs {succeeded}/{total} ok | pre=FAIL post=OK"
    else:
        summary = f"Smart Repair finished: all {total} repairs succeeded — network still healthy | pre=OK post=OK"
    return NetResult("Smart Repair", True, summary,
                     data={"pre": None, "post": None, "repairs_ok": True},
                     code=ResultCode.OK)


def _verdict_not_recovered(pre_ok: bool, post_ok: bool, total: int, succeeded: int,
                           pre_dns: Any, pre_net: Any,
                           post_dns: Any, post_net: Any) -> NetResult:
    if post_dns and not post_net:
        summary = f"Smart Repair: repairs {succeeded}/{total} executed; network NOT recovered. Gateway OK, WAN down → likely upstream/ISP/captive portal. Suggestions: check router uplink, or run manual probes (MANUAL §Troubleshooting). | pre={'OK' if pre_ok else 'FAIL'} post=FAIL"
        code = ResultCode.PARTIAL
    elif post_dns is False and post_net is False and pre_dns is False and pre_net is False:
        summary = f"Smart Repair: repairs {succeeded}/{total} executed; network NOT recovered. Gateway OK, WAN down → likely upstream/ISP/captive portal. | pre=FAIL post=FAIL"
        code = ResultCode.FAILED
    elif not pre_ok and post_ok is False:
        summary = f"Smart Repair: repairs {succeeded}/{total} ok — network still down (upstream outage suspected) | pre=FAIL post=FAIL"
        code = ResultCode.FAILED
    else:
        summary = f"Smart Repair: repairs {succeeded}/{total} ok — new fault detected post-repair | pre={'OK' if pre_ok else 'FAIL'} post=FAIL"
        code = ResultCode.FAILED
    return NetResult("Smart Repair", False, summary,
                     data={"pre": None, "post": None, "repairs_ok": True},
                     code=code)


def _verdict_repairs_failed(pre_ok: bool, post_ok: bool, total: int, succeeded: int) -> NetResult:
    return NetResult(
        "Smart Repair", False,
        f"Smart Repair: repairs {succeeded}/{total} succeeded — review log for failures | pre={'OK' if pre_ok else 'FAIL'} post={'OK' if post_ok else 'FAIL'}",
        data={"pre": None, "post": None, "repairs_ok": False},
        code=ResultCode.FAILED,
    )


@dataclasses.dataclass(frozen=True)
class _VerdictInputs:
    """Precomputed verdict inputs (keeps _compute_verdict branch-flat)."""

    repairs_ok: bool
    total: int
    succeeded: int
    pre_ok: bool
    post_ok: bool
    pre_dns: Any
    pre_net: Any
    post_dns: Any
    post_net: Any


def _gather_inputs(state: _RepairState) -> _VerdictInputs:
    repairs_ok = all(_is_ok_or_executed(r) for r in state.repairs) if state.repairs else True
    pre_data: Dict[str, Any] = state.diag.data if state.diag and isinstance(state.diag.data, dict) else {}
    post_data: Dict[str, Any] = state.post.data if state.post and isinstance(state.post.data, dict) else {}
    return _VerdictInputs(
        repairs_ok=repairs_ok,
        total=len(state.repairs),
        succeeded=sum(1 for r in state.repairs if _is_ok_or_executed(r)),
        pre_ok=bool(state.diag and state.diag.code and state.diag.code == ResultCode.OK),
        post_ok=bool(state.post and state.post.code and state.post.code == ResultCode.OK),
        pre_dns=pre_data.get("dns_ok"),
        pre_net=pre_data.get("internet_ok"),
        post_dns=post_data.get("dns_ok"),
        post_net=post_data.get("internet_ok"),
    )


def _compute_verdict(do_verify: bool, state: _RepairState) -> NetResult:
    """Delta verdict — code-driven; pre/post data attached by the caller."""
    inputs = _gather_inputs(state)
    if not do_verify:
        result = _verdict_unverified(inputs.repairs_ok, inputs.total, inputs.succeeded)
    elif inputs.repairs_ok and inputs.post_ok:
        result = _verdict_recovered(inputs.pre_ok, inputs.total, inputs.succeeded)
    elif inputs.repairs_ok:
        result = _verdict_not_recovered(
            inputs.pre_ok, inputs.post_ok, inputs.total, inputs.succeeded,
            inputs.pre_dns, inputs.pre_net, inputs.post_dns, inputs.post_net)
    else:
        result = _verdict_repairs_failed(inputs.pre_ok, inputs.post_ok,
                                         inputs.total, inputs.succeeded)
    # Attach pre/post snapshots (kept here so phase helpers stay small).
    # overall derives from code (never read result.success: narrowed shim).
    code = result.code if isinstance(result.code, ResultCode) else ResultCode(result.code)
    return NetResult(result.operation, code == ResultCode.OK, result.message,
                     data={"pre": state.diag.data if state.diag else None,
                           "post": state.post.data if state.post else None,
                           "repairs_ok": inputs.repairs_ok},
                     code=code)


def run_smart_repair(deps: RepairDeps, callbacks: RepairCallbacks) -> NetResult:
    """Run the Smart Repair sequence; return the delta verdict.

    Contract (VERBS.md §5): pre-diagnosis never counts as a repair;
    standalone flush-dns stays EXECUTED; the verdict compares pre/post.
    Sequencing shell over the _pre_diagnose/_do_repairs/_verify/_verdict
    phases so no single function exceeds reviewable size (N2).
    """
    log = callbacks.log
    log("--- Starting Smart Repair ---")
    state = _RepairState()
    _pre_diagnose(deps, callbacks, state)
    if _is_healthy(state.diag):
        log("Smart Repair: network healthy, nothing to repair — skipped privileged actions.")
        post: Optional[NetResult] = None
        if deps.verify:
            callbacks.push_status("Verifying repair...")
            try:
                post = deps.diagnose()
                log(f"[Post-Repair] {post.to_log_entry()}")
            finally:
                callbacks.pop_status()
        return _verdict_skipped(state.diag, post)
    _do_repairs(deps, callbacks, state)
    if deps.verify:
        _verify(deps, callbacks, state)
    return _compute_verdict(deps.verify, state)
