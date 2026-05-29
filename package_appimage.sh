#!/bin/bash
set -e

# Configuración
APP_NAME="NetMedic"
BUILD_DIR="NetMedic.AppDir"

echo "🔨 Iniciando empaquetado AppImage para ..."

# 1. Build del binario con PyInstaller (Standalone)
./build_standalone.sh

# 2. Limpiar build previo
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR/usr/bin
mkdir -p $BUILD_DIR/usr/share/applications
mkdir -p $BUILD_DIR/usr/share/icons/hicolor/scalable/apps

# 3. Copiar binario y assets
cp dist/netmedic $BUILD_DIR/usr/bin/netmedic
cp netmedic.desktop $BUILD_DIR/
cp netmedic.png $BUILD_DIR/usr/share/icons/hicolor/scalable/apps/netmedic.png

# 4. Crear AppRun
cat <<'EOF_RUN' > $BUILD_DIR/AppRun
#!/bin/sh
exec usr/bin/netmedic "$@"
EOF_RUN
chmod +x $BUILD_DIR/AppRun

# 5. Generar AppImage (requiere appimagetool en el PATH)
if command -v appimagetool &> /dev/null; then
    appimagetool $BUILD_DIR NetMedic-x86_64.AppImage
    echo "✅ AppImage generado: NetMedic-x86_64.AppImage"
else
    echo "⚠️ appimagetool no encontrado. La carpeta NetMedic.AppDir está lista."
    echo "Puedes ejecutar: appimagetool NetMedic.AppDir para crear el AppImage."
fi
