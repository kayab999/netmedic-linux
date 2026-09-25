#!/bin/bash
# Soak sampler (Sprint 1 background work): hourly resource snapshot of the
# headless daemon for the 72h soak. Any long-lived machine counts.
#
# Install:  (crontab -l; echo "0 * * * * /path/to/netmedic-linux/scripts/soak_sample.sh") | crontab -
# Analyze:  python3 -c "import csv,sys; rows=list(csv.DictReader(open('$HOME/.local/state/netmedic/soak.csv'))); ..."
#           flat slopes on rss_kb/fds/threads (audit/log bytes grow by design).
set -u

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/netmedic"
OUT="$STATE_DIR/soak.csv"
TS="$(date -u +%FT%TZ)"
PID=""

if [ -f "$STATE_DIR/ipc.pid" ]; then
    PID="$(tr -dc '0-9' < "$STATE_DIR/ipc.pid" 2>/dev/null || true)"
fi
if [ -z "$PID" ] || [ ! -d "/proc/$PID" ]; then
    PID="$(pgrep -f "netmedic --headless" 2>/dev/null | head -n 1 || true)"
fi

if [ -z "$PID" ] || [ ! -d "/proc/$PID" ]; then
    status="down"
    rss=""; fds=""; threads=""; uptime_s=""
else
    status="up"
    rss="$(awk '/VmRSS/{print $2}' "/proc/$PID/status" 2>/dev/null || true)"
    fds="$(ls "/proc/$PID/fd" 2>/dev/null | wc -l)"
    threads="$(awk '/Threads/{print $2}' "/proc/$PID/status" 2>/dev/null || true)"
    uptime_s="$(awk '{print int($1)}' /proc/uptime 2>/dev/null || true)"
fi
audit_bytes=0; log_bytes=0
[ -f "$STATE_DIR/audit.log" ] && audit_bytes="$(stat -c %s "$STATE_DIR/audit.log" 2>/dev/null || echo 0)"
[ -f "$STATE_DIR/netmedic.log" ] && log_bytes="$(stat -c %s "$STATE_DIR/netmedic.log" 2>/dev/null || echo 0)"

if [ ! -f "$OUT" ]; then
    echo "ts,status,pid,rss_kb,fds,threads,uptime_s,audit_bytes,log_bytes" > "$OUT"
    chmod 600 "$OUT" 2>/dev/null || true
fi
echo "$TS,$status,${PID:-},$rss,$fds,$threads,$uptime_s,$audit_bytes,$log_bytes" >> "$OUT"
