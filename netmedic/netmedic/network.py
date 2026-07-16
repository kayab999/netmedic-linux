import logging
import os
import re
import uuid
import threading
import shutil
import json
from typing import List, Optional, Set, Tuple

_DNS_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)

from netmedic.models import NetResult
from netmedic.system import CommandRunner
from netmedic.config import Config

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
        if self._initialized:
            return
        self._state_lock = threading.Lock()
        self._state_file = Config.get_state_dir() / f"created_ifaces.{os.getpid()}.json"
        self._created_ifaces: Set[str] = set()

        self._reap_orphan_iface_state()
        self._load_state()
        if self._created_ifaces:
            logger.info(f"Detectadas interfaces residuales de sesión previa: {self._created_ifaces}. Limpiando...")
            self.cleanup()

        self._initialized = True

    def _save_state(self):
        """Guarda la lista de interfaces creadas en disco."""
        try:
            with open(self._state_file, "w") as f:
                json.dump(list(self._created_ifaces), f)
            os.chmod(self._state_file, 0o600)
        except Exception as e:
            logger.error(f"Error guardando estado de interfaces: {e}")

    def _load_state(self):
        """Carga la lista de interfaces creadas desde el disco."""
        if not self._state_file.exists():
            return
        try:
            with open(self._state_file, "r") as f:
                ifaces = json.load(f)
                self._created_ifaces = set(ifaces)
        except Exception as e:
            logger.error(f"Error cargando estado de interfaces: {e}")

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _reap_orphan_iface_state(self):
        """Remove virtual interfaces tracked by dead NetMedic processes."""
        state_dir = Config.get_state_dir()
        for path in state_dir.glob("created_ifaces.*.json"):
            try:
                pid = int(path.name.split(".")[1])
            except (ValueError, IndexError):
                continue
            if pid == os.getpid() or self._is_process_alive(pid):
                continue
            try:
                ifaces = json.loads(path.read_text())
                for iface in ifaces:
                    CommandRunner.run(["ip", "link", "del", iface], require_root=True)
                path.unlink(missing_ok=True)
                logger.info("Reaped orphan interface state from PID %d", pid)
            except Exception as exc:
                logger.warning("Failed to reap orphan state %s: %s", path, exc)

    def _is_physical_interface(self, iface: str) -> bool:
        virtual_markers = (
            "docker", "br-", "veth", "vnet", "virbr",
            "tun", "wg", "tailscale", "nm-", "lo",
        )
        return not any(marker in iface for marker in virtual_markers)

    def _get_active_nm_connection(self) -> Optional[Tuple[str, str]]:
        """Return (connection_name, device) aligned with the default-route interface."""
        res = CommandRunner.run(["nmcli", "-t", "-f", "NAME,DEVICE", "con", "show", "--active"])
        if not res.success or not res.stdout.strip():
            return None

        matches: List[Tuple[str, str]] = []
        for line in res.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] and parts[1]:
                matches.append((parts[0], parts[1]))

        iface = self.get_default_interface()
        if iface:
            for name, device in matches:
                if device == iface:
                    return (name, device)
        return matches[0] if matches else None

    def get_default_interface(self) -> Optional[str]:
        """
        Detecta la interfaz de red activa por defecto.
        Si no hay ruta por defecto (offline), intenta detectar una interfaz física disponible.
        
        Riesgo: Bajo (Solo lectura).
        Tiempo: < 1s.
        Reversibilidad: N/A.
        """
        # Intento 1: Ruta por defecto (Rápido y preciso si hay conexión)
        res = CommandRunner.run(["ip", "route", "show", "default"])
        if res.success and res.stdout:
            parts = res.stdout.split()
            try:
                dev_idx = parts.index("dev")
                return parts[dev_idx + 1]
            except (ValueError, IndexError):
                pass

        # Intento 2: Fallback - Buscar interfaz física que esté levantada (UP)
        # Filtramos loopback (lo) y interfaces virtuales comunes (docker, br-, vnet, etc)
        res = CommandRunner.run(["ip", "-o", "link", "show", "up"])
        if res.success and res.stdout:
            for line in res.stdout.splitlines():
                parts = line.split(':')
                if len(parts) < 2:
                    continue
                iface = parts[1].strip()
                
                if not self._is_physical_interface(iface):
                    continue
                
                # Si llegamos aquí, es una interfaz física probable (eth0, wlan0, enp3s0, etc)
                return iface

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
                return NetResult("Cleanup", True, "Nothing to clean")
            to_clean = list(self._created_ifaces)
            self._created_ifaces.clear()

        failed = []
        for iface in to_clean:
            res = CommandRunner.run(["ip", "link", "del", iface], require_root=True)
            if not res.success:
                failed.append(iface)
                with self._state_lock:
                    self._created_ifaces.add(iface)

        # Actualizar persistencia tras limpieza
        self._save_state()

        return NetResult("Cleanup", len(failed) == 0, 
                         "Cleanup completed" if not failed else f"Failed on: {failed}")

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
            return NetResult("Flush DNS", False, "Missing 'resolvectl' (systemd-resolved not detected)")

        if CommandRunner.is_service_active("systemd-resolved"):
            res = CommandRunner.run(["resolvectl", "flush-caches"], require_root=True)
            return NetResult("Flush DNS", res.success, "systemd-resolved cache flushed" if res.success else res.stderr)
        
        return NetResult("Flush DNS", False, "systemd-resolved service is not active")

    def change_dns(self, server: str = "1.1.1.1") -> NetResult:
        """
        Configura el DNS IPv4 de la conexión NetworkManager activa.

        Riesgo: Medio (Modifica resolución de nombres).
        Tiempo: 2s - 5s.
        Reversibilidad: Sí (Restaurar DHCP o valores previos).
        """
        if not _DNS_IP_RE.match(server):
            return NetResult("Change DNS", False, f"DNS inválido: {server}")

        if not self._check_requirement("nmcli"):
            return NetResult("Change DNS", False, "NetworkManager (nmcli) no disponible")

        active = self._get_active_nm_connection()
        if not active:
            return NetResult("Change DNS", False, "No active NetworkManager connection found")

        conn_name, device = active
        mod_res = CommandRunner.run(
            [
                "nmcli", "con", "mod", conn_name,
                "ipv4.dns", server,
                "ipv4.ignore-auto-dns", "yes",
            ],
            require_root=True,
        )
        if not mod_res.success:
            return NetResult("Change DNS", False, mod_res.stderr)

        up_res = CommandRunner.run(["nmcli", "con", "up", conn_name], require_root=True)
        if not up_res.success:
            return NetResult("Change DNS", False, up_res.stderr)

        return NetResult("Change DNS", True, f"DNS set to {server} on {conn_name} ({device})")

    def renew_ip(self) -> NetResult:
        """
        Solicita una nueva IP al servidor DHCP.
        Requests a new IP from the DHCP server.
        
        Risk: Medium (Temporary connection cut).
        Time: 5s - 20s.
        Reversibility: Yes (Can be statically reassigned or retried).
        """
        iface = self.get_default_interface()
        if not iface:
            return NetResult("Renew IP", False, "No interface detected")
        
        # Modern NetworkManager fallback
        nm_error = ""
        if shutil.which("nmcli"):
            res = CommandRunner.run(["nmcli", "device", "reapply", iface], require_root=True)
            if res.success:
                return NetResult("Renew IP", True, f"IP renewed via NetworkManager on {iface}")
            nm_error = res.stderr or res.stdout

        if not shutil.which("dhclient"):
            detail = nm_error or "dhclient not available"
            return NetResult("Renew IP", False, f"DHCP renewal failed on {iface}", details=detail)

        release_res = CommandRunner.run(["dhclient", "-r", iface], require_root=True, timeout=10)
        if not release_res.success:
            logger.warning("dhclient release failed on %s: %s", iface, release_res.stderr)
        res = CommandRunner.run(["dhclient", iface], require_root=True, timeout=15)
        
        if not res.success:
            logger.error("DHCP renewal failed for %s: %s", iface, res.stderr)
            return NetResult(
                "Renew IP",
                False,
                f"DHCP renewal failed on {iface}. Try Infrastructure tab for a full stack reset.",
                details=res.stderr,
            )

        return NetResult("Renew IP", True, f"IP renewed on {iface}")

    def reset_tcp_ip_stack(self) -> NetResult:
        """
        Reinicia el servicio NetworkManager.
        
        Riesgo: Alto (Desconexión total temporal de todas las interfaces).
        Tiempo: 5s - 15s.
        Reversibilidad: Sí (El servicio vuelve a subir automáticamente).
        """
        res = CommandRunner.run(["systemctl", "restart", "NetworkManager"], require_root=True)
        return NetResult("Reset Stack", res.success, "Stack reset successful" if res.success else res.stderr)

    def restart_adapter(self) -> NetResult:
        """
        Baja y sube la interfaz de red por defecto.
        
        Riesgo: Medio (Corte de conexión en la interfaz específica).
        Tiempo: 2s - 5s.
        Reversibilidad: Sí (Subir manualmente con 'ip link set UP').
        """
        iface = self.get_default_interface()
        if not iface:
            return NetResult("Restart Adapter", False, "No interface detected")
        
        down = CommandRunner.run(["ip", "link", "set", iface, "down"], require_root=True)
        if not down.success:
            return NetResult("Restart Adapter", False, f"Failed to bring {iface} down", details=down.stderr)
        res = CommandRunner.run(["ip", "link", "set", iface, "up"], require_root=True)
        return NetResult(
            "Restart Adapter",
            res.success,
            f"Adapter {iface} restarted" if res.success else "Failed to bring interface up",
            details=res.stderr if not res.success else None,
        )

    @staticmethod
    def read_firewall_status() -> str:
        """Read UFW state without initializing the NetworkMedic singleton."""
        res = CommandRunner.run(["ufw", "status"])
        if "inactive" in res.stdout.lower():
            return "OFF"
        if "active" in res.stdout.lower():
            return "ON"
        return "Unknown"

    def get_firewall_status(self) -> str:
        return self.read_firewall_status()

    def toggle_firewall(self) -> NetResult:
        """
        Activa o desactiva el firewall UFW.
        
        Riesgo: Medio (Cambia política de seguridad del sistema).
        Tiempo: 1s - 3s.
        Reversibilidad: Sí (Toggle inverso).
        """
        current = self.get_firewall_status()
        if current not in ("ON", "OFF"):
            return NetResult("Firewall", False, f"Cannot determine UFW status (got: {current})")
        action = "enable" if current == "OFF" else "disable"
        res = CommandRunner.run(["ufw", action], require_root=True)
        if not res.success:
            return NetResult("Firewall", False, f"ufw {action} failed", details=res.stderr)

        # Validación post-operación: No confiar solo en el exit code
        final_status = self.get_firewall_status()
        expected = "ON" if action == "enable" else "OFF"
        
        if final_status == expected:
            return NetResult("Firewall", True, f"Firewall is now: {final_status}")
        else:
            return NetResult("Firewall", False, f"Failed to toggle firewall. Current state: {final_status}")

    def create_virtual_adapter(self) -> NetResult:
        """
        Crea una interfaz de red dummy para pruebas.
        
        Riesgo: Bajo.
        Tiempo: < 1s.
        Reversibilidad: Sí (Usar método cleanup()).
        """
        iface = f"medic{uuid.uuid4().hex[:6]}"
        res = CommandRunner.run(["ip", "link", "add", iface, "type", "dummy"], require_root=True)
        if res.success:
            with self._state_lock:
                self._created_ifaces.add(iface)
                self._save_state()
            return NetResult("Virtual Adapter", True, f"Created: {iface}")
        return NetResult("Virtual Adapter", False, res.stderr)
