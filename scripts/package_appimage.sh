#!/bin/bash
# Package NetMedic as AppImage
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

APP_NAME="NetMedic"
BUILD_DIR="NetMedic.AppDir"

echo "Packaging ${APP_NAME} AppImage..."

"${REPO_ROOT}/scripts/build_binary.sh"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps"

cp dist/netmedic "$BUILD_DIR/usr/bin/netmedic"
sed -e "s|@EXEC@|netmedic|g" \
    assets/netmedic.desktop.in > "$BUILD_DIR/usr/share/applications/netmedic.desktop"
cp assets/netmedic.png "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/netmedic.png"
cp assets/netmedic.png "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/netmedic.png"

cat > "$BUILD_DIR/AppRun" <<'EOF'
#!/bin/sh
export GDK_BACKEND=x11,wayland
export NO_AT_BRIDGE=1
exec usr/bin/netmedic "$@"
EOF
chmod +x "$BUILD_DIR/AppRun"

if command -v appimagetool &>/dev/null; then
    appimagetool "$BUILD_DIR" NetMedic-x86_64.AppImage
    echo "AppImage created: NetMedic-x86_64.AppImage"
else
    echo "appimagetool not found. AppDir ready at ${BUILD_DIR}/"
    echo "Run: appimagetool NetMedic.AppDir"
fi