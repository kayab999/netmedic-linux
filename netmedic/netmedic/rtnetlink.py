"""Minimal stdlib rtnetlink client (read-only).

Scope (Phase 5) is intentionally limited to:
  * enumerating links,
  * enumerating IPv4/IPv6 addresses,
  * obtaining IPv4/IPv6 default routes.

No interface/route/address creation or modification is performed. Any
inconclusive or failed collection returns None so callers can fall back to
/proc and /sys without a false negative.
"""
from __future__ import annotations

import os
import socket
import struct
from typing import Any, Dict, List, Optional

NETLINK_ROUTE = 0
RTM_GETLINK = 18
RTM_GETADDR = 22
RTM_GETROUTE = 26
RTM_NEWLINK = 16
RTM_NEWADDR = 20
RTM_NEWROUTE = 24
NLM_F_REQUEST = 0x01
NLM_F_DUMP = 0x300  # ROOT | MATCH
NLM_F_MULTI = 0x02
NLMSG_NOOP = 1
NLMSG_ERROR = 2
NLMSG_DONE = 3
NLMSG_OVERRUN = 4

RTN_UNICAST = 1
RT_TABLE_MAIN = 254

IFLA_IFNAME = 3
IFLA_MTU = 4
IFLA_ADDRESS = 1
IFLA_OPERSTATE = 16

IFA_ADDRESS = 1
IFA_LOCAL = 2
IFA_LABEL = 4

RTA_DST = 1
RTA_OIF = 4
RTA_GATEWAY = 5
RTA_PRIORITY = 6
RTA_TABLE = 15

AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6
AF_UNSPEC = 0

_MAX_MSG = 256 * 1024
_TIMEOUT = 2.0


def _align4(n: int) -> int:
    return (n + 3) & ~3


def _safe_iface(name: str) -> bool:
    import re

    return bool(name) and ".." not in name and re.fullmatch(r"[A-Za-z0-9._-]+", name) is not None


def _recv_dump(sock: socket.socket, seq: int, pid: int) -> Optional[List[bytes]]:
    """Receive a (possibly multipart) dump. Returns list of message payloads or None."""
    chunks: List[bytes] = []
    sock.settimeout(_TIMEOUT)
    try:
        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                return None
            if not data:
                return None
            offset = 0
            total = len(data)
            # Data may contain multiple nlmsghdr in one recv.
            while offset < total:
                if offset + 16 > total:
                    return None
                nlmsg_len, nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid = struct.unpack_from(
                    "IHHII", data, offset
                )
                if nlmsg_len < 16 or offset + nlmsg_len > total:
                    return None
                if nlmsg_seq != seq:
                    # Not our response; ignore this datagram.
                    return None
                if nlmsg_pid != 0 and nlmsg_pid != pid:
                    return None
                payload = data[offset + 16 : offset + nlmsg_len]
                if nlmsg_type == NLMSG_ERROR:
                    # struct nlmsgerr: error (i32) + original header.
                    if len(payload) < 4:
                        return None
                    err = struct.unpack_from("i", payload, 0)[0]
                    if err != 0:
                        return None
                    # ACK with error 0: treat as end.
                    return chunks if chunks else []
                if nlmsg_type == NLMSG_DONE:
                    return chunks
                if nlmsg_type == NLMSG_NOOP:
                    offset += _align4(nlmsg_len)
                    continue
                if nlmsg_type == NLMSG_OVERRUN:
                    return None
                chunks.append(data[offset : offset + nlmsg_len])
                offset += _align4(nlmsg_len)
                if not (nlmsg_flags & NLM_F_MULTI):
                    # Single (non-multipart) response.
                    return chunks
    except (OSError, ValueError):
        return None


def _send_dump_request(sock_type: int, family: int, extra_payload: bytes = b"") -> Optional[List[bytes]]:
    try:
        sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_ROUTE)
    except OSError:
        return None
    try:
        sock.settimeout(_TIMEOUT)
        try:
            sock.bind((os.getpid(), 0))
        except OSError:
            return None
        seq = 1
        pid = os.getpid()
        # Build nlmsghdr + payload.
        nlmsg_len = 16 + len(extra_payload)
        header = struct.pack("IHHII", nlmsg_len, sock_type, NLM_F_REQUEST | NLM_F_DUMP, seq, pid)
        msg = header + extra_payload
        try:
            sock.sendall(msg)
        except OSError:
            return None
        return _recv_dump(sock, seq, pid)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _parse_attrs(data: bytes, off: int) -> Dict[int, bytes]:
    attrs: Dict[int, bytes] = {}
    n = len(data)
    while off + 4 <= n:
        rta_len, rta_type = struct.unpack_from("HH", data, off)
        if rta_len < 4 or off + rta_len > n:
            break
        attrs[rta_type] = data[off + 4 : off + rta_len]
        off += _align4(rta_len)
    return attrs


