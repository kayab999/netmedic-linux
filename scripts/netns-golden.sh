#!/usr/bin/env bash
# netns-golden.sh — hermetic netmedic-sim v0 harness
# Creates two netns + veth, runs golden replay inside client ns.
# Footprint host = 0 after trap EXIT.
# Requires: ip, nft, python3, pytest, cap NET_ADMIN (sudo).
set -euo pipefail

RUNID="$$"
NS_R="nmsim-${RUNID}-r"
NS_C="nmsim-${RUNID}-c"
VETH_R="nmsim-${RUNID}-rc"
VETH_C="nmsim-${RUNID}-c"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/netmedic/sim"
STATE_FILE="${STATE_DIR}/${RUNID}.json"
SCENARIO="${1:-all}"  # all | A | B

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root (sudo $0)" >&2
  exit 1
fi

for bin in ip nft python3; do
  if ! command -v "$bin" >/dev/null; then
    echo "Missing $bin" >&2
    exit 1
  fi
done

PYTEST_BIN="./venv/bin/python"
if [[ ! -x "$PYTEST_BIN" ]]; then
  echo "Missing $PYTEST_BIN (create venv and pip install -e netmedic/)" >&2
  exit 1
fi
# Fail loud if skipif stomped pytest.mark.netns (rc1 collected 0).
n_netns=$("$PYTEST_BIN" -m pytest --collect-only -q -m netns tests/test_golden_replay_ns.py 2>/dev/null | grep -c '::' || true)
if [[ "${n_netns:-0}" -lt 2 ]]; then
  echo "netns marker stomped? collected ${n_netns:-0} with -m netns (want >=2)" >&2
  exit 1
fi

cleanup() {
  set +e
  echo "[netns-golden] teardown $RUNID" >&2
  # Kill micro-dns if running
  pkill -f "micro_dns.*${NS_R}" 2>/dev/null || true
  ip netns del "$NS_R" 2>/dev/null || true
  ip netns del "$NS_C" 2>/dev/null || true
  rm -rf "/etc/netns/${NS_C}" 2>/dev/null || true
  rm -f "$STATE_FILE" 2>/dev/null || true
  # host veth auto-reaped with peer
}
trap cleanup EXIT

