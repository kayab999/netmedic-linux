#!/bin/bash
# NetMedic PyInstaller build (one-file binary)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

APP_NAME="NetMedic"
VENV_DIR="${REPO_ROOT}/venv"

echo "--- Building ${APP_NAME} v1.0.0 ---"

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Run ./install.sh first."
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

rm -rf build dist netmedic_run

pip install -q wheel pyinstaller pillow
pyinstaller netmedic.spec --clean

if [ -f dist/netmedic ]; then
    cat > netmedic_run <<EOF
#!/bin/bash
export GDK_BACKEND=x11,wayland
export NO_AT_BRIDGE=1
exec "${REPO_ROOT}/dist/netmedic" "\$@"
EOF
    chmod +x netmedic_run
    echo "--- Build successful: dist/netmedic ---"
    echo "Test with: ./netmedic_run"
else
    echo "Build failed: dist/netmedic not found."
    exit 1
fi