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


def run_smart_repair(deps: RepairDeps, callbacks: RepairCallbacks) -> NetResult:
    """Run the Smart Repair sequence; return the delta verdict.

    Contract (VERBS.md §5): pre-diagnosis never counts as a repair;
    standalone flush-dns stays EXECUTED; the verdict compares pre/post.
    """
    log, push, pop = callbacks.log, callbacks.push_status, callbacks.pop_status
    do_verify = deps.verify
    log("--- Starting Smart Repair ---")
    repair_repairs: List[NetResult] = []
    diag_res: Optional[NetResult] = None

    # Step 1: pre-repair diagnostics (informational, not counted as repair)
    push("Diagnosing...")
    try:
        diag_res = deps.diagnose()
        log(diag_res.to_log_entry())
        if diag_res.details:
            log(f"  ↳ {diag_res.details}")
    finally:
        pop()

    # Structured skip check: no gateway => gateway_ok false
    skip_renew = False
    iface_for_settle: Optional[str] = None
    if diag_res is not None:
        if diag_res.data and isinstance(diag_res.data, dict):
            skip_renew = not diag_res.data.get("gateway_ok", False)
            if diag_res.details and isinstance(diag_res.details, dict):
                gw = diag_res.details.get("gateway")
                skip_renew = gw in (None, "none") or not diag_res.details.get("gateway_ok", False)
        else:
            skip_renew = "Gateway Not Found" in (diag_res.message or "")
        try:
            iface_for_settle = deps.default_iface()
        except Exception:
            iface_for_settle = None
    if skip_renew:
        log("Smart Repair: skipping IP renewal (no default gateway detected).")

    # R4 short-circuit: if network already healthy, don't elevate
    is_healthy = False
    if diag_res and diag_res.data and isinstance(diag_res.data, dict):
        is_healthy = bool(diag_res.data.get("gateway_ok") and diag_res.data.get("dns_ok")
                          and diag_res.data.get("internet_ok"))
    elif diag_res:
        is_healthy = diag_res.code == ResultCode.OK
    if is_healthy:
        log("Smart Repair: network healthy, nothing to repair — skipped privileged actions.")
        post_res: Optional[NetResult] = None
        if do_verify:
            push("Verifying repair...")
            try:
                post_res = deps.diagnose()
                log(f"[Post-Repair] {post_res.to_log_entry()}")
            finally:
                pop()
        return NetResult("Smart Repair", False, "SKIPPED — network healthy, nothing to repair",
                         data={"pre": diag_res.data if diag_res else None,
                               "post": post_res.data if post_res else None},
                         code=ResultCode.SKIPPED)

    # Step 2: flush DNS (always) — EXECUTED expected
    push("Flushing DNS...")
    try:
        res = deps.act("flush_dns")
        repair_repairs.append(res)
        log(res.to_log_entry())
        if res.details:
            log(f"  ↳ {res.details}")
    finally:
        pop()

    # Step 3: renew IP (conditionally)
    if not skip_renew:
        push("Renewing IP...")
        try:
            res = deps.act("renew_ip")
            repair_repairs.append(res)
            log(res.to_log_entry())
            if res.details:
                log(f"  ↳ {res.details}")
        finally:
            pop()

    # Step 4: post-repair verification
    post_res = None
    if do_verify:
        push("Verifying repair...")
        try:
            deps.settle(iface_for_settle, 8)
            post_res = deps.diagnose()
            log(f"[Post-Repair] {post_res.to_log_entry()}")
            if post_res.details:
                log(f"  ↳ {post_res.details}")
                if isinstance(post_res.details, dict) and post_res.details.get("captive_portal_hint"):
                    log(f"  ↳ Hint: {post_res.details.get('captive_portal_hint')}")
        finally:
            pop()

    # Delta verdict — code-driven
    repairs_ok = all(_is_ok_or_executed(r) for r in repair_repairs) if repair_repairs else True
    repairs_total = len(repair_repairs)
    repairs_succeeded = sum(1 for r in repair_repairs if _is_ok_or_executed(r))
    pre_ok = bool(diag_res and diag_res.code and diag_res.code == ResultCode.OK)
    post_ok = bool(post_res and post_res.code and post_res.code == ResultCode.OK)
    pre_data: Dict[str, Any] = diag_res.data if diag_res and isinstance(diag_res.data, dict) else {}
    post_data: Dict[str, Any] = post_res.data if post_res and isinstance(post_res.data, dict) else {}
    pre_dns, pre_net = pre_data.get("dns_ok"), pre_data.get("internet_ok")
    post_dns, post_net = post_data.get("dns_ok"), post_data.get("internet_ok")
    if not do_verify:
        # Debug escape hatch only. Never present unverified repairs as OK.
        overall_code = ResultCode.EXECUTED if repairs_ok else ResultCode.FAILED
        summary = (
            f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} executed; "
            "post-repair verification DISABLED "
            "(NETMEDIC_POST_REPAIR_VERIFY=0, debug only). "
            "Re-run with the flag unset before treating this as recovery."
        )
        overall = False
    elif repairs_ok and post_ok:
        if not pre_ok:
            summary = f"Smart Repair: SUCCESS (verified) — repairs {repairs_succeeded}/{repairs_total} ok | pre=FAIL post=OK"
        else:
            summary = f"Smart Repair finished: all {repairs_total} repairs succeeded — network still healthy | pre=OK post=OK"
        overall = True
        overall_code = ResultCode.OK
    elif repairs_ok and not post_ok:
        if post_dns and not post_net:
            summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} executed; network NOT recovered. Gateway OK, WAN down → likely upstream/ISP/captive portal. Suggestions: check router uplink, or run manual probes (MANUAL §Troubleshooting). | pre={'OK' if pre_ok else 'FAIL'} post=FAIL"
            overall_code = ResultCode.PARTIAL
        elif post_dns is False and post_net is False and pre_dns is False and pre_net is False:
            summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} executed; network NOT recovered. Gateway OK, WAN down → likely upstream/ISP/captive portal. | pre=FAIL post=FAIL"
            overall_code = ResultCode.FAILED
        elif not pre_ok and post_ok is False:
            summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} ok — network still down (upstream outage suspected) | pre=FAIL post=FAIL"
            overall_code = ResultCode.FAILED
        else:
            summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} ok — new fault detected post-repair | pre={'OK' if pre_ok else 'FAIL'} post=FAIL"
            overall_code = ResultCode.FAILED
        overall = False
    else:
        summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} succeeded — review log for failures | pre={'OK' if pre_ok else 'FAIL'} post={'OK' if post_ok else 'FAIL'}"
        overall = False
        overall_code = ResultCode.FAILED
    return NetResult("Smart Repair", overall, summary,
                     data={"pre": diag_res.data if diag_res else None,
                           "post": post_res.data if post_res else None,
                           "repairs_ok": repairs_ok},
                     code=overall_code)
