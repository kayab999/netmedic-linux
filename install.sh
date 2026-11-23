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
PROFILE="desktop"
# M7: --yes means non-interactive (assume defaults, never prompt).
NONINTERACTIVE=0

usage() {
    echo "Usage: ./install.sh [--yes] [--skip-tests] [--with-ai] [--keep-venv] [--headless] [--profile=desktop|headless]"
}

for arg in "$@"; do
    case "$arg" in
        --yes) NONINTERACTIVE=1 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        --with-ai) INSTALL_AI=1 ;;
        --keep-venv) RECREATE_VENV=0 ;;
        --headless) PROFILE="headless" ;;
        --profile=*) PROFILE="${arg#--profile=}" ;;
        --profile)
            echo "Missing value for --profile" >&2
            usage
            exit 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $arg"; usage; exit 1 ;;
    esac
done

case "$PROFILE" in
    desktop|headless) ;;
    *) echo "Unknown profile: $PROFILE"; usage; exit 1 ;;
esac

echo -e "${BLUE}=== NetMedic Linux Installer (v1.9.0, profile: $PROFILE) ===${NC}"

echo -e "${BLUE}[0/6] Runtime dependency preflight...${NC}"
chmod +x scripts/check-deps.sh
./scripts/check-deps.sh --profile="$PROFILE"

echo -e "${BLUE}[1/6] Detecting system dependencies...${NC}"
if [ -f /etc/debian_version ]; then
    sudo apt-get update -qq || true
    # noble (24.04+) renamed the gir dev package; jammy (22.04) uses the 1.0 name.
    gir_dev="libgirepository-2.0-dev"
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        case "${VERSION_ID:-}" in
            22.04) gir_dev="libgirepository1.0-dev" ;;
        esac
    fi
    # policykit-1 was split into polkitd + pkexec on Ubuntu 24.04+; both
    # names exist on 22.04 too, so one list covers the supported releases.
    pkgs="python3-venv python3-dev iproute2 curl iputils-ping"
    if [ "$PROFILE" = "desktop" ]; then
        pkgs="$pkgs $gir_dev libcairo2-dev gir1.2-gtk-3.0 network-manager polkitd pkexec"
    fi
    install_cmd="sudo apt-get install -y $pkgs"
elif [ -f /etc/fedora-release ]; then
    # M7: Fedora package is 'polkit', not 'policykit' (no such package).
    pkgs="python3-devel iproute curl iputils"
    if [ "$PROFILE" = "desktop" ]; then
        pkgs="$pkgs gobject-introspection-devel cairo-gobject-devel gtk3 NetworkManager polkit"
    fi
    install_cmd="sudo dnf install -y $pkgs"
elif [ -f /etc/arch-release ]; then
    pkgs="python iproute2 curl iputils"
    if [ "$PROFILE" = "desktop" ]; then
        pkgs="$pkgs gobject-introspection cairo gtk3 networkmanager polkit"
    fi
    install_cmd="sudo pacman -S --noconfirm $pkgs"
else
    # LUCP Phase 2b: an unknown manager is not, by itself, fatal. Report it
    # and let the preflight decide whether the profile is already satisfied.
    echo -e "${RED}Unsupported distro for automatic dependency install.${NC}"
    echo "Install Python 3.10-3.13 and the profile dependencies manually, then re-run."
    echo "Headless profile needs only Python; desktop profile also needs GTK3,"
    echo "GObject introspection, NetworkManager and PolicyKit."
    install_cmd=""
fi

if [ -f /etc/debian_version ] && [ -n "${install_cmd:-}" ]; then
    sudo apt-get update -qq || true
fi

if [ -n "${install_cmd:-}" ]; then
    $install_cmd
else
    echo -e "${BLUE}Skipping automatic system package installation.${NC}"
fi

echo -e "${BLUE}[2/6] Creating virtual environment...${NC}"
if [ "$RECREATE_VENV" -eq 1 ]; then
    rm -rf venv
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
# M7: pin dev/test tools (were unpinned latest). Versions mirror
# requirements-dev.lock; keep in sync when bumping that file.
pip install --upgrade pip wheel setuptools
pip install "pytest==9.1.0" "pytest-cov==7.1.0" "ruff==0.15.12" "hypothesis==6.168.1"

echo -e "${BLUE}[3/6] Installing NetMedic core ($PROFILE profile)...${NC}"
if [ "$PROFILE" = "desktop" ]; then
    pip install -e "netmedic[gui]" --config-settings editable_mode=strict
    python -c "import netmedic.constants, netmedic.probes, netmedic.gui"
