# Capability and action inventory (baseline 1.9.0)

Baseline commit: `2a240ee` (tag `v1.9.0`). This inventory captures the 1.9.0
diagnostic sources before the LUCP runtime changes; the Readiness section
reflects the Phase 1 split.

## Diagnostic capabilities (L0 candidates)

| Capability | Current source | Level | Notes |
|---|---|---|---|
| Interface list/state/MAC | `ip` + `/sys` | L0 target | Must become native-first |
| Addresses | `ip` | L0 target | rtnetlink in Phase 5 |
| Default route/gateway | `ip` + `/proc/net/route` | L0 target | Native IPv4/IPv6 needed |
| System name resolution | `socket.getaddrinfo()` | L0 | Native NSS resolution; no `getent` dependency |
| TCP connectivity | `curl` | L0 target | Replace with `socket.create_connection` |
| HTTP/TLS access | `curl` | L0 target | stdlib HTTP client |
| Captive portal hint | Ubuntu-specific endpoint | L0 target | Neutral configurable endpoint |
| Interface MTU | not collected | L0 target | `/sys/class/net/*/mtu` |
| ICMP latency/loss | `ping` | L1/L0 optional | Separate capability, may be absent |
| NetworkManager state | `nmcli` | L1 | Optional integration |
| Firewall status | `ufw` | L1 | Optional integration |
| Inbound/outbound tools | `resolvectl`, `dhclient`, `rfkill` | L1 | Optional |

## Privileged actions (L2)

| IPC verb | Polkit action | Backend | keep_auth |
|---|---|---|---|
| flush-dns | com.kayab.netmedic.flush-dns | resolvectl | yes |
| renew-ip | com.kayab.netmedic.renew-ip | nmcli/dhclient | yes |
| change-dns | com.kayab.netmedic.change-dns | nmcli | no |
| restart-adapter | com.kayab.netmedic.restart-adapter | ip link | no |
| reset-stack | com.kayab.netmedic.reset-stack | systemctl NM | no |
| toggle-firewall | com.kayab.netmedic.toggle-firewall | ufw | no |
| vpn-install | com.kayab.netmedic.vpn-install | vendored installer | no |
| vpn-add-client | com.kayab.netmedic.vpn-create | openvpn | no |
| vpn-revoke-client | com.kayab.netmedic.vpn-revoke | openvpn | no |
| vpn-restart-service | com.kayab.netmedic.vpn-reconnect | systemctl | no |
| vpn-list | com.kayab.netmedic.vpn-list | EasyRSA index | no |
| vpn-start-service | com.kayab.netmedic.vpn-start | systemctl | no |

## Readiness

- `core_ready`: diagnostic gate. Requires a supported Python runtime and a
  `0700` state directory owned by the current user. It does not require
  NetworkManager, iproute2, curl, the helper or Polkit.
- `privileged_ready`: installed helper + library, `pkexec` and all 12 Kayab
  Polkit actions. `false` never degrades `core_ready`.
- `production_ready`: deprecated alias of `core_ready` (kept through 1.10.x).
- `overall_ok`: equals `core_ready`; internal core failures only.
- `--require-privileged`: exits 1 when `privileged_ready` is false.

`collect_status()` now also emits `schema_version`, `scope` (current network
namespace plus a conservative container hint) and `capabilities`. Each
capability separates `availability` (`AVAILABLE`/`UNAVAILABLE`/`UNKNOWN`) from
`outcome` (`NOT_ATTEMPTED` initially).

## Readiness status values (current)

Phase 1 is implemented in `netmedic/netmedic/capabilities.py` and
`netmedic/netmedic/status.py`. The L0 backends listed above are still the
current ones: `status` reports them as capabilities but does not execute
probes, so a missing `getent`/`curl`/`ip`/`ping` narrows detail without making
the install non-operational. Native-first replacements remain scheduled for
Phases 3–5.