#!/usr/bin/env bash
# Install NetMedic polkit policy + system helper wrapper (requires sudo).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/assets/com.kayab.netmedic.policy"
DEST="/usr/share/polkit-1/actions/com.kayab.netmedic.policy"
LIBEXEC_DIR="/usr/libexec/netmedic"
HELPER_WRAPPER="$LIBEXEC_DIR/helper"

if [[ ! -f "$SRC" ]]; then
  echo "Missing policy source: $SRC" >&2
  exit 1
fi

# Resolve the real netmedic-helper entrypoint (venv or PATH).
HELPER_BIN=""
if [[ -x "$ROOT/venv/bin/netmedic-helper" ]]; then
  HELPER_BIN="$ROOT/venv/bin/netmedic-helper"
elif command -v netmedic-helper >/dev/null 2>&1; then
  HELPER_BIN="$(command -v netmedic-helper)"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
  HELPER_BIN="$ROOT/venv/bin/python"
  HELPER_MODULE=1
else
  HELPER_BIN="$(command -v python3)"
  HELPER_MODULE=1
fi

echo "Installing privileged helper wrapper → $HELPER_WRAPPER"
sudo mkdir -p "$LIBEXEC_DIR"
if [[ "${HELPER_MODULE:-0}" -eq 1 ]]; then
  # Fallback: invoke package module (dev / incomplete console_scripts).
  sudo tee "$HELPER_WRAPPER" >/dev/null <<EOF
#!/bin/sh
# NetMedic privileged helper (module fallback)
export PYTHONPATH="${ROOT}/netmedic\${PYTHONPATH:+:\$PYTHONPATH}"
exec "${HELPER_BIN}" -m netmedic.helper_main "\$@"
EOF
else
  sudo tee "$HELPER_WRAPPER" >/dev/null <<EOF
#!/bin/sh
# NetMedic privileged helper → console script
exec "${HELPER_BIN}" "\$@"
EOF
fi
sudo chmod 755 "$HELPER_WRAPPER"
sudo chown root:root "$HELPER_WRAPPER" 2>/dev/null || true

echo "Installing polkit policy → $DEST"
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

echo "Helper installed. Elevation auto-uses helper when this path exists:"
echo "  $HELPER_WRAPPER"
echo "Force legacy: NETMEDIC_USE_HELPER=0"
echo "Force helper:  NETMEDIC_USE_HELPER=1"
