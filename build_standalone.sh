#!/bin/bash
# build_standalone.sh - Genera binario solo con el núcleo de NetMedic
echo "Compilando NetMedic Standalone..."

# PyInstaller no debe incluir el módulo de IA
pyinstaller --noconfirm --onefile --windowed \
 --name netmedic \
 --collect-all netmedic \
 --exclude-module netmedic_ai \
 netmedic/netmedic/app.py

echo "Binario standalone generado en /dist/netmedic"
