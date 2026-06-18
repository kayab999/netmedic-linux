#!/bin/bash
# Build standalone binary (core only, no AI module)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "Building NetMedic standalone binary..."

if [ -d venv ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

pyinstaller --noconfirm --onefile --windowed \
    --name netmedic \
    --collect-all netmedic \
    --exclude-module netmedic_ai \
    netmedic/netmedic/app.py

echo "Binary ready: ${REPO_ROOT}/dist/netmedic"