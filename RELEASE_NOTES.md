# Release Notes - NetMedic v1.0.0-rc1 (Sovereign Engineering Edition)

Este Release Candidate marca la transición de un prototipo funcional a una herramienta de infraestructura profesional y segura. Se han priorizado la integridad del sistema y la transparencia operativa.

## 🛡️ Seguridad y Resiliencia
- **Ancla de Confianza (Trust Anchor)**: Se ha implementado una verificación de integridad SHA256 para todos los scripts descargados de terceros. Esto previene ataques de Remote Code Execution (RCE) incluso si el repositorio remoto se ve comprometido.
- **Manejo de Señales**: NetMedic ahora escucha activamente las señales del sistema operativo (`SIGTERM`, `SIGINT`). Al recibirlas, detiene cualquier operación en curso y ejecuta una limpieza garantizada de interfaces virtuales para evitar la contaminación del host.
- **Privacidad de Logs**: Los comandos ejecutados con privilegios elevados ahora pasan por un filtro de redacción que protege sus credenciales, tokens y secretos de quedar expuestos en texto plano en el sistema de archivos.

## 🧑‍💻 Experiencia de Usuario (UX)
- **Manejo de Privilegios**: Se ha refinado la interacción con `pkexec`. El usuario ahora recibe feedback visual claro si cancela un diálogo de autenticación, y el sistema recupera su estado operativo de forma predecible sin bloquear la interfaz.
- **Timeouts Inteligentes**: Las tareas pesadas (como instalaciones de VPN) ahora tienen timeouts extendidos (5 minutos) para evitar fallos falsos en conexiones lentas o procesos de compilación.

## 🧪 Validación y QA
- Se han incluido tests de seguridad automáticos que validan el sistema de redacción de logs y la detección de alteraciones en scripts externos.
- Veredicto de Auditoría: **LISTO PARA PUBLICACIÓN PÚBLICA (RC1)**.

---
*KAYAB Senior Release Manager*
