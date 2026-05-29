# NetMedic Linux 🛡️

**NetMedic** es una herramienta profesional de diagnóstico, reparación y gestión de infraestructura de red para sistemas Linux. Diseñada bajo los principios de **Soberanía Técnica**, combina una interfaz moderna (GTK3) con un motor de ejecución endurecido.

## 🚀 Características Principales (v1.0.0)

- **Smart Repair**: Diagnóstico y reparación automatizada.
- **Gestión de Infraestructura**: Control de Firewall y stack TCP/IP.
- **Ciclo de Vida Robusto**: Gestión centralizada de estados y cleanup garantizado (v1.0.0).
- **Operador VPN (Angristan)**: Instalación con verificación de integridad.
- **Seguridad Endurecida**:
  - **Cleanup Garantizado**: Gestión centralizada de recursos (PID, Lock, Socket).
  - **Privacidad de Logs**: Redacción de secretos.
  - **Elevación Segura**: Polkit/pkexec.

## 📦 Instalación y Uso (AppImage / Binario)

NetMedic se distribuye como binario autónomo.

1. **Descarga**: Obtén `NetMedic-x86_64.AppImage` desde la pestaña de Releases.
2. **Ejecución**:
   ```bash
   chmod +x NetMedic-x86_64.AppImage
   ./NetMedic-x86_64.AppImage
   ```

## 🛠️ Desarrollo e Instalación desde Fuente

```bash
git clone https://github.com/kayab999/netmedic-linux.git && cd netmedic-linux
./install.sh
./venv/bin/python -m netmedic.app
```

## 📖 Documentación Adicional
- [Manual de Usuario Detallado](docs/MANUAL.md)
- [Historial de Cambios](CHANGELOG.md)

---
**Veredicto Técnico**: Certified for v1.0.0 Release.
