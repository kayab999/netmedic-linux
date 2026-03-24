#!/bin/bash
set -e

# Colores para UX
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== NetMedic Linux Installer (V4 Release) ===${NC}"

# 1. Detección de Distro y Dependencias de Sistema
echo -e "${BLUE}[1/5] Detectando sistema y dependencias nativas...${NC}"

if [ -f /etc/debian_version ]; then
    echo "Sistema detectado: Debian/Ubuntu/Mint"
    pkgs="python3-venv python3-dev libgirepository1.0-dev libcairo2-dev gir1.2-gtk-3.0"
    install_cmd="sudo apt-get install -y $pkgs"
elif [ -f /etc/fedora-release ]; then
    echo "Sistema detectado: Fedora/RHEL"
    pkgs="python3-devel gobject-introspection-devel cairo-gobject-devel gtk3"
    install_cmd="sudo dnf install -y $pkgs"
elif [ -f /etc/arch-release ]; then
    echo "Sistema detectado: Arch Linux/Manjaro"
    pkgs="python gobject-introspection cairo gtk3"
    install_cmd="sudo pacman -S --noconfirm $pkgs"
else
    echo -e "${RED}Distro no soportada automáticamente.${NC}"
    echo "Asegúrate de tener instalados los headers de GTK3 y GObject."
    install_cmd="true"
fi

echo "Instalando dependencias de sistema (se requiere root)..."
$install_cmd

# 2. Configuración del Entorno Virtual
echo -e "${BLUE}[2/5] Configurando Python Virtual Environment...${NC}"
if [ -d "venv" ]; then
    rm -rf venv
fi
python3 -m venv venv
source venv/bin/activate

# Actualizar herramientas de construcción
pip install --upgrade pip wheel setuptools

# 3. Instalación de la Aplicación
echo -e "${BLUE}[3/5] Compilando e instalando NetMedic...${NC}"
# Instala PyGObject explícitamente primero para evitar errores de build
pip install PyGObject
# Instala el paquete actual en modo editable
pip install -e .

# 4. Integración de Escritorio (.desktop)
echo -e "${BLUE}[4/5] Creando lanzador de escritorio...${NC}"
INSTALL_DIR=$(pwd)

cat <<EOF > netmedic.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=NetMedic
Comment=Linux Network Diagnostics & Repair Tool
Exec=$INSTALL_DIR/venv/bin/python -m netmedic.app
Icon=utilities-system-monitor
Path=$INSTALL_DIR
Terminal=false
Categories=System;Network;
EOF

# Instalar en el usuario actual
mkdir -p ~/.local/share/applications
cp netmedic.desktop ~/.local/share/applications/
chmod +x ~/.local/share/applications/netmedic.desktop

echo -e "${GREEN}=== Instalación Completada ===${NC}"
echo -e "1. Ejecuta desde terminal: ${BLUE}./venv/bin/python -m netmedic.app${NC}"
echo -e "2. O busca 'NetMedic' en tu menú de aplicaciones."
