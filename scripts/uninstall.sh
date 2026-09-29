#!/usr/bin/env bash
# NetMedic Linux — uninstaller (M7: every install.sh artifact has a removal).
# Removes user-space artifacts always; system artifacts (helper, policy)
# require sudo and are skipped with a warning when sudo is unavailable.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== NetMedic Linux Uninstaller ===${NC}"

echo "Stopping user service (if present)..."
systemctl --user disable --now netmedic-headless.service 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/netmedic-headless.service"
systemctl --user daemon-reload 2>/dev/null || true

echo "Removing desktop launcher and icons..."
rm -f ~/.local/share/applications/netmedic.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
ICON_THEME_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
for size in 48 128 256; do
    rm -f "${ICON_THEME_ROOT}/${size}x${size}/apps/netmedic.png"
done
gtk-update-icon-cache -f -t "${ICON_THEME_ROOT}" 2>/dev/null || true

echo "Removing virtual environment..."
rm -rf "$REPO_ROOT/venv"

echo "Removing system helper and policy (sudo required)..."
if command -v sudo >/dev/null 2>&1; then
    sudo rm -f /usr/share/polkit-1/actions/com.kayab.netmedic.policy
    sudo rm -f /usr/libexec/netmedic/helper
    sudo rm -rf /usr/lib/netmedic
    echo -e "${GREEN}System artifacts removed.${NC}"
else
    echo -e "${RED}WARNING: no sudo — leaving system artifacts in place:${NC}"
    echo "  /usr/share/polkit-1/actions/com.kayab.netmedic.policy"
    echo "  /usr/libexec/netmedic/helper"
    echo "  /usr/lib/netmedic"
fi

echo -e "${GREEN}=== Uninstall complete ===${NC}"
echo "User state under ~/.local/state/netmedic and ~/.local/share/netmedic was kept."
echo "Remove it manually if you want a fully clean slate."
