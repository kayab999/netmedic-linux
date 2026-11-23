"""Native (stdlib) topology collectors for L0 diagnostics.

All collectors accept injectable roots so tests can use temporary fixtures
instead of the live /proc and /sys. Missing or unreadable sources yield
empty results; they never raise. IPv4 addresses are not collected here
faithfully without rtnetlink and are deliberately left to Phase 5.
"""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Any, Dict, List

_IFACE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_iface_name(name: str) -> bool:
    return bool(name) and ".." not in name and _IFACE_NAME_RE.fullmatch(name) is not None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def collect_interfaces(sys_root: Path = Path("/sys")) -> List[Dict[str, Any]]:
    """Collect interface name, state, MAC, MTU and a coarse kind hint."""
    base = sys_root / "class" / "net"
    result: List[Dict[str, Any]] = []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return result
    for entry in entries:
        name = entry.name
        if not _safe_iface_name(name):
            continue
        # Refuse to follow symlinks that escape the sys root.
        try:
            resolved = entry.resolve(strict=False)
            if not str(resolved).startswith(str(sys_root.resolve())):
                continue
        except (OSError, RuntimeError):
            continue
        operstate = _read_text(entry / "operstate").strip() or "unknown"
        address = _read_text(entry / "address").strip()
        mtu_raw = _read_text(entry / "mtu").strip()
        try:
            mtu = int(mtu_raw)
        except ValueError:
            mtu = None
        # Heuristic kind hint only; not a conclusive hardware identification.
        kind = "virtual"
        try:
            if (entry / "device").exists():
                kind = "physical?"
        except OSError:
            kind = "unknown"
        result.append(
            {
                "name": name,
                "state": operstate,
                "mac": address or None,
                "mtu": mtu,
                "kind_hint": kind,
            }
        )
    return result


def collect_ipv6_addresses(proc_root: Path = Path("/proc")) -> Dict[str, List[str]]:
    """Collect IPv6 addresses per interface from /proc/net/if_inet6."""
    path = proc_root / "net" / "if_inet6"
    result: Dict[str, List[str]] = {}
    for line in _read_text(path).splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        addr_hex, _idx, plen, _scope, _flags, iface = parts[:6]
        if not _safe_iface_name(iface):
            continue
        try:
            addr = str(ipaddress.IPv6Address(int(addr_hex, 16)))
        except ValueError:
            continue
        plen_int = int(plen, 16)
        cidr = f"{addr}/{plen_int}"
        result.setdefault(iface, []).append(cidr)
    return result


def _hex_to_ipv4(value: str) -> str:
    # /proc/net/route stores IPv4 in little-endian hex.
    try:
        n = int(value, 16)
    except ValueError:
        return ""
    return ".".join(str((n >> (8 * i)) & 0xFF) for i in range(4))


def collect_default_gateways_v4(proc_root: Path = Path("/proc")) -> List[Dict[str, Any]]:
    """Default IPv4 routes from /proc/net/route, sorted by metric."""
    path = proc_root / "net" / "route"
    routes: List[Dict[str, Any]] = []
    for line in _read_text(path).splitlines():
        cols = line.split()
        if len(cols) < 8 or cols[0] == "Iface":
            continue
        iface, dest, gateway, flags, _refcnt, _use, metric, mask = cols[:8]
        if not _safe_iface_name(iface):
            continue
        if dest != "00000000" or mask != "00000000":
            continue
        # Flag 0x0002 (RTF_GATEWAY) indicates a gateway; 0x0001 (RTF_UP) required.
        try:
            flags_int = int(flags, 16)
            metric_int = int(metric)
        except ValueError:
            continue
        if not (flags_int & 0x0001):
            continue
        gw = _hex_to_ipv4(gateway) if (flags_int & 0x0002) else None
        routes.append({"iface": iface, "gateway": gw, "metric": metric_int, "flags": flags_int})
    routes.sort(key=lambda r: r["metric"])
    return routes


def collect_default_gateways_v6(proc_root: Path = Path("/proc")) -> List[Dict[str, Any]]:
    """Default IPv6 routes from /proc/net/ipv6_route."""
    path = proc_root / "net" / "ipv6_route"
    routes: List[Dict[str, Any]] = []
    for line in _read_text(path).splitlines():
        cols = line.split()
        # dest(32) plen src(32) srcplen next_hop(32) metric refcnt use flags ... iface
        if len(cols) < 10:
            continue
        dest, plen = cols[0], cols[1]
        next_hop = cols[4]
        metric = cols[5]
        iface = cols[-1]
        if not _safe_iface_name(iface):
            continue
        if dest != "0" * 32 or plen != "00":
            continue
        try:
            metric_int = int(metric, 16)
        except ValueError:
            try:
                metric_int = int(metric)
            except ValueError:
                metric_int = 0
        gateway = None
        if next_hop != "0" * 32:
            try:
                chunks = [next_hop[i : i + 4] for i in range(0, 32, 4)]
                gateway = ":".join(format(int(chunk, 16), "x") for chunk in chunks)
            except ValueError:
                gateway = None
        routes.append({"iface": iface, "gateway": gateway, "metric": metric_int})
    routes.sort(key=lambda r: r["metric"])
    return routes


def collect_mtu(sys_root: Path = Path("/sys"), iface: str = "") -> int | None:
    """Read MTU for a single interface; None if unavailable/invalid."""
    if not _safe_iface_name(iface):
        return None
    raw = _read_text(sys_root / "class" / "net" / iface / "mtu").strip()
    try:
        value = int(raw)
    except ValueError:
        return None
    if value < 0:
        return None
    return value