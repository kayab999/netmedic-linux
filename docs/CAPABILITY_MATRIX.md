# Capability and action inventory (baseline 1.9.0)

Baseline commit: `2a240ee` (tag `v1.9.0`). This inventory captures the current
state before LUCP changes; it is the reference for Phase 0 characterisation.

## Diagnostic capabilities (L0 candidates)

| Capability | Current source | Level | Notes |
|---|---|---|---|
| Interface list/state/MAC | `ip` + `/sys` | L0 target | Must become native-first |
| Addresses | `ip` | L0 target | rtnetlink in Phase 5 |
| Default route/gateway | `ip` + `/proc/net/route` | L0 target | Native IPv4/IPv6 needed |
| System name resolution | `getent` | L0 target | Replace with `socket.getaddrinfo` |
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

- `production_ready`: currently requires nmcli, ip, curl, helper, polkit, etc.
  (to be split into `core_ready` / `privileged_ready` in Phase 1).
- `overall_ok`: aggregates almost all checks (to be narrowed to core health).

## Readiness status values (current)

See `netmedic/netmedic/status.py` for the full check list. No change in this
phase.