# Reap stale nmsim-* from previous crashed runs (pattern like medic reap)
mkdir -p "$STATE_DIR"
# Remove state files for dead PIDs
for f in "$STATE_DIR"/*.json; do
  [[ -f "$f" ]] || continue
  pid=$(basename "$f" .json)
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "[netns-golden] reap stale $f" >&2
    rm -f "$f"
    # Try to delete any lingering ns with that pid prefix
    for ns in $(ip netns list 2>/dev/null | grep "nmsim-${pid}-" || true); do
      ip netns del "$ns" 2>/dev/null || true
      rm -rf "/etc/netns/$ns" 2>/dev/null || true
    done
  fi
done

# Record state for reap (mirrors network.py created_ifaces pattern)
mkdir -p "$(dirname "$STATE_FILE")"
echo "{\"runid\": \"$RUNID\", \"ns_r\": \"$NS_R\", \"ns_c\": \"$NS_C\", \"scenario\": \"$SCENARIO\"}" > "$STATE_FILE"
chmod 600 "$STATE_FILE"

echo "[netns-golden] setup $RUNID scenario=$SCENARIO" >&2

# Create namespaces
ip netns add "$NS_R"
ip netns add "$NS_C"
mkdir -p "/etc/netns/${NS_C}"
echo "nameserver 192.0.2.1" > "/etc/netns/${NS_C}/resolv.conf"

# Create veth pair and move
ip link add "$VETH_R" type veth peer name "$VETH_C"
ip link set "$VETH_R" netns "$NS_R"
ip link set "$VETH_C" netns "$NS_C"

# Router ns: LAN + loopback + WAN dummy IPs
ip netns exec "$NS_R" ip link set lo up
ip netns exec "$NS_R" ip link set "$VETH_R" up
ip netns exec "$NS_R" ip addr add 192.0.2.1/24 dev "$VETH_R"
# Dummy IPs for probes — kernel owns them, RST on :80
ip netns exec "$NS_R" ip addr add 8.8.8.8/32 dev lo
ip netns exec "$NS_R" ip addr add 1.1.1.1/32 dev lo

# Client ns: IP + route
ip netns exec "$NS_C" ip link set lo up
ip netns exec "$NS_C" ip link set "$VETH_C" up
ip netns exec "$NS_C" ip addr add 192.0.2.2/24 dev "$VETH_C"
ip netns exec "$NS_C" ip route add default via 192.0.2.1 dev "$VETH_C"

# Verify gateway reachable before fault injection
if ! ip netns exec "$NS_C" ping -c1 -W1 192.0.2.1 >/dev/null; then
  echo "Gateway not reachable after setup" >&2
  exit 1
fi

# Scenario-specific fault
if [[ "$SCENARIO" == "A" || "$SCENARIO" == "all" ]]; then
  # Scenario A will be tested as -k test_golden_wan_drop
  ip netns exec "$NS_R" nft add table inet nmsim 2>/dev/null || true
  ip netns exec "$NS_R" nft add chain inet nmsim input { type filter hook input priority 0 \; } 2>/dev/null || true
  ip netns exec "$NS_R" nft add rule inet nmsim input ip daddr {8.8.8.8,1.1.1.1} icmp type echo-request drop 2>/dev/null || true
  ip netns exec "$NS_R" nft add rule inet nmsim input ip daddr {8.8.8.8,1.1.1.1} tcp dport 80 drop 2>/dev/null || true
  ip netns exec "$NS_R" nft add rule inet nmsim input ip daddr 1.1.1.1 tcp dport 443 drop 2>/dev/null || true
  # No DNS listener in A (resolv.conf -> 192.0.2.1). Do not DROP udp/53:
  # blackhole makes getent wait the full CommandRunner timeout (was 30s x 2).
fi

if [[ "$SCENARIO" == "B" ]]; then
  # Scenario B: micro-DNS up, no nft drop (TCP RST does blocking, ICMP ok)
  # Flush any previous nft
  ip netns exec "$NS_R" nft flush ruleset 2>/dev/null || true
  # Start micro DNS in router ns background
  ip netns exec "$NS_R" nohup python3 "$(dirname "$0")/../tools/netmedic-sim/micro_dns.py" >/tmp/nmsim-${RUNID}-dns.log 2>&1 &
  sleep 0.5
fi

echo "[netns-golden] running golden replay in $NS_C (NETMEDIC_SIM_NS=1)" >&2

# Run pytest inside client ns
if [[ "$SCENARIO" == "B" ]]; then
  ip netns exec "$NS_C" env NETMEDIC_SIM_NS=1 NETMEDIC_SIM_SCENARIO=B ./venv/bin/python -m pytest -m netns -v tests/test_golden_replay_ns.py -k test_golden_icmp_ok_tcp_blocked
else
  # Default: both scenarios (A + B if --scenario all, but B needs micro DNS)
  # For 'all', run A first, then restart B
  ip netns exec "$NS_C" env NETMEDIC_SIM_NS=1 NETMEDIC_SIM_SCENARIO=A ./venv/bin/python -m pytest -m netns -v tests/test_golden_replay_ns.py::test_golden_wan_drop
  if [[ "$SCENARIO" == "all" ]]; then
    # Reconfigure for B
    ip netns exec "$NS_R" nft flush ruleset 2>/dev/null || true
    ip netns exec "$NS_R" nohup python3 "$(dirname "$0")/../tools/netmedic-sim/micro_dns.py" >/tmp/nmsim-${RUNID}-dns.log 2>&1 &
    sleep 0.5
    ip netns exec "$NS_C" env NETMEDIC_SIM_NS=1 NETMEDIC_SIM_SCENARIO=B ./venv/bin/python -m pytest -m netns -v tests/test_golden_replay_ns.py::test_golden_icmp_ok_tcp_blocked
  fi
fi

echo "[netns-golden] done" >&2
