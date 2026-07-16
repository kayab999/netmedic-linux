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

rm -rf build dist netmedic_run
pyinstaller netmedic.spec --clean --noconfirm

echo "Binary ready: ${REPO_ROOT}/dist/netmedic"