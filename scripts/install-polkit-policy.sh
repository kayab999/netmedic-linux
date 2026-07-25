#!/usr/bin/env bash
# Install system-owned NetMedic helper + polkit policy (requires sudo).
# Phase D: helper must not depend on the git checkout or user venv path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_POLICY="$ROOT/assets/com.kayab.netmedic.policy"
DEST_POLICY="/usr/share/polkit-1/actions/com.kayab.netmedic.policy"
LIB_DIR="/usr/lib/netmedic"
PKG_DIR="$LIB_DIR/netmedic"
LIBEXEC_DIR="/usr/libexec/netmedic"
HELPER_WRAPPER="$LIBEXEC_DIR/helper"

if [[ ! -f "$SRC_POLICY" ]]; then
  echo "Missing policy source: $SRC_POLICY" >&2
  exit 1
fi

HELPER_SRC="$ROOT/netmedic/netmedic"
if [[ ! -f "$HELPER_SRC/helper_main.py" || ! -f "$HELPER_SRC/helper_verbs.py" ]]; then
  echo "Missing helper sources under $HELPER_SRC" >&2
  exit 1
fi

PYTHON3="$(command -v python3)"
if [[ -z "$PYTHON3" ]]; then
  echo "python3 not found" >&2
  exit 1
fi

echo "Installing system helper package → $PKG_DIR"
sudo mkdir -p "$PKG_DIR"
# Minimal package: only helper modules (stdlib deps).
sudo tee "$PKG_DIR/__init__.py" >/dev/null <<'EOF'
"""System-installed NetMedic helper package (elevation only)."""
__version__ = "1.5.0"
EOF
sudo cp "$HELPER_SRC/helper_verbs.py" "$PKG_DIR/helper_verbs.py"
sudo cp "$HELPER_SRC/helper_main.py" "$PKG_DIR/helper_main.py"
# Rewrite import for system layout (package is top-level 'netmedic' on sys.path).
# Sources already use `from netmedic.helper_verbs` — keep package name.
sudo chmod 644 "$PKG_DIR"/*.py
sudo chown -R root:root "$LIB_DIR"

echo "Installing privileged helper wrapper → $HELPER_WRAPPER"
sudo mkdir -p "$LIBEXEC_DIR"
sudo tee "$HELPER_WRAPPER" >/dev/null <<EOF
#!/bin/sh
# NetMedic privileged helper — system-owned (no repo/venv dependency)
# Note: do not use python -I here; isolated mode ignores PYTHONPATH.
export PYTHONPATH="${LIB_DIR}"
exec ${PYTHON3} -s -m netmedic.helper_main "\$@"
EOF
sudo chmod 755 "$HELPER_WRAPPER"
sudo chown root:root "$HELPER_WRAPPER"

echo "Installing polkit policy → $DEST_POLICY"
sudo cp "$SRC_POLICY" "$DEST_POLICY"
sudo chmod 644 "$DEST_POLICY"
sudo chown root:root "$DEST_POLICY"

echo "Verifying helper dry-run..."
if ! "$HELPER_WRAPPER" flush-dns --dry-run >/dev/null; then
  echo "ERROR: helper dry-run failed" >&2
  exit 1
fi
echo "OK: $HELPER_WRAPPER flush-dns --dry-run"

if command -v pkaction >/dev/null 2>&1; then
  if pkaction --action-id com.kayab.netmedic.flush-dns >/dev/null 2>&1; then
    echo "OK: polkit sees com.kayab.netmedic.flush-dns"
    pkaction 2>/dev/null | grep 'com.kayab.netmedic' || true
  else
    echo "WARNING: policy copied but pkaction does not list actions yet."
    echo "Try: systemctl restart polkit  (or re-login)"
  fi
else
  echo "WARNING: pkaction not found; cannot verify registration."
fi

echo
echo "Install complete."
echo "  Helper:  $HELPER_WRAPPER"
echo "  Library: $PKG_DIR"
echo "  Policy:  $DEST_POLICY"
echo "Elevation auto-uses helper when present. Force legacy (tests only):"
echo "  NETMEDIC_USE_HELPER=0 NETMEDIC_ALLOW_LEGACY_ELEVATION=1"