else
    pip install -e netmedic/ --config-settings editable_mode=strict
    python -c "import netmedic.constants, netmedic.probes, netmedic.runtime"
fi

# M7: --yes never prompts (previous code prompted unless --with-ai).
if [ "$INSTALL_AI" -eq 0 ] && [ "$NONINTERACTIVE" -eq 0 ] && [ -t 0 ]; then
    echo -e "${BLUE}Install AI module (optional)? [y/N]${NC}"
    read -r install_ai_answer
    if [[ "$install_ai_answer" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        INSTALL_AI=1
    fi
fi
if [ "$INSTALL_AI" -eq 1 ]; then
    echo -e "${BLUE}[3b/6] Installing AI pilot dependencies...${NC}"
    # M5: upstream renamed these for the GGML backend; the pre-rename
    # CUBLAS/VULKAN flag names are ignored, silently building CPU-only
    # wheels on GPU hosts.
    if command -v nvidia-smi &>/dev/null; then
        export CMAKE_ARGS="-DGGML_CUDA=on"
    elif [ -d /usr/include/vulkan ] || command -v vulkaninfo &>/dev/null; then
        export CMAKE_ARGS="-DGGML_VULKAN=on"
    fi
    pip install -e "netmedic_ai[runtime]"
    pip install -e "netmedic[ai]"
fi

echo -e "${BLUE}[4/6] Installing desktop artifacts (profile: $PROFILE)...${NC}"
if [ "$PROFILE" = "desktop" ]; then
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

# M7: install the system helper itself (helper lib + wrapper + policy).
# install.sh previously copied only the policy XML, so the installed policy
# pointed at a missing helper and every privileged action failed with 127
# while the installer still printed "Installation complete".
echo -e "${BLUE}Installing system helper (root-owned, sudo required)...${NC}"
if ! ./scripts/install-polkit-policy.sh; then
    echo -e "${RED}ERROR: system helper install failed — privileged actions will not work.${NC}"
    echo "Re-run: ./scripts/install-polkit-policy.sh (see output above)"
    exit 1
fi

ICON_THEME_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
for size in 48 128 256; do
    mkdir -p "${ICON_THEME_ROOT}/${size}x${size}/apps"
    cp assets/netmedic.png "${ICON_THEME_ROOT}/${size}x${size}/apps/netmedic.png"
done
gtk-update-icon-cache -f -t "${ICON_THEME_ROOT}" 2>/dev/null || true

DESKTOP_TMP="$(mktemp "${TMPDIR:-/tmp}/netmedic.desktop.XXXXXX")"
# M7: quote the Exec path — repo checkouts under directories with spaces
# previously produced a broken launcher.
sed -e "s|@EXEC@|\"${REPO_ROOT}/venv/bin/netmedic\"|g" \
    assets/netmedic.desktop.in > "$DESKTOP_TMP"
mkdir -p ~/.local/share/applications
cp "$DESKTOP_TMP" ~/.local/share/applications/netmedic.desktop
rm -f "$DESKTOP_TMP"
chmod +x ~/.local/share/applications/netmedic.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true

fi

SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SERVICE_DIR"
sed -e "s|@EXEC@|\"${REPO_ROOT}/venv/bin/netmedic\"|g" \
    assets/netmedic-headless.service.in > "${SERVICE_DIR}/netmedic-headless.service"
systemctl --user daemon-reload 2>/dev/null || true

if [ "$SKIP_TESTS" -eq 0 ]; then
    echo -e "${BLUE}[5/6] Running test suite...${NC}"
    if [ "$PROFILE" = "desktop" ]; then
        python -m pytest tests/ -q
    else
        python -m pytest tests/test_capabilities.py tests/test_status.py tests/test_probes.py tests/test_packaging_metadata.py -q
    fi
else
    echo -e "${BLUE}[5/6] Skipping test suite (--skip-tests).${NC}"
fi

echo -e "${GREEN}=== Installation complete ===${NC}"
echo -e "Run: ${BLUE}${REPO_ROOT}/venv/bin/netmedic${NC}"
echo -e "Or search for 'NetMedic' in your application menu."
echo -e "Headless daemon: ${BLUE}systemctl --user enable --now netmedic-headless.service${NC}"
echo -e "Uninstall: ${BLUE}${REPO_ROOT}/scripts/uninstall.sh${NC}"