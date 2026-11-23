"""LUCP capability registry (Phase 1).

Availability and outcome are separate: a missing optional tool is
``UNAVAILABLE`` with ``NOT_ATTEMPTED`` outcome, never a generic failure. A
probe that cannot determine the truth is ``UNKNOWN`` and must not be reported
as absent.

This module is stdlib-only. It does not execute diagnostics; it describes what
the current build can attempt and which backend each capability uses.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from netmedic.action_catalog import ACTIONS

SCHEMA_VERSION = "1.0"

LEVEL_L0 = "L0"
LEVEL_L1 = "L1"
LEVEL_L2 = "L2"
LEVELS = frozenset({LEVEL_L0, LEVEL_L1, LEVEL_L2})

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
AVAILABILITIES = frozenset({AVAILABLE, UNAVAILABLE, UNKNOWN})

NOT_ATTEMPTED = "NOT_ATTEMPTED"
OK = "OK"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
ERROR = "ERROR"
OUTCOMES = frozenset({NOT_ATTEMPTED, OK, PARTIAL, FAILED, CANCELLED, ERROR})

REASON_TOOL_NOT_FOUND = "tool_not_found"
REASON_HELPER_NOT_INSTALLED = "helper_not_installed"
REASON_HELPER_DISABLED = "helper_disabled"
REASON_PKEXEC_NOT_FOUND = "pkexec_not_found"
REASON_POLKIT_PROBE_UNAVAILABLE = "polkit_probe_unavailable"
REASON_POLKIT_ACTION_MISSING = "polkit_action_missing"

SCOPE_LABEL = "current network namespace"
SCOPE_NETNS_LINK = "/proc/self/ns/net"
CONTAINER_MARKERS: Tuple[str, ...] = ("/.dockerenv", "/run/.containerenv")
CONTAINER_CGROUP_TOKENS: Tuple[str, ...] = (
    "docker",
    "kubepods",
    "containerd",
    "lxc",
    "podman",
)

Which = Callable[[str], Optional[str]]


@dataclass(frozen=True)
class Capability:
    """One entry of the capability report (see docs/LUCP.md §3.3)."""

    id: str
    level: str
    availability: str
    outcome: str = NOT_ATTEMPTED
    backend: Optional[str] = None
    reason_code: Optional[str] = None
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    remediation: Optional[str] = None
    scope: str = SCOPE_LABEL

    def __post_init__(self) -> None:
        if not self.id or not self.id.replace("_", "").isalnum():
            raise ValueError(f"capability id must be stable snake_case: {self.id!r}")
        if self.level not in LEVELS:
            raise ValueError(f"invalid level {self.level!r}")
        if self.availability not in AVAILABILITIES:
            raise ValueError(f"invalid availability {self.availability!r}")
        if self.outcome not in OUTCOMES:
            raise ValueError(f"invalid outcome {self.outcome!r}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Scope:
    """What the diagnostics observe: the current network namespace, not a host guess."""

    label: str
    network_namespace: Optional[str]
    container_hint: Optional[bool]
    container_sources: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "network_namespace": self.network_namespace,
            "container_hint": self.container_hint,
            "container_sources": list(self.container_sources),
        }


@dataclass(frozen=True)
class DetectionContext:
    """Inputs already resolved by the caller (status.py or tests)."""

    which: Which = shutil.which
    helper_installed: bool = False
    helper_enabled: bool = False
    pkexec_present: bool = False
    polkit_probe_ok: bool = False
    polkit_actions: frozenset[str] = frozenset()


# (id, level, tool, backend, summary) — current backends, not future targets.
_TOOL_CAPABILITIES: Tuple[Tuple[str, str, str, str, str], ...] = (
    (
        "interface_inventory",
        LEVEL_L0,
        "ip",
        "iproute2",
        "List interfaces, link state and MAC addresses.",
    ),
    (
        "address_inventory",
        LEVEL_L0,
        "ip",
        "iproute2",
        "List IPv4/IPv6 addresses per interface.",
    ),
    (
        "default_route",
        LEVEL_L0,
        "ip",
        "iproute2",
        "Read the current default route and gateway.",
    ),
    (
        "system_name_resolution",
        LEVEL_L0,
        "getent",
        "getent",
        "Resolve names through the system NSS configuration.",
    ),
    (
        "tcp_connectivity",
        LEVEL_L0,
        "curl",
        "curl",
        "Probe TCP reachability of fixed targets.",
    ),
    (
        "http_tls_access",
        LEVEL_L0,
        "curl",
        "curl",
        "Probe HTTP status and TLS access of fixed targets.",
    ),
    (
        "captive_portal_hint",
        LEVEL_L0,
        "curl",
        "curl",
        "Detect a captive portal through a redirect/204 check.",
    ),
    (
        "icmp_latency",
        LEVEL_L0,
        "ping",
        "iputils",
        "Optional ICMP latency/loss detail; absence is not a core failure.",
    ),
    (
        "networkmanager",
        LEVEL_L1,
        "nmcli",
        "networkmanager",
        "Read NetworkManager state and apply NM-backed changes.",
    ),
    (
        "firewall_admin",
        LEVEL_L1,
        "ufw",
        "ufw",
        "Read and change UFW firewall state.",
    ),
    (
        "resolver_cache",
        LEVEL_L1,
        "resolvectl",
        "systemd-resolved",
        "Flush the systemd-resolved cache.",
    ),
    (
        "dhcp_client",
        LEVEL_L1,
        "dhclient",
        "dhclient",
        "Renew a DHCP lease when NetworkManager is not the backend.",
    ),
    (
        "service_manager",
        LEVEL_L1,
        "systemctl",
        "systemd",
        "Restart network services through systemd.",
    ),
)


def _tool_capability(
    ctx: DetectionContext,
    cap_id: str,
    level: str,
    tool: str,
    backend: str,
    summary: str,
) -> Capability:
    path = ctx.which(tool)
    if path:
        return Capability(
            id=cap_id,
            level=level,
            availability=AVAILABLE,
            backend=backend,
            summary=summary,
            details={"tool": tool},
        )
    return Capability(
        id=cap_id,
        level=level,
        availability=UNAVAILABLE,
        backend=None,
        reason_code=REASON_TOOL_NOT_FOUND,
        summary=summary,
        details={"tool": tool},
        remediation=f"Install {tool} to enable this capability.",
    )


def _privileged_capability(
    ctx: DetectionContext,
    cap_id: str,
    verb: Optional[str],
    polkit_id: str,
    description: str,
) -> Capability:
    details = {"verb": verb, "polkit_action": polkit_id}

    def entry(
        availability: str,
        *,
        reason_code: Optional[str] = None,
        remediation: Optional[str] = None,
    ) -> Capability:
        return Capability(
            id=cap_id,
            level=LEVEL_L2,
            availability=availability,
            backend="helper",
            reason_code=reason_code,
            summary=description,
            details=details,
            remediation=remediation,
        )

    if not ctx.helper_installed:
        return entry(
            UNAVAILABLE,
            reason_code=REASON_HELPER_NOT_INSTALLED,
            remediation="Run ./scripts/install-polkit-policy.sh to install the helper.",
        )
    if not ctx.helper_enabled:
        return entry(
            UNAVAILABLE,
            reason_code=REASON_HELPER_DISABLED,
            remediation="Unset NETMEDIC_USE_HELPER=0 (or install the system helper).",
        )
    if not ctx.pkexec_present:
        return entry(
            UNAVAILABLE,
            reason_code=REASON_PKEXEC_NOT_FOUND,
            remediation="Install polkit/pkexec for privileged actions.",
        )
    if not ctx.polkit_probe_ok:
        return entry(
            UNKNOWN,
            reason_code=REASON_POLKIT_PROBE_UNAVAILABLE,
            remediation="Check that pkaction and the polkit daemon are reachable.",
        )
    if polkit_id not in ctx.polkit_actions:
        return entry(
            UNAVAILABLE,
            reason_code=REASON_POLKIT_ACTION_MISSING,
            remediation="Re-run ./scripts/install-polkit-policy.sh as root.",
        )
    return entry(AVAILABLE)


def collect_capabilities(ctx: DetectionContext) -> list[Capability]:
    """Build the capability list for the current build and detection context."""
    capabilities = [
        _tool_capability(ctx, *entry) for entry in _TOOL_CAPABILITIES
    ]
    for spec in ACTIONS:
        if spec.ipc_action is None or spec.polkit_id is None:
            continue
        capabilities.append(
            _privileged_capability(
                ctx=ctx,
                cap_id=f"privileged_{spec.ipc_action}",
                verb=spec.helper_verb,
                polkit_id=spec.polkit_id,
                description=spec.description,
            )
        )
    return capabilities


def collect_scope(
    *,
    ns_link: str = SCOPE_NETNS_LINK,
    cgroup_path: str = "/proc/self/cgroup",
    marker_paths: Sequence[str] = CONTAINER_MARKERS,
) -> Scope:
    """Return a conservative description of the observed network scope.

    ``container_hint=False`` means no hint was found; it does not prove the
    process runs on a physical host. ``network_namespace=None`` means the
    identity could not be read, not that there is no namespace.
    """
    try:
        network_namespace: Optional[str] = os.readlink(ns_link)
    except OSError:
        network_namespace = None

    sources: list[str] = []
    for marker in marker_paths:
        try:
            if Path(marker).exists():
                sources.append(marker)
        except OSError:
            continue

    try:
        cgroup = Path(cgroup_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        cgroup = ""
    for token in CONTAINER_CGROUP_TOKENS:
        if token in cgroup:
            sources.append(f"cgroup:{token}")
            break

    return Scope(
        label=SCOPE_LABEL,
        network_namespace=network_namespace,
        container_hint=bool(sources),
        container_sources=tuple(sources),
    )
