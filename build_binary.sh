#!/bin/bash
# NetMedic Stable Build Script (The "Sovereign" Method)
set -e

APP_NAME="NetMedic"
VENV_DIR="/home/carlos/netmedic_linux/venv"

echo "--- 🛠️  Building $APP_NAME Final RC ---"

# 1. Asegurar que estamos en el venv y tenemos PyGObject instalado en el sistema también
# (PyInstaller necesita ver las libs del sistema para empaquetarlas)
source $VENV_DIR/bin/activate

# 2. Limpieza profunda
rm -rf build dist netmedic_run pyi_gi_runtime_hook.py

# 3. Build exhaustivo
echo "--- 📦 Running PyInstaller with GI-Fixes ---"
# Instalamos wheel para asegurar build correcto
pip install wheel pyinstaller pillow

pyinstaller netmedic.spec --clean

# 4. Crear el Lanzador de Integridad
if [ -f "dist/netmedic_bundle/netmedic" ]; then
    cat <<EOF > netmedic_run
#!/bin/bash
export GDK_BACKEND=x11,wayland
export NO_AT_BRIDGE=1
# Ejecutar el binario
"/home/carlos/netmedic_linux/dist/netmedic_bundle/netmedic" "\$@"
EOF
    chmod +x netmedic_run
    echo "--- ✅ Build Successful! ---"
    echo "Prueba ahora: ./netmedic_run"
else
    echo "❌ Error Crítico: El binario no se generó."
    exit 1
fi