def _ifname_from_attrs(attrs: Dict[int, bytes]) -> str:
    raw = attrs.get(IFLA_IFNAME, b"")
    if not raw:
        return ""
    # null-terminated
    idx = raw.find(b"\x00")
    if idx >= 0:
        raw = raw[:idx]
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def collect_links(timeout: float = _TIMEOUT) -> Optional[List[Dict[str, Any]]]:
    """Enumerate network links via rtnetlink."""
    # ifinfomsg: family(u8) pad(u8) type(u16) index(i32) flags(u32) change(u32)
    payload = struct.pack("BBHiii", 0, 0, 0, 0, 0, 0)
    msgs = _send_dump_request(RTM_GETLINK, 0, payload)
    if msgs is None:
        return None
    result: List[Dict[str, Any]] = []
    for msg in msgs:
        if len(msg) < 16:
            continue
        nlmsg_len, nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid = struct.unpack_from("IHHII", msg, 0)
        if nlmsg_type != RTM_NEWLINK:
            continue
        body = msg[16:]
        if len(body) < 16:
            continue
        family, pad, if_type, if_index, if_flags, if_change = struct.unpack_from("BBHiii", body, 0)
        attrs = _parse_attrs(body, 16)
        name = _ifname_from_attrs(attrs)
        if not _safe_iface(name):
            name = f"if{if_index}"
        mtu = None
        mtu_raw = attrs.get(IFLA_MTU)
        if mtu_raw is not None and len(mtu_raw) >= 4:
            mtu = struct.unpack_from("I", mtu_raw, 0)[0]
        operstate = None
        os_raw = attrs.get(IFLA_OPERSTATE)
        if os_raw is not None and len(os_raw) >= 1:
            operstate = os_raw[0]
        mac = None
        mac_raw = attrs.get(IFLA_ADDRESS)
        if mac_raw:
            mac = ":".join(f"{b:02x}" for b in mac_raw)
        result.append(
            {
                "index": if_index,
                "name": name,
                "flags": if_flags,
                "operstate": operstate,
                "mac": mac,
                "mtu": mtu,
            }
        )
    return result


def collect_addresses(timeout: float = _TIMEOUT) -> Optional[List[Dict[str, Any]]]:
    """Enumerate IPv4/IPv6 addresses via rtnetlink."""
    # ifaddrmsg: family(u8) prefixlen(u8) flags(u8) scope(u8) index(u32)
    payload = struct.pack("BBBB I", 0, 0, 0, 0, 0)  # family=AF_UNSPEC (0) dumps all
    # Actually family 0 may not dump all on some kernels; do AF_INET and AF_INET6 separately.
    all_items: List[Dict[str, Any]] = []
    for fam in (AF_INET, AF_INET6):
        payload = struct.pack("BBBB I", fam, 0, 0, 0, 0)
        msgs = _send_dump_request(RTM_GETADDR, fam, payload)
        if msgs is None:
            return None
        for msg in msgs:
            if len(msg) < 16:
                continue
            nlmsg_len, nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid = struct.unpack_from("IHHII", msg, 0)
            if nlmsg_type != RTM_NEWADDR:
                continue
            body = msg[16:]
            if len(body) < 8:
                continue
            family, prefixlen, flags, scope, if_index = struct.unpack_from("BBBB I", body, 0)
            attrs = _parse_attrs(body, 8)
            addr_bytes = attrs.get(IFA_ADDRESS) or attrs.get(IFA_LOCAL)
            if not addr_bytes:
                continue
            try:
                addr = socket.inet_ntop(family, addr_bytes)
            except (OSError, ValueError):
                continue
            all_items.append(
                {
                    "ifindex": if_index,
                    "family": "ipv4" if family == AF_INET else "ipv6" if family == AF_INET6 else str(family),
                    "address": addr,
                    "prefixlen": prefixlen,
                    "scope": scope,
                    "flags": flags,
                }
            )
    return all_items


def collect_default_routes(timeout: float = _TIMEOUT) -> Optional[List[Dict[str, Any]]]:
    """Enumerate IPv4/IPv6 default routes via rtnetlink."""
    result: List[Dict[str, Any]] = []
    for fam in (AF_INET, AF_INET6):
        # rtmsg: family, dst_len, src_len, tos, table, protocol, scope, type, flags
        payload = struct.pack("BBBBBBBB I", fam, 0, 0, 0, 0, 0, 0, RTN_UNICAST, 0)
        msgs = _send_dump_request(RTM_GETROUTE, fam, payload)
        if msgs is None:
            return None
        for msg in msgs:
            if len(msg) < 16:
                continue
            nlmsg_len, nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid = struct.unpack_from("IHHII", msg, 0)
            if nlmsg_type != RTM_NEWROUTE:
                continue
            body = msg[16:]
            if len(body) < 12:
                continue
            rtm_family, rtm_dst_len, rtm_src_len, rtm_tos, rtm_table, rtm_protocol, rtm_scope, rtm_type, rtm_flags = struct.unpack_from(
                "BBBBBBBB I", body, 0
            )
            if rtm_dst_len != 0:
                continue
            if rtm_type != RTN_UNICAST:
                continue
            if rtm_table not in (0, RT_TABLE_MAIN):
                continue
            attrs = _parse_attrs(body, 12)
            oif_raw = attrs.get(RTA_OIF)
            if_index = struct.unpack_from("I", oif_raw, 0)[0] if (oif_raw and len(oif_raw) >= 4) else 0
            gw_raw = attrs.get(RTA_GATEWAY)
            gateway = None
            if gw_raw:
                try:
                    gateway = socket.inet_ntop(rtm_family, gw_raw)
                except (OSError, ValueError):
                    gateway = None
            prio_raw = attrs.get(RTA_PRIORITY)
            metric = struct.unpack_from("I", prio_raw, 0)[0] if (prio_raw and len(prio_raw) >= 4) else 0
            result.append(
                {
                    "family": "ipv4" if rtm_family == AF_INET else "ipv6" if rtm_family == AF_INET6 else str(rtm_family),
                    "ifindex": if_index,
                    "gateway": gateway,
                    "metric": metric,
                    "table": rtm_table,
                }
            )
    return result


def netlink_available() -> bool:
    try:
        sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_ROUTE)
        sock.close()
        return True
    except OSError:
        return False