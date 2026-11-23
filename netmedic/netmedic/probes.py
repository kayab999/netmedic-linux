"""Shared network probes (single source of truth for DIV-01).
Used by network.py diagnostics and sensors.get_network_snapshot().
"""
from __future__ import annotations

import concurrent.futures
import http.client
import socket
import ssl
import threading
import time
import urllib.parse
from typing import Any, Dict, Optional, Tuple

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


_TCP_TARGETS = (("1.1.1.1", 80), ("8.8.8.8", 80), ("1.1.1.1", 443))
_TCP_TIMEOUT = 3.0


def _tcp_probe(host: str, port: int, timeout: float) -> Tuple[bool, float | None, str | None]:
    """Native TCP connect probe with monotonic RTT measurement."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            rtt_ms = (time.monotonic() - start) * 1000.0
            return True, rtt_ms, None
    except (socket.timeout, TimeoutError):
        return False, None, "timeout"
    except ConnectionRefusedError:
        return False, None, "refused"
    except OSError as exc:
        return False, None, f"unreachable:{exc.errno}" if exc.errno is not None else "unreachable"


def check_tcp_connectivity_detailed() -> Tuple[bool, Dict[str, Dict[str, Any]], str]:
    """Native TCP connectivity (no curl). Returns RTT and classification."""
    per: Dict[str, Dict[str, Any]] = {}
    successful = ""
    for host, port in _TCP_TARGETS:
        label = f"{host}:{port}"
        ok, rtt_ms, error = _tcp_probe(host, port, _TCP_TIMEOUT)
        per[label] = {"success": ok, "rtt_ms": rtt_ms, "error": error}
        if ok and not successful:
            successful = label
    overall = bool(successful)
    return overall, per, successful


def check_tcp_connectivity() -> Tuple[bool, Dict[str, bool], str]:
    overall, detailed, successful = check_tcp_connectivity_detailed()
    per = {label: bool(info.get("success")) for label, info in detailed.items()}
    return overall, per, successful


def check_internet_access() -> Tuple[bool, Dict[str, bool], str]:
    """Probe internet via native TCP connects (R1: TCP only, no HTTP claim).

    overall_ok is TCP reachability only. ICMP is recorded in per_target for
    PARTIAL diagnostics and must not count as internet_ok. RTT/detail live in
    check_tcp_connectivity_detailed().
    """
    overall, detailed, successful = check_tcp_connectivity_detailed()
    per: Dict[str, bool] = {
        label: bool(info.get("success")) for label, info in detailed.items()
    }
    if successful:
        return True, per, successful
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


def check_http_access(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Native HTTP/HTTPS probe with TLS validation (never CERT_NONE)."""
    return _http_probe(url, timeout=timeout)


def check_http_tls_access(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Alias for :func:`check_http_access` (HTTP/TLS capability)."""
    return _http_probe(url, timeout=timeout)


def _http_probe(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Bounded stdlib HTTP probe. Does not follow redirects automatically."""
    result: Dict[str, Any] = {
        "tcp_ok": False,
        "http_ok": False,
        "tls_ok": None,
        "status": None,
        "headers": {},
        "body": "",
        "error": None,
        "reason_code": None,
    }
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        result["error"] = str(exc)
        result["reason_code"] = "invalid_url"
        return result
    scheme = (parsed.scheme or "http").lower()
    host = parsed.hostname
    if not host:
        result["error"] = "missing host"
        result["reason_code"] = "invalid_url"
        return result
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    use_tls = scheme == "https"
    if use_tls:
        result["tls_ok"] = False

    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except (socket.timeout, TimeoutError):
        result["error"] = "timeout"
        result["reason_code"] = "timeout"
        return result
    except OSError as exc:
        result["error"] = str(exc)
        result["reason_code"] = "tcp_error"
        return result

    result["tcp_ok"] = True
    wrapped = sock
    if use_tls:
        try:
            context = ssl.create_default_context()
            wrapped = context.wrap_socket(sock, server_hostname=host)
            result["tls_ok"] = True
        except (ssl.SSLError, OSError) as exc:
            result["error"] = str(exc)
            result["reason_code"] = "tls_error"
            try:
                sock.close()
            except OSError:
                pass
            return result

    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    conn.sock = wrapped
    try:
        conn.request(
            "GET",
            path,
            headers={"Host": host, "Connection": "close", "User-Agent": "NetMedic"},
        )
        response = conn.getresponse()
        body = response.read(4096)
        result["status"] = response.status
        result["headers"] = {k: v for k, v in response.getheaders()}
        try:
            result["body"] = body.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            result["body"] = ""
        result["http_ok"] = True
        result["reason_code"] = "ok"
    except (http.client.HTTPException, OSError, TimeoutError) as exc:
        result["error"] = str(exc)
        result["reason_code"] = "http_error"
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        if wrapped is not sock:
            try:
                wrapped.close()
            except OSError:
                pass
        else:
            try:
                sock.close()
            except OSError:
                pass
    return result


def check_captive_portal() -> Tuple[Optional[bool], str]:
    """Return (portal_detected, detail). None means the probe was inconclusive."""
    return check_portal_at_url(_portal_url())


def _portal_url() -> str:
    """Captive-portal endpoint; overridable (privacy) via NETMEDIC_PORTAL_URL."""
    import os

    return os.environ.get(
        "NETMEDIC_PORTAL_URL", "http://nmcheck.gnome.org/check_network_status.txt"
    )


def check_portal_at_url(url: str) -> Tuple[Optional[bool], str]:
    """Native captive-portal detection. Redirects are not followed."""
    probe = _http_probe(url, timeout=5.0)
    if probe["status"] is None:
        return None, f"unknown: {probe['error'] or 'no response'}"
    status = probe["status"]
    headers = {str(k).lower(): str(v) for k, v in (probe["headers"] or {}).items()}
    body = probe["body"] or ""
    if "location" in headers or status in (301, 302, 303, 307, 308):
        return True, "possible captive portal (redirect detected)"
    if status == 204:
        return False, "no portal (204)"
    if status == 200 and "NetworkManager is online" in body:
        return False, "no portal (200)"
    if status == 200:
        return None, "unknown: unexpected 200 body"
    return None, f"unknown: HTTP {status}"
