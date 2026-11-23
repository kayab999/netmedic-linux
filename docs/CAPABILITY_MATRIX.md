# Capability inventory (1.10.0)

Current as of tag `v1.10.0`. This is the authoritative inventory of NetMedic's
capabilities, backends, levels and limitations. The historical 1.9.0 baseline is
preserved in `CAPABILITY_MATRIX_1.9.0_BASELINE.md`.

## Levels

- **L0** — universal diagnostics: native, stdlib/kernel sources, no privileges.
- **L1** — adaptive integration: optional tools and services.
- **L2** — conditional administration: privileged helper + Polkit.

## L0 capabilities (native)

| Capability | Backend | Source | Notes |
|---|---|---|---|
| `interface_inventory` | iproute2 (enrichment) | `/sys/class/net` + `ip` | Native interface list from `/sys`; `ip` is enrichment |
| `address_inventory` | iproute2 (enrichment) | `/sys` + `ip` | IPv6 from `/proc/net/if_inet6`; IPv4 pending rtnetlink |
| `default_route` | native | `/proc/net/route`, `/proc/net/ipv6_route`, rtnetlink | Native first; `ip` fallback |
| `system_name_resolution` | native | `socket.getaddrinfo()` | NSS-aware; no `getent` dependency |
| `tcp_connectivity` | native | `socket.create_connection()` | RTT measured; refused/timeout/unreachable classified |
| `http_tls_access` | native | stdlib `http.client` + `ssl` | Certificate validation always on; never `CERT_NONE` |
| `captive_portal_hint` | native | stdlib HTTP | Redirect detection; inconclusive → unknown |
| `interface_mtu` | native | `/sys/class/net/*/mtu` | Invalid/missing → None |
| `icmp_latency` | iputils (optional) | `ping` | L0 optional; absence → UNAVAILABLE, not attempted |
| `scope` | native | `/proc/self/ns/net` | Current network namespace; container hints only |

## L1 capabilities (adaptive integration)

| Capability | Backend | Tool | Notes |
|---|---|---|---|
| `networkmanager` | NetworkManager | `nmcli` | Optional; absence → UNAVAILABLE |
| `firewall_admin` | UFW | `ufw` | Optional |
| `resolver_cache` | systemd-resolved | `resolvectl` | Optional |
| `dhcp_client` | dhclient | `dhclient` | Optional |
| `service_manager` | systemd | `systemctl` | Optional |
| `nm_connectivity` | NetworkManager | `nmcli` | Second opinion; None if absent |

## L2 capabilities (privileged, helper + Polkit)

12 actions: `flush_dns`, `renew_ip`, `change_dns`, `restart_adapter`,
`reset_stack`, `toggle_firewall`, `vpn_install`, `vpn_create_client`,
`vpn_revoke_client`, `vpn_restart_service`, `vpn_list`, `vpn_start_service`.

Each requires: installed helper + library, `pkexec`, and the corresponding
Polkit action registered. `privileged_ready` is true only when all 12 are
available. `false` never degrades `core_ready`.

## Readiness

- `core_ready`: supported Python runtime + `0700` state dir owned by the
  current user. Does not require NM, iproute2, curl, helper or Polkit.
- `privileged_ready`: helper + library + `pkexec` + all 12 Kayab Polkit actions.
- `production_ready`: deprecated alias of `core_ready` (kept through 1.10.x).
- `overall_ok`: equals `core_ready`.
- `--require-privileged`: exits 1 when `privileged_ready` is false.

## Known limitations (1.10.0)

- `interface_inventory` and `address_inventory` still rely on `ip` as
  enrichment; native `/sys` collection is primary but IPv4 addresses are
  pending rtnetlink (Phase 5).
- `icmp_latency` requires `ping`; absence only reduces detail.
- L2 administration limited to the 12 supported verbs and the installed
  helper; no new backends in this release.
- Compatibility matrix covers Ubuntu 24.04, Debian bookworm-slim and Alpine
  3.20 in CI; Ubuntu 22.04/26.04, Fedora, Arch and openSUSE are targeted
  but not yet in CI.

## Scope

All diagnostics observe the **current network namespace**. Container hints
(`/.dockerenv`, cgroups) are advisory only; absence does not prove a physical
host. See `docs/LUCP.md` §3.4.
EOF
echo done