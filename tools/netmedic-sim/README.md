# netmedic-sim — hermetic network-fault harness

> **Purpose:** inject the exact incident (`gateway OK, WAN down`) as *real* kernel state
> in Linux netns, not mocked `CommandRunner`. Converts the E2E matrix from manual
> iptables on VM to automated regression: `pytest -m netns` needs `cap NET_ADMIN`
> (root in CI).

## Topology v0 (one topology, two scenarios)

```
root ns (setup only) — creates veth, moves, then sleeps (no mutation)
┌─ nmsim-<runid>-r (ROUTER = "internet") ─┐
│ LAN 192.0.2.1/24  (gateway)              │
│ WAN dummy: 8.8.8.8/32, 1.1.1.1/32        │
│   no service → without nft: RST on :80  │
│   Scenario A: nft INPUT drop (timeout)  │
│   Scenario B: micro-DNS :53 on 192.0.2.1 │
└─────────── veth nmsim-<id>-rc ──────────┘
            ↕
┌─ nmsim-<runid>-c (CLIENT) ──────────────┐
│ 192.0.2.2/24 via 192.0.2.1                │
│ /etc/netns/<name>/resolv.conf → 192.0.2.1│
│ runs: netmedic (pytest -m netns)         │
└──────────────────────────────────────────┘
```

*Host footprint after run:* zero — `ip netns del` + `rm /etc/netns/<name>` + veth auto-reap + nft table dies with ns.

*Why hermetic:* sysctls per-netns, nft per-ns, veth peer dies with ns, `/etc/netns/<name>/resolv.conf` makes DNS deterministic:
- **A:** `nft drop udp dport 53` → DNS timeout (drop, faithful to dead upstream)
- **B:** micro-DNS → DNS instant success
Without nft, DNS to 192.0.2.1 with no listener would be `port unreachable` (refused) — also fail but different timing; drop is more faithful (silent).

*Naming:* `nmsim-<runid>-{c,r}` (runid = wrapper PID) — parallel runs + reap; never `medic[0-9a-f]{6}` so `network.py:103` medic reap does not interfere.

*State file:* `~/.local/state/netmedic/sim/<runid>.json` mirrors `network.py` medic reap pattern — wrapper `trap EXIT` removes, but stale check on next wrapper start reaps orphaned `nmsim-*` ns (same as `created_ifaces` reap).

## Scenarios v0

| Scenario | Router-ns config | Expected golden (5 lines) |
|---|---|---|
| **A WAN-drop (incident)** | `nft drop icmp + tcp dport 80/443 + udp dport 53` to `{8.8.8.8,1.1.1.1,192.0.2.1}` → timeouts silent (faithful to dead upstream), no micro-DNS | `❌ Diagnostics FAILED` (gateway OK, DNS fail, net fail, no captive) `⚠️ Flush EXECUTED` `⚠️ Renew` (code ∈ {EXECUTED,FAILED,ERROR}, never OK) `❌ Post unchanged` `❌ Smart Repair NOT recovered upstream` |
| **B ICMP-ok/TCP-blocked** | Flush nft, **micro-DNS** on 192.0.2.1:53 → `getent` OK, TCP RST (no listener, no drop), ICMP OK | `⚠️ Diagnostics PARTIAL "TCP blocked, ICMP ok — firewall suspected"` + `internet_ok=False` + `icmp True` in details |

*Scenario B* is the **R1 regression**: topology A alone does not catch TCP-only vs ICMP bug.

## Wiring

- **Wrapper** `scripts/netns-golden.sh` (root): setup → `ip netns exec nmsim-<id>-c env NETMEDIC_SIM_NS=1 ./venv/bin/pytest -m netns tests/test_golden_replay_ns.py` → `trap EXIT` teardown.
- **Guard** `pytest.mark.netns` + `skipif(not os.environ.get("NETMEDIC_SIM_NS"))` — never runs outside ns.
- **Budget** DNS refused instant + 2×curl 5s + https fallback + settle ≤8s → <30s per scenario.
- **Benign side effect:** `resolvectl flush-caches` in-ns reaches host via D-Bus (shared) — cleans host cache too; documented, harmless.
- **Growth v1 (no redesign):** add services in router-ns (HTTP 204 on 1.1.1.1, 302 captive, DNS-only) — zero new topologies.

## Acceptance v0

1. Wrapper idempotent from dirty state (kill mid-run → reaps).
2. Both scenarios pass in-ns and **fail loudly** if probes regress (e.g. reintroducing ICMP into `overall` → B fails).
3. Post-run: `ip link | grep nmsim` empty, `/etc/netns` empty.
4. Zero new `sf-str: allow`.

## Run

```bash
sudo ./scripts/netns-golden.sh           # both scenarios
sudo ./scripts/netns-golden.sh --scenario A
```

Manual only: never `iptables` on dev host — VM or netns, always.
