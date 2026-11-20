# ADR-001 — Adopt LUCP for universal diagnostics and multi-backend management

- **Status:** Accepted
- **Date:** 2026-11-20
- **Deciders:** Kayab Software (single maintainer)
- **Related:** `docs/LUCP.md`, maintainer plan `netmedic-lucp-roadmap.md`

## Context

NetMedic 1.9.0 hardened the privileged helper but still carries inherited
assumptions: `production_ready` requires `nmcli` and `ip`; DNS/TCP/HTTP probes
depend on `getent`/`curl`/`ping`; PyGObject is a mandatory dependency even for
headless use; the installer rejects unknown distributions. These contradict the
goal of diagnosing an unknown Linux host honestly.

## Decision

Adopt the Linux Universal Capability Principle (LUCP) as the architecture for
NetMedic 1.10.0 (*Universal Diagnostics Foundation*) and the subsequent
multi-backend line:

- Separate availability from operation outcome.
- Separate `core_ready` from `privileged_ready`.
- Make the diagnostic core stdlib- and kernel-interface-based.
- Make GTK/PyGObject an optional GUI dependency.
- Decouple NetworkManager, systemd-networkd, firewalld and nftables through
  adapters that declare their own semantics.
- Keep helper selection fail-closed: only backend IDs, fixed executable paths.
- Add reproducible L0 compatibility matrices (Ubuntu, Debian slim, Fedora,
  Arch, openSUSE, Alpine) with fault-injection for missing tools.

Versioning: `HELPER_VERSION` and `HELPER_PROTOCOL_VERSION` are independent.
The major version only changes on a real external contract break.

## Consequences

- Larger initial refactor (Phases 0–6) before any new backend.
- Existing NM/UFW behaviour must not regress.
- Documentation and truthfulness tests must track every announced capability.