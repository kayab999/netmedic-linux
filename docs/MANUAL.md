# Manual de Usuario - NetMedic Linux 🛡️

Esta guía proporciona instrucciones detalladas para el uso profesional y seguro de **NetMedic**.

## 1. Introducción
NetMedic es una herramienta diseñada para usuarios que necesitan diagnosticar y reparar problemas de red comunes en Linux, además de gestionar servidores VPN de forma automatizada y segura.

## 2. Operaciones de Reparación Básica (Tab 1)
Estas acciones son **no destructivas** y seguras para la mayoría de los casos.

- **Check Connectivity**: Realiza pings de prueba al gateway y a servicios de internet (Google DNS/Cloudflare) para determinar el origen de un fallo de conexión.
- **Flush DNS**: Limpia la caché del servicio `systemd-resolved`. Útil cuando puedes navegar por IP pero no por nombre de dominio.
- **Renew IP Address**: Fuerza la renovación del contrato DHCP de la interfaz de red activa.

## 3. Operaciones de Infraestructura (Tab 2)
**Atención**: Estas acciones requieren privilegios de administrador (`pkexec`) y pueden causar desconexiones momentáneas.

- **Reset TCP/IP Stack**: Reinicia el servicio **NetworkManager**. Esto reinicia todas las conexiones de red del sistema.
- **Toggle Firewall (UFW)**: Activa o desactiva el firewall del sistema. Asegúrate de conocer tus reglas de entrada antes de activarlo.
- **Gestión de VPN (Angristan)**:
  - **Instalar**: Descarga y configura un servidor OpenVPN. El sistema verificará el hash SHA256 antes de instalar para garantizar tu seguridad.
  - **Add Client**: Crea un nuevo certificado para un usuario/dispositivo.
  - **Revoke Client**: Invalida un certificado existente para denegar el acceso al servidor.

## 4. Seguridad y Logs
NetMedic registra todas sus acciones en un archivo de log rotativo:
`~/.local/state/netmedic/netmedic.log`

- **Redacción de Logs**: Por seguridad, NetMedic ocultará automáticamente cualquier contraseña o token que aparezca en los argumentos de los comandos ejecutados.
- **Limpieza de Sistema**: Al cerrar la aplicación, NetMedic eliminará automáticamente cualquier interfaz virtual creada para pruebas (`medicXX`).

## 5. Solución de Problemas
- **pkexec Error (126/127)**: Significa que cancelaste el diálogo de autenticación. NetMedic reactivará los botones para que puedas reintentar.
- **SHA256 Mismatch**: Si el script de VPN falla en la verificación de integridad, NetMedic detendrá la operación. Esto protege tu sistema de ataques remotos o archivos corruptos.

---
**NetMedic Team** - 2026.
