#!/usr/bin/env bash
# Install system-owned NetMedic helper + polkit policy (requires sudo).
# Phase D: helper must not depend on the git checkout or user venv path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_POLICY="$ROOT/assets/com.kayab.netmedic.policy"
DEST_POLICY="/usr/share/polkit-1/actions/com.kayab.netmedic.policy"
LIB_DIR="/usr/lib/netmedic"
PKG_DIR="$LIB_DIR/netmedic"
SCRIPTS_DIR="$LIB_DIR/scripts"
LIBEXEC_DIR="/usr/libexec/netmedic"
HELPER_WRAPPER="$LIBEXEC_DIR/helper"
VPN_INSTALLER_SRC="$ROOT/netmedic/netmedic/data/vpn/openvpn-install.sh"

if [[ ! -f "$SRC_POLICY" ]]; then
  echo "Missing policy source: $SRC_POLICY" >&2
  exit 1
fi

HELPER_SRC="$ROOT/netmedic/netmedic"
if [[ ! -f "$HELPER_SRC/helper_main.py" || ! -f "$HELPER_SRC/helper_verbs.py" || ! -f "$HELPER_SRC/validators.py" || ! -f "$HELPER_SRC/action_catalog.py" ]]; then
  echo "Missing helper sources under $HELPER_SRC" >&2
  exit 1
fi
# F2: the installer is vendored; never download it at install or run time.
if [[ ! -f "$VPN_INSTALLER_SRC" ]]; then
  echo "Missing vendored VPN installer: $VPN_INSTALLER_SRC" >&2
  exit 1
fi

# F3: fixed system interpreter — never bake a venv/pyenv/conda python into
# a root-executed wrapper (threat-model item 13).
PYTHON3="/usr/bin/python3"
if [[ ! -x "$PYTHON3" ]]; then
  echo "Error: $PYTHON3 not found/executable (refusing venv interpreter)" >&2
  exit 1
fi
# Keep version in sync with netmedic/netmedic/helper_verbs.py HELPER_VERSION.
# L4: absolute path + validated interpreter — works from any cwd, no PATH lookup.
HELPER_VERSION="$("$PYTHON3" -c 'import re,sys;print(re.search(r"HELPER_VERSION\s*=\s*\"([^\"]+)\"", open(sys.argv[1]).read()).group(1))' "$HELPER_SRC/helper_verbs.py")"

echo "Installing system helper package → $PKG_DIR (python $PYTHON3, version $HELPER_VERSION)"
sudo mkdir -p "$PKG_DIR"
# Minimal package: only helper modules (stdlib deps, M4: +validators).
sudo tee "$PKG_DIR/__init__.py" >/dev/null <<EOF
"""System-installed NetMedic helper package (elevation only)."""
__version__ = "$HELPER_VERSION"
EOF
sudo install -o root -g root -m 0644 "$HELPER_SRC/helper_verbs.py" "$PKG_DIR/helper_verbs.py"
sudo install -o root -g root -m 0644 "$HELPER_SRC/helper_main.py" "$PKG_DIR/helper_main.py"
sudo install -o root -g root -m 0644 "$HELPER_SRC/validators.py" "$PKG_DIR/validators.py"
sudo install -o root -g root -m 0644 "$HELPER_SRC/action_catalog.py" "$PKG_DIR/action_catalog.py"
# F2: vendored installer at the fixed path the helper resolves by script_id.
echo "Installing vendored VPN installer → $SCRIPTS_DIR/openvpn-install.sh"
sudo install -d -o root -g root -m 0755 "$SCRIPTS_DIR"
sudo install -o root -g root -m 0644 "$VPN_INSTALLER_SRC" "$SCRIPTS_DIR/openvpn-install.sh"
# Launcher for -I mode (-I ignores PYTHONPATH, so sys.path is set explicitly).
sudo tee "$LIB_DIR/_run_helper.py" >/dev/null <<EOF
"""Root-owned launcher: fixed sys.path, isolated mode safe."""
import sys
sys.path.insert(0, "$LIB_DIR")
from netmedic.helper_main import main
if __name__ == "__main__":
    raise SystemExit(main())
EOF
sudo chmod 0644 "$LIB_DIR/_run_helper.py"
sudo chown -R root:root "$LIB_DIR"

echo "Installing privileged helper wrapper → $HELPER_WRAPPER"
sudo mkdir -p "$LIBEXEC_DIR"
sudo tee "$HELPER_WRAPPER" >/dev/null <<EOF
#!/bin/sh
# NetMedic privileged helper — system-owned (no repo/venv dependency)
# Fixed interpreter + isolated mode; path is set by _run_helper.py.
exec $PYTHON3 -I -s $LIB_DIR/_run_helper.py "\$@"
EOF
sudo chmod 0755 "$HELPER_WRAPPER"
sudo chown root:root "$HELPER_WRAPPER"

echo "Installing polkit policy → $DEST_POLICY"
sudo cp "$SRC_POLICY" "$DEST_POLICY"
sudo chmod 644 "$DEST_POLICY"
sudo chown root:root "$DEST_POLICY"

# F4: pkexec 0.105 (Ubuntu 22.04/24.04) selects the action by exec.path only,
# ignoring exec.argv1. A single shared helper path therefore collapses every
# action into the first enumerated one. Install one root-owned wrapper per verb
# so each polkit action has a unique, stable exec.path.
echo "Installing per-verb helper wrappers → $LIBEXEC_DIR"
sudo "$PYTHON3" - "$DEST_POLICY" "$LIBEXEC_DIR" "$HELPER_WRAPPER" <<'PY'
import os
import sys
import xml.etree.ElementTree as ET

policy_path, libexec_dir, helper_wrapper = sys.argv[1:4]
root = ET.parse(policy_path).getroot()
for action in root.iter("action"):
    action_id = action.get("id", "")
    if not action_id.startswith("com.kayab.netmedic."):
        continue
    verb = action_id.rsplit(".", 1)[-1]
    wrapper_path = os.path.join(libexec_dir, "helper-" + verb)
    with open(wrapper_path, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\\n")
        handle.write('exec ' + helper_wrapper + ' ' + verb + ' "$@"\\n')
    os.chmod(wrapper_path, 0o755)
    os.chown(wrapper_path, 0, 0)
PY
# Remove stale wrappers that no longer correspond to a policy action.
for existing in "$LIBEXEC_DIR"/helper-*; do
    [ -e "$existing" ] || continue
    verb="${existing##*/helper-}"
    if ! grep -q "com.kayab.netmedic.$verb" "$DEST_POLICY"; then
        sudo rm -f "$existing"
    fi
done

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
echo "  Scripts: $SCRIPTS_DIR"
echo "  Policy:  $DEST_POLICY"
