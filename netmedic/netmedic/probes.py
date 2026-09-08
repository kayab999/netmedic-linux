"""Shared network probes (single source of truth for DIV-01).
Used by network.py diagnostics and sensors.get_network_snapshot().
"""
from __future__ import annotations

import concurrent.futures
from typing import Dict, Tuple

from netmedic.system import CommandRunner


def check_dns_resolution() -> Tuple[bool, Dict[str, bool], str]:
    """Probe DNS with two hosts. Returns (overall_ok, per_host, successful_host)."""
    hosts = ["google.com", "cloudflare.com"]
    per = {}
    ok_host = ""
    for h in hosts:
        res = CommandRunner.run(["getent", "hosts", h])
        per[h] = res.success
        if res.success and not ok_host:
            ok_host = h
    overall = any(per.values())
    return overall, per, ok_host


def _probe_target(cmd):
    res = CommandRunner.run(cmd, timeout=5)
    return res.success, res


def check_internet_access() -> Tuple[bool, Dict[str, bool], str]:
    """Probe internet in parallel: two http + https fallback + icmp.
    Returns (overall_ok, per_target dict, successful_label or details string).
    """
    targets = {
        "1.1.1.1:80": ["curl", "-Is", "--connect-timeout", "3", "http://1.1.1.1"],
        "8.8.8.8:80": ["curl", "-Is", "--connect-timeout", "3", "http://8.8.8.8"],
    }
    per: Dict[str, bool] = {}
    successful = ""
    # Parallel http probes
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(_probe_target, cmd): label for label, cmd in targets.items()}
        for fut in concurrent.futures.as_completed(futs):
            label = futs[fut]
            try:
                ok, res = fut.result()
            except Exception:
                ok = False
            per[label] = ok
            if ok and not successful:
                successful = label
    if successful:
        return True, per, successful
    # https fallback
    https_cmd = ["curl", "-Is", "--connect-timeout", "3", "https://1.1.1.1"]
    ok, _ = _probe_target(https_cmd)
    per["1.1.1.1:443"] = ok
    if ok:
        return True, per, "1.1.1.1:443 (port 80 blocked hint)"
    # icmp fallback
    ping = CommandRunner.run(["ping", "-c", "1", "-W", "2", "8.8.8.8"])
    per["8.8.8.8:icmp"] = ping.success
    if ping.success:
        return True, per, "8.8.8.8:icmp"
    # Build details string for diagnostics
    details = ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in per.items())
    return False, per, details


def check_nm_connectivity() -> Tuple[bool | None, str]:
    """NM second-opinion (L1). Returns (is_full|None, details). None = skipped/absent."""
    import os
    if os.environ.get("NETMEDIC_SIM_NS"):
        return None, "skipped in netns (host NM not visible via rtnetlink, per-netns)"
    # Use terse output to avoid i18n parsing
    res = CommandRunner.run(["nmcli", "-t", "-f", "CONNECTIVITY", "networking", "connectivity"], timeout=5)
    if not res.success:
        # Try alternative syntax
        res = CommandRunner.run(["nmcli", "networking", "connectivity", "check"], timeout=5)
        if not res.success:
            return None, f"nm check absent/disabled ({res.stderr or res.stdout or 'no output'})"
    out = (res.stdout or "").strip().lower()
    if "full" in out:
        return True, "nm: full"
    if "limited" in out or "portal" in out:
        return False, f"nm: {out} (portal/limited)"
    if "none" in out:
        return False, "nm: none"
    return None, f"nm: {out or 'unknown'}"


def check_captive_portal() -> Tuple[bool, str]:
    """If gateway OK but WAN fail, check connectivity-check.ubuntu.com for redirect."""
    # Use curl -s http://connectivity-check.ubuntu.com (expects 204 no-content)
    res = CommandRunner.run(["curl", "-Is", "--connect-timeout", "3", "http://connectivity-check.ubuntu.com"], timeout=5)
    if not res.success:
        return False, "portal probe failed"
    out = (res.stdout or "") + "\n" + (res.stderr or "")
    # Ubuntu check returns 204 when not captive, 302/200 when captive
    if "204" in out or "No Content" in out:
        return False, "no portal (204)"
    if "302" in out or "Location:" in out:
        return True, "possible captive portal (redirect detected)"
    return False, "portal check ambiguous"
