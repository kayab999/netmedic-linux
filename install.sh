#!/bin/bash
# NetMedic Linux — source installer
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

SKIP_TESTS=0
RECREATE_VENV=1
INSTALL_AI=0

usage() {
    echo "Usage: ./install.sh [--yes] [--skip-tests] [--with-ai] [--keep-venv]"
}

for arg in "$@"; do
    case "$arg" in
        --yes) INSTALL_AI=0 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        --with-ai) INSTALL_AI=1 ;;
        --keep-venv) RECREATE_VENV=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $arg"; usage; exit 1 ;;
    esac
done

echo -e "${BLUE}=== NetMedic Linux Installer (v1.5.0) ===${NC}"

echo -e "${BLUE}[0/6] Runtime dependency preflight...${NC}"
chmod +x scripts/check-deps.sh
./scripts/check-deps.sh

echo -e "${BLUE}[1/6] Detecting system dependencies...${NC}"
if [ -f /etc/debian_version ]; then
    sudo apt-get update -qq || true
    pkgs="python3-venv python3-dev libgirepository-2.0-dev libcairo2-dev gir1.2-gtk-3.0 network-manager iproute2 curl iputils-ping policykit-1"
    install_cmd="sudo apt-get install -y $pkgs"
elif [ -f /etc/fedora-release ]; then
    pkgs="python3-devel gobject-introspection-devel cairo-gobject-devel gtk3 NetworkManager iproute curl iputils policykit"
    install_cmd="sudo dnf install -y $pkgs"
elif [ -f /etc/arch-release ]; then
    pkgs="python gobject-introspection cairo gtk3 networkmanager iproute2 curl iputils polkit"
    install_cmd="sudo pacman -S --noconfirm $pkgs"
else
    echo -e "${RED}Unsupported distro for automatic dependency install.${NC}"
    echo "Install Python 3.8+, GTK3, NetworkManager, and GObject introspection headers manually."
    install_cmd="true"
fi
$install_cmd

echo -e "${BLUE}[2/6] Creating virtual environment...${NC}"
if [ "$RECREATE_VENV" -eq 1 ]; then
    rm -rf venv
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip wheel setuptools pytest ruff

echo -e "${BLUE}[3/6] Installing NetMedic core...${NC}"
pip install PyGObject
pip install -e netmedic/ --config-settings editable_mode=strict

if [ "$INSTALL_AI" -eq 0 ] && [ -t 0 ]; then
    echo -e "${BLUE}Install AI module (optional)? [y/N]${NC}"
    read -r install_ai_answer
    if [[ "$install_ai_answer" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        INSTALL_AI=1
    fi
fi
if [ "$INSTALL_AI" -eq 1 ]; then
    echo -e "${BLUE}[3b/6] Installing AI pilot dependencies...${NC}"
    if command -v nvidia-smi &>/dev/null; then
        export CMAKE_ARGS="-DLLAMA_CUBLAS=on"
    elif [ -d /usr/include/vulkan ] || command -v vulkaninfo &>/dev/null; then
        export CMAKE_ARGS="-DLLAMA_VULKAN=on"
    fi
    pip install -e "netmedic_ai[runtime]"
    pip install -e "netmedic[ai]"
fi

echo -e "${BLUE}[4/6] Installing polkit policy, icon, and desktop launcher...${NC}"
# Polkit only loads actions from system paths on most distros — user XDG paths
# are not sufficient. Prefer system install; fall back to sudo.
POLKIT_SYSTEM="/usr/share/polkit-1/actions/com.kayab.netmedic.policy"
if [ -w /usr/share/polkit-1/actions ] 2>/dev/null; then
    cp assets/com.kayab.netmedic.policy "$POLKIT_SYSTEM"
elif command -v sudo >/dev/null 2>&1; then
    echo -e "${BLUE}Installing polkit policy system-wide (sudo required)...${NC}"
    sudo cp assets/com.kayab.netmedic.policy "$POLKIT_SYSTEM" || {
        echo -e "${RED}WARNING: Failed to install polkit policy to $POLKIT_SYSTEM${NC}"
        echo "Privileged IPC will fail until the policy is installed."
    }
else
    echo -e "${RED}WARNING: Cannot install polkit policy (no write access / no sudo).${NC}"
fi
if command -v pkaction >/dev/null 2>&1; then
    if pkaction --action-id com.kayab.netmedic.flush-dns >/dev/null 2>&1; then
        echo -e "${GREEN}Polkit actions registered (com.kayab.netmedic.*).${NC}"
    else
        echo -e "${RED}WARNING: pkaction does not see com.kayab.netmedic.flush-dns yet.${NC}"
        echo "You may need to re-login or restart polkit after installing the policy."
    fi
fi

ICON_THEME_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
for size in 48 128 256; do
    mkdir -p "${ICON_THEME_ROOT}/${size}x${size}/apps"
    cp assets/netmedic.png "${ICON_THEME_ROOT}/${size}x${size}/apps/netmedic.png"
done
gtk-update-icon-cache -f -t "${ICON_THEME_ROOT}" 2>/dev/null || true

DESKTOP_TMP="$(mktemp "${TMPDIR:-/tmp}/netmedic.desktop.XXXXXX")"
sed -e "s|@EXEC@|${REPO_ROOT}/venv/bin/netmedic|g" \
    assets/netmedic.desktop.in > "$DESKTOP_TMP"
mkdir -p ~/.local/share/applications
cp "$DESKTOP_TMP" ~/.local/share/applications/netmedic.desktop
rm -f "$DESKTOP_TMP"
chmod +x ~/.local/share/applications/netmedic.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true

SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SERVICE_DIR"
sed -e "s|@EXEC@|${REPO_ROOT}/venv/bin/netmedic|g" \
    assets/netmedic-headless.service.in > "${SERVICE_DIR}/netmedic-headless.service"
systemctl --user daemon-reload 2>/dev/null || true

if [ "$SKIP_TESTS" -eq 0 ]; then
    echo -e "${BLUE}[5/6] Running test suite...${NC}"
    python -m pytest tests/ -q
else
    echo -e "${BLUE}[5/6] Skipping test suite (--skip-tests).${NC}"
fi

echo -e "${GREEN}=== Installation complete ===${NC}"
echo -e "Run: ${BLUE}${REPO_ROOT}/venv/bin/netmedic${NC}"
echo -e "Or search for 'NetMedic' in your application menu."
echo -e "Headless daemon: ${BLUE}systemctl --user enable --now netmedic-headless.service${NC}"