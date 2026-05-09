#!/bin/bash
# build_ai.sh - Genera binario completo con soporte de IA (Nandi Mini)
echo "Compilando NetMedic AI (Sovereign Runtime)..."

# Incluimos explícitamente el módulo netmedic_ai
pyinstaller --noconfirm --onefile --windowed \
 --name netmedic-ai \
 --collect-all netmedic \
 --collect-all netmedic_ai \
 --hidden-import llama_cpp \
 netmedic/netmedic/app.py

echo "Binario AI generado en /dist/netmedic-ai"
