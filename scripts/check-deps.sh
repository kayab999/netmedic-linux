#!/bin/bash
# NetMedic runtime dependency preflight
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PROFILE="desktop"
for arg in "$@"; do
    case "$arg" in
        --profile=*) PROFILE="${arg#--profile=}" ;;
        --profile) shift; PROFILE="${1:-desktop}" ;;
        -h|--help)
            echo "Usage: $0 [--profile=desktop|headless]"
            exit 0
            ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

case "$PROFILE" in
    desktop|headless) ;;
    *) echo "Unknown profile: $PROFILE" >&2; exit 2 ;;
esac

REQUIRED_MISSING=()
OPTIONAL_MISSING=()

if ! command -v python3 &>/dev/null; then
    REQUIRED_MISSING+=("python3")
fi

if command -v python3 &>/dev/null; then
    if ! python3 -m pip --version &>/dev/null; then
        REQUIRED_MISSING+=("python3-pip")
    fi
    if ! python3 -c "import venv" &>/dev/null; then
        REQUIRED_MISSING+=("python3-venv")
    fi
    PY_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
    PY_MAJOR="$(echo "$PY_VERSION" | cut -d. -f1)"
    PY_MINOR="$(echo "$PY_VERSION" | cut -d. -f2)"
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
        echo "Python 3.10+ required, found $PY_VERSION"
        exit 1
    fi
    if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -gt 13 ]; then
        echo "WARNING: Python $PY_VERSION is above the pinned 3.10-3.13 range (CI matrix). Continuing."
    fi
else
    PY_VERSION="unknown"
fi

for bin_name in nmcli ip pkexec curl ping resolvectl dhclient rfkill ufw systemctl; do
    if ! command -v "$bin_name" &>/dev/null; then
        OPTIONAL_MISSING+=("$bin_name")
    fi
done

if [ "${#REQUIRED_MISSING[@]}" -gt 0 ]; then
    echo "Missing required tools: ${REQUIRED_MISSING[*]}"
    exit 1
fi

if [ "${#OPTIONAL_MISSING[@]}" -gt 0 ]; then
    echo "Optional tools not found (some features may be limited): ${OPTIONAL_MISSING[*]}"
fi

if [ -f /etc/debian_version ]; then
    echo "Package manager: apt"
elif [ -f /etc/fedora-release ]; then
    echo "Package manager: dnf"
elif [ -f /etc/arch-release ]; then
    echo "Package manager: pacman"
elif [ -f /etc/SuSE-release ] || [ -f /etc/os-release ] && grep -qi suse /etc/os-release 2>/dev/null; then
    echo "Package manager: zypper"
else
    echo "Package manager: unknown (install system dependencies manually)"
fi

if [ "$PROFILE" = "desktop" ]; then
    if python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' &>/dev/null; then
        echo "GUI (GTK3/PyGObject): available"
    else
        echo "GUI (GTK3/PyGObject): not available yet (desktop profile can install it)"
    fi
    if command -v pkexec &>/dev/null && pkexec --version &>/dev/null; then
        echo "Privileged helper support: pkexec available"
    else
        echo "Privileged helper support: pkexec not found (desktop profile can install it)"
    fi
else
    echo "GUI (GTK3/PyGObject): not required for headless profile"
    echo "Privileged helper support: not installed by headless profile"
fi

echo "Dependency preflight passed for profile '$PROFILE' (Python ${PY_VERSION})."