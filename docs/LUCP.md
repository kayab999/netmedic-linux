# Linux Universal Capability Principle (LUCP)

NetMedic adopts LUCP as an engineering policy for the 1.10.0 line. The full
phased implementation plan lives in the maintainer plan
`netmedic-lucp-roadmap.md`; this document states the policy and the invariants
that every change must preserve.

## Principle

Software adapts to the capabilities of the host operating system. It does not
impose a distribution, service manager, package manager or tool set as a
universal requirement, except when a specific function explicitly depends on
them.

## Levels

- **L0 — universal diagnostics:** interfaces, addresses, routes, gateway,
  system name resolution, TCP connectivity, HTTP/TLS access, external
  connectivity, visible MTU and, when available, ICMP latency/loss. No
  privileges required to read or probe.
- **L1 — adaptive integration:** NetworkManager, systemd-networkd, Netplan as
  a configuration source, systemd-resolved, iproute2, UFW, firewalld, nftables
  and wireless tools. Netplan is never presented as a runtime service.
- **L2 — conditional administration:** interface/service restart, DNS, firewall,
  VPN and other privileged actions, only when capability, policy and permissions
  allow.

**L0 never depends on L1 or L2.** Missing `nmcli`, `curl`, `getent`, `ping`,
`ip`, `ufw`, polkit or the helper must not prevent native diagnosis.

## States

Availability and outcome are separate:

- `AVAILABLE` / `UNAVAILABLE` / `UNKNOWN` for capability availability.
- `NOT_ATTEMPTED` / `OK` / `PARTIAL` / `FAILED` / `CANCELLED` / `ERROR` for
  operation outcome.

`UNAVAILABLE` means a required mechanism was determined to be absent.
`UNKNOWN` means the probe could not determine it; it is never shown as absent
and never becomes a global failure. A real negative result is not retried
through another backend to obtain a more favourable verdict.

## Invariants

1. Distribution-independent functional core.
2. Diagnosis primarily through native interfaces.
3. Specific integrations decoupled through adapters.
4. Explicit representation of missing capabilities.
5. Minimum privileges; detection and privileged execution are separate.
6. Transparent functional degradation.
7. Compatibility demonstrated through reproducible matrices and tests.

## Quality criterion

100 % of hermetic L0 tests pass in target environments, and no L1/L2
limitation is hidden. Every exception is documented with cause and scope.

## Scope of this document

This policy authorises future work in NetMedic only. It does not copy modules or
contracts into FileWizard, NetRail or other Kayab products without their own
analysis.