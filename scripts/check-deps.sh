#!/bin/bash
# NetMedic runtime dependency preflight
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

REQUIRED_BINS=(python3 nmcli ip pkexec curl ping)
OPTIONAL_BINS=(resolvectl dhclient rfkill ufw systemctl gtk-launch)

missing_required=()
missing_optional=()

for bin_name in "${REQUIRED_BINS[@]}"; do
    if ! command -v "$bin_name" &>/dev/null; then
        missing_required+=("$bin_name")
    fi
done

for bin_name in "${OPTIONAL_BINS[@]}"; do
    if ! command -v "$bin_name" &>/dev/null; then
        missing_optional+=("$bin_name")
    fi
done

if [ "${#missing_required[@]}" -gt 0 ]; then
    echo "Missing required tools: ${missing_required[*]}"
    exit 1
fi

if [ "${#missing_optional[@]}" -gt 0 ]; then
    echo "Optional tools not found (some features may be limited): ${missing_optional[*]}"
fi

PY_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
PY_MAJOR="$(echo "$PY_VERSION" | cut -d. -f1)"
PY_MINOR="$(echo "$PY_VERSION" | cut -d. -f2)"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
    echo "Python 3.8+ required, found $PY_VERSION"
    exit 1
fi

echo "Dependency preflight passed (Python $PY_VERSION)."