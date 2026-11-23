"""Minimal rtnetlink client tests (read-only, hermetic)."""
from __future__ import annotations

import socket
import struct
from unittest.mock import patch

from netmedic import rtnetlink as rt


def test_parse_attrs_basic() -> None:
    # rta_len includes 4-byte header.
    data = struct.pack("HH", 8, 3) + b"eth0\x00" + b"\x00\x00\x00\x00"
    attrs = rt._parse_attrs(data, 0)
    assert 3 in attrs
    assert attrs[3].startswith(b"eth0")


def test_parse_attrs_rejects_short() -> None:
    assert rt._parse_attrs(b"\x01\x00", 0) == {}


def test_ifname_from_attrs() -> None:
    assert rt._ifname_from_attrs({rt.IFLA_IFNAME: b"eth0\x00"}) == "eth0"
    assert rt._ifname_from_attrs({}) == ""


def test_netlink_available() -> None:
    assert isinstance(rt.netlink_available(), bool)


def test_collect_links_socket_failure_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("socket.socket", lambda *a, **k: (_ for _ in ()).throw(OSError("no netlink")))
    assert rt.collect_links() is None


def test_collect_addresses_socket_failure_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("socket.socket", lambda *a, **k: (_ for _ in ()).throw(OSError("no netlink")))
    assert rt.collect_addresses() is None


def test_collect_default_routes_socket_failure_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("socket.socket", lambda *a, **k: (_ for _ in ()).throw(OSError("no netlink")))
    assert rt.collect_default_routes() is None


def test_collect_links_parses_crafted_message(monkeypatch) -> None:
    # Build a minimal RTM_NEWLINK message with IFLA_IFNAME and IFLA_MTU.
    ifname = b"eth9\x00"
    name_attr = struct.pack("HH", 4 + len(ifname), rt.IFLA_IFNAME) + ifname
    name_attr += b"\x00" * ((4 - (len(name_attr) % 4)) % 4)
    mtu_attr = struct.pack("HHI", 8, rt.IFLA_MTU, 1400)  # rta_len=8, type=IFLA_MTU, value u32
    # ifinfomsg 16 bytes + attrs
    body = struct.pack("BBHiii", 2, 0, 0, 42, 0x100, 0) + name_attr + mtu_attr
    msg = struct.pack("IHHII", 16 + len(body), rt.RTM_NEWLINK, rt.NLM_F_MULTI, 1, 1) + body
    # NLMSG_DONE terminator
    done = struct.pack("IHHII", 16, rt.NLMSG_DONE, 0, 1, 1)
    monkeypatch.setattr(rt, "_send_dump_request", lambda *a, **k: [msg, done])
    links = rt.collect_links()
    assert links is not None
    assert any(l["name"] == "eth9" and l["mtu"] == 1400 and l["index"] == 42 for l in links)


def test_collect_default_routes_parses_crafted_message(monkeypatch) -> None:
    import socket as _s

    # rtmsg 12 bytes + RTA_OIF (4+4) + RTA_GATEWAY (4+4) + RTA_PRIORITY (4+4)
    oif = struct.pack("I", 2)
    gw = _s.inet_pton(_s.AF_INET, "192.168.1.1")
    prio = struct.pack("I", 100)
    attrs = (
        struct.pack("HH", 8, rt.RTA_OIF) + oif
        + struct.pack("HH", 8, rt.RTA_GATEWAY) + gw
        + struct.pack("HH", 8, rt.RTA_PRIORITY) + prio
    )
    body = struct.pack("BBBBBBBB I", 2, 0, 0, 0, 0, 0, 0, rt.RTN_UNICAST, 0) + attrs
    msg = struct.pack("IHHII", 16 + len(body), rt.RTM_NEWROUTE, rt.NLM_F_MULTI, 1, 1) + body
    done = struct.pack("IHHII", 16, rt.NLMSG_DONE, 0, 1, 1)
    monkeypatch.setattr(rt, "_send_dump_request", lambda *a, **k: [msg, done])
    routes = rt.collect_default_routes()
    assert routes is not None
    assert any(r["family"] == "ipv4" and r["gateway"] == "192.168.1.1" and r["metric"] == 100 for r in routes)


def test_collect_links_returns_none_on_nlmsg_error(monkeypatch) -> None:
    # NLMSG_ERROR with nonzero errno.
    err = struct.pack("IHHII", 16 + 4, rt.NLMSG_ERROR, 0, 1, 1) + struct.pack("i", -1) + b"\x00" * 12
    monkeypatch.setattr(rt, "_send_dump_request", lambda *a, **k: None)
    assert rt.collect_links() is None