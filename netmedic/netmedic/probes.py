"""Shared network probes (single source of truth for DIV-01).
Used by network.py diagnostics and sensors.get_network_snapshot().
"""
from __future__ import annotations

import concurrent.futures
import socket
import threading
from typing import Any, Dict, Tuple

from netmedic.system import CommandRunner

_DNS_HOSTS = ("google.com", "cloudflare.com")
_DNS_TIMEOUT = 5.0


def _dns_reason(exc: BaseException) -> str:
    if isinstance(exc, concurrent.futures.TimeoutError):
        return "timeout"
    if isinstance(exc, socket.gaierror):
        errno = getattr(exc, "errno", None)
        if errno == socket.EAI_NONAME:
            return "eai_noname"
        if errno == socket.EAI_AGAIN:
            return "eai_again"
        if errno == socket.EAI_FAIL:
            return "eai_fail"
        if errno == socket.EAI_SERVICE:
            return "eai_service"
        if errno == socket.EAI_FAMILY:
            return "eai_family"
        if errno == socket.EAI_SOCKTYPE:
            return "eai_socktype"
        return "gai_error"
    if isinstance(exc, socket.timeout):
        return "timeout"
    return "resolution_error"


def _resolve_host(host: str, timeout: float) -> Tuple[str, Dict[str, Any]]:
    """Resolve one host with the system resolver (NSS), bounded by ``timeout``."""
    result: Dict[str, Any] = {
        "success": False,
        "addresses": [],
        "families": [],
        "reason_code": None,
    }
    holder: Dict[str, Any] = {"infos": None, "exc": None}

    def worker() -> None:
        try:
            holder["infos"] = socket.getaddrinfo(host, None)
        except BaseException as exc:  # noqa: BLE001 - probe must not raise
            holder["exc"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        result["reason_code"] = "timeout"
        return host, result

    if holder["exc"] is not None:
        result["reason_code"] = _dns_reason(holder["exc"])
        return host, result

    infos = holder["infos"] or []
    addresses: list[str] = []
    families: set[str] = set()
    for family, _type, _proto, _canon, sockaddr in infos or []:
        try:
            address = sockaddr[0]
        except (IndexError, TypeError):
            continue
        if address and address not in addresses:
            addresses.append(address)
        if family == socket.AF_INET:
            families.add("ipv4")
        elif family == socket.AF_INET6:
            families.add("ipv6")
        else:
            families.add(str(family))

    result["success"] = bool(addresses)
    result["addresses"] = addresses[:8]
    result["families"] = sorted(families)
    if not result["success"]:
        result["reason_code"] = "no_addresses"
    return host, result


def check_dns_resolution_detailed() -> Tuple[bool, Dict[str, Dict[str, Any]], str]:
    """Native (stdlib) system name resolution.

    Returns ``(overall_ok, per_host, successful_host)`` where ``per_host`` maps
    each host to ``{success, addresses, families, reason_code}``. A real
    negative result (EAI_NONAME/EAI_AGAIN) is reported as such; it never
    triggers a fallback to another tool.
    """
    per: Dict[str, Dict[str, Any]] = {}
    ok_host = ""
    for host in _DNS_HOSTS:
        _host, info = _resolve_host(host, _DNS_TIMEOUT)
        per[_host] = info
        if info["success"] and not ok_host:
            ok_host = _host
    overall = any(info.get("success") for info in per.values())
    return overall, per, ok_host


def check_dns_resolution() -> Tuple[bool, Dict[str, bool], str]:
    """Compatibility wrapper around :func:`check_dns_resolution_detailed`."""
    overall, detailed, ok_host = check_dns_resolution_detailed()
    per = {host: bool(info.get("success")) for host, info in detailed.items()}
    return overall, per, ok_host


def _probe_target(cmd):
    res = CommandRunner.run(cmd, timeout=5)
    return res.success, res


def check_internet_access() -> Tuple[bool, Dict[str, bool], str]:
    """Probe internet in parallel: two http + https fallback + icmp.

    overall_ok is TCP/HTTPS only (R1). ICMP is recorded in per_target for
    PARTIAL diagnostics and must not count as internet_ok.
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
    # icmp: details only — a ping does not mean the user has internet (R1)
    ping = CommandRunner.run(["ping", "-c", "1", "-W", "2", "8.8.8.8"])
    per["8.8.8.8:icmp"] = ping.success
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
    return check_portal_at_url(_portal_url())


def _portal_url() -> str:
    """Captive-portal 204 endpoint; overridable (privacy) via NETMEDIC_PORTAL_URL."""
    import os

    return os.environ.get(
        "NETMEDIC_PORTAL_URL", "http://connectivity-check.ubuntu.com"
    )


def check_portal_at_url(url: str) -> Tuple[bool, str]:
    """True when `url` answers like a captive portal (redirect/200 instead of 204)."""
    res = CommandRunner.run(["curl", "-Is", "--connect-timeout", "3", url], timeout=5)
    if not res.success:
        return False, "portal probe failed"
    out = (res.stdout or "") + "\n" + (res.stderr or "")
    # Ubuntu check returns 204 when not captive, 302/200 when captive
    if "204" in out or "No Content" in out:
        return False, "no portal (204)"
    if "302" in out or "Location:" in out:
        return True, "possible captive portal (redirect detected)"
    return False, "portal check ambiguous"
