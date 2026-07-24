#!/usr/bin/env bash
# Install NetMedic polkit action definitions system-wide (requires sudo).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/assets/com.kayab.netmedic.policy"
DEST="/usr/share/polkit-1/actions/com.kayab.netmedic.policy"

if [[ ! -f "$SRC" ]]; then
  echo "Missing policy source: $SRC" >&2
  exit 1
fi

echo "Installing polkit policy to $DEST"
sudo cp "$SRC" "$DEST"
sudo chmod 644 "$DEST"

if command -v pkaction >/dev/null 2>&1; then
  if pkaction --action-id com.kayab.netmedic.flush-dns >/dev/null 2>&1; then
    echo "OK: polkit sees com.kayab.netmedic.flush-dns"
    pkaction 2>/dev/null | grep 'com.kayab.netmedic' || true
  else
    echo "WARNING: policy copied but pkaction does not list actions yet."
    echo "Try: systemctl restart polkit  (or re-login)"
    exit 2
  fi
else
  echo "WARNING: pkaction not found; cannot verify registration."
fi
