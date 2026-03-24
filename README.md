# NetMedic Linux 🛡️

**NetMedic** es una herramienta profesional de diagnóstico, reparación y gestión de infraestructura de red para sistemas Linux (Debian, Fedora, Arch). Diseñada bajo los principios de **Soberanía Técnica**, combina una interfaz moderna (GTK3/CustomTkinter) con un motor de ejecución endurecido y seguro.

## 🚀 Características Principales (v1.0.0-rc1)

- **Smart Repair**: Diagnóstico y reparación automatizada (DNS Flush, IP Renew).
- **Gestión de Infraestructura**: Control de Firewall (UFW) y reinicio del stack TCP/IP.
- **Operador VPN (Angristan)**: Instalación y gestión de servidores OpenVPN con **Verificación de Integridad SHA256**.
- **Seguridad Endurecida**:
  - **Cleanup Garantizado**: Limpieza de interfaces virtuales ante señales `SIGTERM/SIGINT`.
  - **Privacidad de Logs**: Redacción automática de secretos (passwords/tokens) en logs.
  - **Elevación Segura**: Integración con Polkit (`pkexec`) para evitar ejecutar la GUI como root.

## 📦 Instalación y Uso (AppImage / Binario)

NetMedic se distribuye ahora como un binario autónomo para máxima compatibilidad.

1. **Descarga**: Obtén el archivo `netmedic` o `NetMedic.AppImage` desde la pestaña de Releases.
2. **Ejecución**:
   ```bash
   chmod +x netmedic
   ./netmedic
   ```
3. **Lanzador de Escritorio**: Para integrar NetMedic en tu Dock o Menú, utiliza el archivo `netmedic.desktop` incluido en la raíz.

## 🛠️ Desarrollo e Instalación desde Fuente

Si deseas contribuir o ejecutar desde el código fuente:

```bash
# 1. Clonar y entrar al directorio
git clone https://github.com/user/netmedic_linux.git && cd netmedic_linux

# 2. Instalar dependencias de sistema y venv (Usar script unificado)
# (Requiere Python 3.8+, GTK3, PyGObject)
./install.sh 

# 3. Ejecutar
./venv/bin/python -m netmedic.app
```

## 📖 Documentación Adicional
- [Manual de Usuario Detallado](docs/MANUAL.md)
- [Notas de Versión (RC1)](RELEASE_NOTES.md)
- [Historial de Cambios](CHANGELOG.md)

---
**Veredicto Técnico**: Certified for v1.0.0-rc1 Release.
