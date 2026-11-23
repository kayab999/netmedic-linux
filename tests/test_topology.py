"""Native topology collectors (L0) — hermetic fixture tests."""
from __future__ import annotations

import os
from pathlib import Path

from netmedic.topology import (
    collect_default_gateways_v4,
    collect_default_gateways_v6,
    collect_interfaces,
    collect_ipv6_addresses,
    collect_mtu,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_interfaces_from_sys_fixture(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    for name, oper, mac, mtu in (
        ("eth0", "up", "aa:bb:cc:dd:ee:ff", "1500"),
        ("lo", "unknown", "00:00:00:00:00:00", "65536"),
    ):
        base = sys_root / "class" / "net" / name
        _write(base / "operstate", oper + "\n")
        _write(base / "address", mac + "\n")
        _write(base / "mtu", mtu + "\n")
    ifaces = collect_interfaces(sys_root)
    names = [i["name"] for i in ifaces]
    assert "eth0" in names and "lo" in names
    eth = next(i for i in ifaces if i["name"] == "eth0")
    assert eth["state"] == "up"
    assert eth["mac"] == "aa:bb:cc:dd:ee:ff"
    assert eth["mtu"] == 1500


def test_collect_interfaces_rejects_unsafe_names(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    bad = sys_root / "class" / "net" / ".." / "evil"
    bad.mkdir(parents=True, exist_ok=True)
    # A name with path traversal must not be collected.
    assert all(i["name"] != ".." for i in collect_interfaces(sys_root))


def test_collect_interfaces_missing_source_returns_empty(tmp_path: Path) -> None:
    assert collect_interfaces(tmp_path / "no-sys") == []


def test_collect_interfaces_invalid_mtu(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    base = sys_root / "class" / "net" / "eth0"
    _write(base / "operstate", "up\n")
    _write(base / "address", "aa:bb\n")
    _write(base / "mtu", "not-a-number\n")
    ifaces = collect_interfaces(sys_root)
    assert ifaces[0]["mtu"] is None


def test_collect_default_gateways_v4(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    _write(
        proc_root / "net" / "route",
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\tFE01A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
        "eth0\t0001A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n",
    )
    routes = collect_default_gateways_v4(proc_root)
    assert len(routes) == 1
    assert routes[0]["iface"] == "eth0"
    assert routes[0]["gateway"] == "192.168.1.254"
    assert routes[0]["metric"] == 100


def test_collect_default_gateways_v4_absent(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    _write(proc_root / "net" / "route", "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n")
    assert collect_default_gateways_v4(proc_root) == []


def test_collect_default_gateways_v4_metric_sort(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    _write(
        proc_root / "net" / "route",
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
        "eth1\t00000000\t0201A8C0\t0003\t0\t0\t200\t00000000\n"
        "eth0\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\n",
    )
    routes = collect_default_gateways_v4(proc_root)
    assert [r["iface"] for r in routes] == ["eth0", "eth1"]


def test_collect_default_gateways_v6(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    _write(
        proc_root / "net" / "ipv6_route",
        "00000000000000000000000000000000 00 00000000000000000000000000000000 00 fe800000000000000000000000000001 00000064 00000005 00000000 00000003   eth0\n",
    )
    routes = collect_default_gateways_v6(proc_root)
    assert len(routes) == 1
    assert routes[0]["iface"] == "eth0"
    assert routes[0]["gateway"] == "fe80:0:0:0:0:0:0:1"


def test_collect_ipv6_addresses(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    _write(
        proc_root / "net" / "if_inet6",
        "2806102e002f8e0e2c0c18b8acc5a981 02 40 00 01   eth0\n"
        "fe800000000000009ab931c748abf9e1 02 40 20 80   eth0\n",
    )
    addrs = collect_ipv6_addresses(proc_root)
    assert "eth0" in addrs
    assert len(addrs["eth0"]) == 2
    assert addrs["eth0"][0].endswith("/64")


def test_collect_mtu(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    _write(sys_root / "class" / "net" / "eth0" / "mtu", "1500\n")
    assert collect_mtu(sys_root, "eth0") == 1500
    assert collect_mtu(sys_root, "nope") is None
    assert collect_mtu(sys_root, "../evil") is None


def test_collect_mtu_invalid(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    _write(sys_root / "class" / "net" / "eth0" / "mtu", "garbage\n")
    assert collect_mtu(sys_root, "eth0") is None