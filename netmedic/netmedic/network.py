import logging
import random
import threading
import shutil
from typing import Set, List, Optional

from netmedic.models import NetResult, CommandResult
from netmedic.system import CommandRunner

logger = logging.getLogger(__name__)

class NetworkMedic:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(NetworkMedic, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        self._state_lock = threading.Lock()
        self._created_ifaces: Set[str] = set()
        self._initialized = True

    def get_default_interface(self) -> Optional[str]:
        """
        Detecta la interfaz de red activa por defecto.
        
        Riesgo: Bajo (Solo lectura).
        Tiempo: < 1s.
        Reversibilidad: N/A.
        """
        res = CommandRunner.run(["ip", "route", "show", "default"])
        if res.success and res.stdout:
            parts = res.stdout.split()
            try:
                dev_idx = parts.index("dev")
                return parts[dev_idx + 1]
            except (ValueError, IndexError):
                pass
        return None

    def get_gateway_ip(self) -> Optional[str]:
        """
        Detecta la IP del gateway por defecto.
        
        Riesgo: Bajo (Solo lectura).
        Tiempo: < 1s.
        """
        res = CommandRunner.run(["ip", "route", "show", "default"])
        if res.success and res.stdout:
            parts = res.stdout.split()
            try:
                via_idx = parts.index("via")
                return parts[via_idx + 1]
            except (ValueError, IndexError):
                pass
        return None

    def cleanup(self) -> NetResult:
        """
        Elimina interfaces virtuales creadas por NetMedic.
        
        Riesgo: Medio (Modifica interfaces).
        Tiempo: 1s - 5s.
        Reversibilidad: Sí (Se pueden volver a crear).
        """
        with self._state_lock:
            if not self._created_ifaces:
                return NetResult("Cleanup", True, "Nada que limpiar")
            to_clean = list(self._created_ifaces)
            self._created_ifaces.clear()

        failed = []
        for iface in to_clean:
            res = CommandRunner.run(["ip", "link", "del", iface], require_root=True)
            if not res.success:
                failed.append(iface)
                with self._state_lock: self._created_ifaces.add(iface)

        return NetResult("Cleanup", len(failed) == 0, 
                         "Limpieza completada" if not failed else f"Falló en: {failed}")

    def run_diagnostics(self) -> NetResult:
        """
        Realiza pruebas de conectividad (Ping, DNS, HTTP).
        
        Riesgo: Bajo (Solo lectura de red).
        Tiempo: 2s - 10s.
        Reversibilidad: N/A.
        """
        results = []
        
        gw_ip = self.get_gateway_ip()
        if gw_ip:
            ping_gw = CommandRunner.run(["ping", "-c", "2", "-W", "1", gw_ip])
            results.append("Gateway Reachable" if ping_gw.success else "Gateway Unreachable")
        else:
            results.append("Gateway Not Found")
        
        dns_res = CommandRunner.run(["getent", "hosts", "google.com"])
        results.append("DNS Resolution OK" if dns_res.success else "DNS Resolution Failed")

        net_res = CommandRunner.run(["curl", "-Is", "http://1.1.1.1"], timeout=5)
        results.append("Internet Access OK" if net_res.success else "No Internet Access")

        msg = " | ".join(results)
        return NetResult("Diagnostics", "Failed" not in msg and "Unreachable" not in msg and "Not Found" not in msg, msg)

    def _check_requirement(self, binary: str) -> bool:
        """Verifica si un binario necesario existe en el PATH."""
        exists = shutil.which(binary) is not None
        if not exists:
            logger.warning(f"Requerimiento faltante: '{binary}'. Algunas funciones estarán desactivadas.")
        return exists

    def flush_dns(self) -> NetResult:
        """
        Limpia la caché DNS de systemd-resolved.
        """
        if not self._check_requirement("resolvectl"):
            return NetResult("Flush DNS", False, "Falta 'resolvectl' (systemd-resolved no detectado)")

        if CommandRunner.is_service_active("systemd-resolved"):
            res = CommandRunner.run(["resolvectl", "flush-caches"], require_root=True)
            return NetResult("Flush DNS", res.success, "Caché systemd-resolved limpia" if res.success else res.stderr)
        
        return NetResult("Flush DNS", False, "El servicio systemd-resolved no está activo")

    def renew_ip(self) -> NetResult:
        """
        Solicita una nueva IP al servidor DHCP.
        
        Riesgo: Medio (Corte temporal de conexión).
        Tiempo: 5s - 20s.
        Reversibilidad: Sí (Se puede reasignar estáticamente o reintentar).
        """
        iface = self.get_default_interface()
        if not iface: return NetResult("Renew IP", False, "No se detectó interfaz")
        
        # Modern NetworkManager fallback
        if shutil.which("nmcli"):
            res = CommandRunner.run(["nmcli", "device", "reapply", iface], require_root=True)
            if res.success:
                return NetResult("Renew IP", True, f"IP renovada vía NetworkManager en {iface}")

        CommandRunner.run(["dhclient", "-r", iface], require_root=True, timeout=10)
        res = CommandRunner.run(["dhclient", iface], require_root=True, timeout=15)
        
        return NetResult("Renew IP", res.success, f"IP renovada en {iface}" if res.success else "Error en DHCP")

    def reset_tcp_ip_stack(self) -> NetResult:
        """
        Reinicia el servicio NetworkManager.
        
        Riesgo: Alto (Desconexión total temporal de todas las interfaces).
        Tiempo: 5s - 15s.
        Reversibilidad: Sí (El servicio vuelve a subir automáticamente).
        """
        res = CommandRunner.run(["systemctl", "restart", "NetworkManager"], require_root=True)
        return NetResult("Reset Stack", res.success, "Stack reiniciado" if res.success else res.stderr)

    def restart_adapter(self) -> NetResult:
        """
        Baja y sube la interfaz de red por defecto.
        
        Riesgo: Medio (Corte de conexión en la interfaz específica).
        Tiempo: 2s - 5s.
        Reversibilidad: Sí (Subir manualmente con 'ip link set UP').
        """
        iface = self.get_default_interface()
        if not iface: return NetResult("Restart Adapter", False, "No se detectó interfaz")
        
        CommandRunner.run(["ip", "link", "set", iface, "down"], require_root=True)
        res = CommandRunner.run(["ip", "link", "set", iface, "up"], require_root=True)
        
        return NetResult("Restart Adapter", res.success, f"Adaptador {iface} reiniciado" if res.success else "Error al levantar")

    def get_firewall_status(self) -> str:
        """
        Consulta el estado actual de UFW.
        """
        res = CommandRunner.run(["ufw", "status"])
        if "inactive" in res.stdout.lower(): return "OFF"
        if "active" in res.stdout.lower(): return "ON"
        return "Unknown"

    def toggle_firewall(self) -> NetResult:
        """
        Activa o desactiva el firewall UFW.
        
        Riesgo: Medio (Cambia política de seguridad del sistema).
        Tiempo: 1s - 3s.
        Reversibilidad: Sí (Toggle inverso).
        """
        current = self.get_firewall_status()
        action = "enable" if current == "OFF" else "disable"
        res = CommandRunner.run(["ufw", action], require_root=True)
        return NetResult("Firewall", res.success, f"Firewall ahora: {'ON' if action == 'enable' else 'OFF'}")

    def create_virtual_adapter(self) -> NetResult:
        """
        Crea una interfaz de red dummy para pruebas.
        
        Riesgo: Bajo.
        Tiempo: < 1s.
        Reversibilidad: Sí (Usar método cleanup()).
        """
        iface = f"medic{random.randint(10,99)}"
        res = CommandRunner.run(["ip", "link", "add", iface, "type", "dummy"], require_root=True)
        if res.success:
            with self._state_lock: self._created_ifaces.add(iface)
            return NetResult("Virtual Adapter", True, f"Creado: {iface}")
        return NetResult("Virtual Adapter", False, res.stderr)
