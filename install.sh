#!/bin/bash
# NetMedic Linux — source installer
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== NetMedic Linux Installer (v1.1.0) ===${NC}"

echo -e "${BLUE}[1/5] Detecting system dependencies...${NC}"
if [ -f /etc/debian_version ]; then
    pkgs="python3-venv python3-dev libgirepository-2.0-dev libcairo2-dev gir1.2-gtk-3.0"
    install_cmd="sudo apt-get install -y $pkgs"
elif [ -f /etc/fedora-release ]; then
    pkgs="python3-devel gobject-introspection-devel cairo-gobject-devel gtk3"
    install_cmd="sudo dnf install -y $pkgs"
elif [ -f /etc/arch-release ]; then
    pkgs="python gobject-introspection cairo gtk3"
    install_cmd="sudo pacman -S --noconfirm $pkgs"
else
    echo -e "${RED}Unsupported distro for automatic dependency install.${NC}"
    echo "Install Python 3.8+, GTK3, and GObject introspection headers manually."
    install_cmd="true"
fi
$install_cmd

echo -e "${BLUE}[2/5] Creating virtual environment...${NC}"
rm -rf venv
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip wheel setuptools pytest ruff

echo -e "${BLUE}[3/5] Installing NetMedic core...${NC}"
pip install PyGObject
pip install -e netmedic/ --config-settings editable_mode=strict

if [ -t 0 ]; then
    echo -e "${BLUE}Install AI module (optional)? [y/N]${NC}"
    read -r install_ai
else
    install_ai="n"
fi
if [[ "$install_ai" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo -e "${BLUE}[3b/5] Installing AI pilot dependencies...${NC}"
    if command -v nvidia-smi &>/dev/null; then
        export CMAKE_ARGS="-DLLAMA_CUBLAS=on"
    elif [ -d /usr/include/vulkan ] || command -v vulkaninfo &>/dev/null; then
        export CMAKE_ARGS="-DLLAMA_VULKAN=on"
    fi
    pip install -e "netmedic_ai[runtime]"
    pip install -e "netmedic[ai]"
fi

echo -e "${BLUE}[4/5] Installing icon and desktop launcher...${NC}"
ICON_THEME_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
for size in 48 128 256; do
    mkdir -p "${ICON_THEME_ROOT}/${size}x${size}/apps"
    cp assets/netmedic.png "${ICON_THEME_ROOT}/${size}x${size}/apps/netmedic.png"
done
gtk-update-icon-cache -f -t "${ICON_THEME_ROOT}" 2>/dev/null || true

sed -e "s|@EXEC@|${REPO_ROOT}/venv/bin/netmedic|g" \
    assets/netmedic.desktop.in > /tmp/netmedic.desktop
mkdir -p ~/.local/share/applications
cp /tmp/netmedic.desktop ~/.local/share/applications/netmedic.desktop
chmod +x ~/.local/share/applications/netmedic.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo -e "${BLUE}[5/5] Running test suite...${NC}"
python -m pytest tests/ -q

echo -e "${GREEN}=== Installation complete ===${NC}"
echo -e "Run: ${BLUE}${REPO_ROOT}/venv/bin/netmedic${NC}"
echo -e "Or search for 'NetMedic' in your application menu."