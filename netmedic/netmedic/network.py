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
# Virtual adapters created by NetMedic only — never delete arbitrary iface names from state files.
_MEDIC_IFACE_RE = re.compile(r"^medic[0-9a-f]{6}$")
_IFACE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._@+-]+$")

from netmedic.models import NetResult, ResultCode
from netmedic.system import CommandRunner
from netmedic.config import Config

logger = logging.getLogger(__name__)


def _elevated_is_cancelled(res) -> bool:
    return res.returncode == 126 or "cancel" in (res.stderr or "").lower() or "dismissed" in (res.stderr or "").lower()

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

    @staticmethod
    def is_medic_virtual_iface(iface: str) -> bool:
        """True only for NetMedic-owned dummy names (medic + 6 hex digits)."""
        return isinstance(iface, str) and bool(_MEDIC_IFACE_RE.fullmatch(iface))

    @staticmethod
    def _sanitize_iface_list(raw) -> Set[str]:
        """Parse state payload and keep only valid medic* interface names."""
        if not isinstance(raw, list):
            return set()
        allowed: Set[str] = set()
        for item in raw:
            if NetworkMedic.is_medic_virtual_iface(item):
                allowed.add(item)
            else:
                logger.warning("Ignoring non-medic interface name in state: %r", item)
        return allowed

    def _save_state(self):
        """Persist created interface list to disk (mode 0600)."""
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            fd = os.open(str(self._state_file), flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(sorted(self._created_ifaces), handle)
            os.chmod(self._state_file, 0o600)
        except Exception as e:
            logger.error("Error saving interface state: %s", e)

    def _load_state(self):
        """Load created interfaces; reject non-medic names (poisoned state)."""
        if not self._state_file.exists():
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                ifaces = json.load(f)
                self._created_ifaces = self._sanitize_iface_list(ifaces)
        except Exception as e:
            logger.error("Error loading interface state: %s", e)

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _delete_medic_iface(iface: str) -> bool:
        """Delete a virtual iface only if its name matches the medic* allowlist."""
        if not NetworkMedic.is_medic_virtual_iface(iface):
            logger.error("Refusing to delete non-medic interface: %r", iface)
            return False
        res = CommandRunner.run_elevated("iface-del", {"iface": iface})
        return res.success

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
                raw = json.loads(path.read_text(encoding="utf-8"))
                for iface in self._sanitize_iface_list(raw):
                    self._delete_medic_iface(iface)
                path.unlink(missing_ok=True)
                logger.info("Reaped orphan interface state from PID %d", pid)
            except Exception as exc:
                logger.warning("Failed to reap orphan state %s: %s", path, exc)

    def _is_physical_interface(self, iface: str) -> bool:
        from netmedic.constants import VIRTUAL_IFACE_MARKERS
        return not any(marker in iface for marker in VIRTUAL_IFACE_MARKERS)

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
            if not self._delete_medic_iface(iface):
                failed.append(iface)
                with self._state_lock:
                    if self.is_medic_virtual_iface(iface):
                        self._created_ifaces.add(iface)

        self._save_state()

        return NetResult(
            "Cleanup",
            len(failed) == 0,
            "Cleanup completed" if not failed else f"Failed on: {failed}",
        )

    def _check_dns_resolution(self) -> tuple[bool, str]:
        """Delegate to shared probes (DIV-01 fix)."""
        from netmedic.probes import check_dns_resolution as shared_dns
        ok, per, host = shared_dns()
        return ok, host

    def _check_dns_resolution_detailed(self):
        from netmedic.probes import check_dns_resolution as shared_dns
        return shared_dns()

    def _check_internet_access(self) -> tuple[bool, str]:
        """Delegate to shared probes."""
        from netmedic.probes import check_internet_access as shared_inet
        ok, per, label = shared_inet()
        return ok, label

    def _check_internet_access_detailed(self):
        from netmedic.probes import check_internet_access as shared_inet
        return shared_inet()

    def _get_iface_ipv4(self, iface: str) -> Optional[str]:
        """Return first IPv4 address for iface, or None."""
        res = CommandRunner.run(["ip", "-4", "addr", "show", iface])
        if not res.success or not res.stdout:
            return None
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1].split("/")[0]
        return None

    def run_diagnostics(self) -> NetResult:
        """
        Realiza pruebas de conectividad (Ping, DNS, HTTP).
        
        Riesgo: Bajo (Solo lectura de red).
        Tiempo: 2s - 12s.
        Reversibilidad: N/A.
        """
        results = []
        gw_ok = True
        dns_ok = True
        net_ok = True

        gw_ip = self.get_gateway_ip()
        if gw_ip:
            ping_gw = CommandRunner.run(["ping", "-c", "2", "-W", "1", gw_ip])
            if ping_gw.success:
                results.append("Gateway Reachable")
                gw_ok = True
            else:
                results.append("Gateway Unreachable")
                gw_ok = False
        else:
            results.append("Gateway Not Found")
            gw_ok = False

        dns_ok, dns_per, dns_host = self._check_dns_resolution_detailed()
        results.append("DNS Resolution OK" if dns_ok else "DNS Resolution Failed")

        net_ok, net_per, net_label = self._check_internet_access_detailed()
        results.append("Internet Access OK" if net_ok else "No Internet Access")

        # Captive portal hint: gateway OK but TCP internet failed (DNS may still
        # "succeed" via a portal resolver — the common captive case).
        portal_hint = None
        if gw_ok and not net_ok:
            from netmedic.probes import check_captive_portal
            is_portal, hint = check_captive_portal()
            if is_portal:
                portal_hint = hint
                # Append hint to message for human display (optional)
                results.append("Captive portal hint")

        # L1: NM second-opinion (divergence signal, not verdict)
        nm_full, nm_details = None, "nm: skipped"
        try:
            from netmedic.probes import check_nm_connectivity
            nm_full, nm_details = check_nm_connectivity()
        except Exception:
            pass

        msg = " | ".join(results)
        success = gw_ok and dns_ok and net_ok
        # PR2 + R1: internet_ok is TCP-only; ICMP lives only in details. PARTIAL when TCP fail but ICMP ok.
        is_partial = False
        if gw_ok and dns_ok and not net_ok:
            # Check if ICMP succeeded while TCP failed
            icmp_ok = net_per.get("8.8.8.8:icmp") if isinstance(net_per, dict) else False
            if icmp_ok:
                is_partial = True
                # Distinct PARTIAL prefix for diagnostics vs repair (E4 detail)
                msg += " (Partial: TCP blocked, ICMP ok — firewall suspected)"
        # PR2: structured details dict, gateway_ok for skip_renew, no substring parsing
        details = {"gateway": gw_ip or "none", "gateway_ok": gw_ok, "dns_probe": dns_host or "none", "net_probe": net_label or "none", "per_probe": {"gw_ok": gw_ok, "dns_ok": dns_ok, "internet_ok": net_ok, "dns_per": dns_per, "net_per": net_per}, "nm": nm_details}
        # Divergence: NM says full but probes say fail → report
        if nm_full is True and not success:
            details["nm_divergence"] = f"NM reports {nm_details} but probes report FAIL — divergence signal"
        elif nm_full is False and success:
            details["nm_divergence"] = f"NM reports {nm_details} but probes report OK"
        if portal_hint:
            details["captive_portal_hint"] = portal_hint
            details["suggestion"] = "Gateway OK, WAN down → likely upstream/ISP/captive portal. Check router uplink, try http://connectivity-check.ubuntu.com"
        # Also keep string for log backward compat in data
        data = {"gateway": gw_ip, "gateway_ok": gw_ok, "dns_ok": dns_ok, "internet_ok": net_ok, "net_probe": net_label, "dns_probe": dns_host, "captive_portal": portal_hint, "nm": nm_details, "nm_full": nm_full}
        if success:
            code = ResultCode.OK
        elif is_partial:
            code = ResultCode.PARTIAL
        else:
            code = ResultCode.FAILED
        # For PARTIAL, success remains False (not fully healthy) but code distinguishes
        return NetResult("Diagnostics", success, msg, details=details, data=data, code=code)

    def _check_requirement(self, binary: str) -> bool:
        """Verifica si un binario necesario existe en el PATH."""
        exists = shutil.which(binary) is not None
        if not exists:
            logger.warning(f"Requerimiento faltante: '{binary}'. Algunas funciones estarán desactivadas.")
        return exists

    def flush_dns(self) -> NetResult:
        """
        Limpia la caché DNS de systemd-resolved. Verifies service still active post-flush.
        """
        if not self._check_requirement("resolvectl"):
            return NetResult("Flush DNS", False, "Missing 'resolvectl' (systemd-resolved not detected)", code=ResultCode.ERROR)

        if not CommandRunner.is_service_active("systemd-resolved"):
            return NetResult("Flush DNS", False, "systemd-resolved service is not active", code=ResultCode.ERROR)

        res = CommandRunner.run_elevated("flush-dns")
        if not res.success:
            if _elevated_is_cancelled(res):
                return NetResult("Flush DNS", False, "Authentication cancelled by user", details=res.stderr, code=ResultCode.CANCELLED)
            if "helper-missing" in (res.stderr or "").lower():
                return NetResult("Flush DNS", False, res.stderr, details=res.stderr, code=ResultCode.ERROR)
            return NetResult("Flush DNS", False, res.stderr or res.stdout or "flush failed", details=res.stderr, code=ResultCode.FAILED)
        # Post-condition: service still active after flush (cheap verification)
        if not CommandRunner.is_service_active("systemd-resolved"):
            return NetResult("Flush DNS", False, "Cache flush succeeded but systemd-resolved became inactive", details="service down post-flush", code=ResultCode.FAILED)
        # Informational DNS probe (does not determine success; upstream may still be down)
        dns_ok, host = self._check_dns_resolution()
        details = {"post_flush_dns_ok": dns_ok, "probe_host": host or "failed"}
        # EXECUTED: command exited 0 but effect not yet verified (network still may be down)
        return NetResult(
            "Flush DNS",
            True,
            "executed (resolvectl) — effect not yet verified",
            details=details,
            code=ResultCode.EXECUTED,
        )

    def change_dns(self, server: str = "1.1.1.1") -> NetResult:
        """
        Configura el DNS IPv4 de la conexión NetworkManager activa.
        Verifies resolver config post-change.

        Riesgo: Medio (Modifica resolución de nombres).
        Tiempo: 2s - 5s.
        Reversibilidad: Sí (Restaurar DHCP o valores previos).
        """
        if not _DNS_IP_RE.match(server):
            return NetResult("Change DNS", False, f"DNS inválido: {server}", code=ResultCode.ERROR)

        if not self._check_requirement("nmcli"):
            return NetResult("Change DNS", False, "NetworkManager (nmcli) no disponible", code=ResultCode.ERROR)

        active = self._get_active_nm_connection()
        if not active:
            return NetResult("Change DNS", False, "No active NetworkManager connection found", code=ResultCode.ERROR)

        conn_name, device = active
        res = CommandRunner.run_elevated(
            "change-dns",
            {"server": server, "connection": conn_name},
        )
        if not res.success:
            if _elevated_is_cancelled(res):
                return NetResult("Change DNS", False, "Authentication cancelled by user", details=res.stderr, code=ResultCode.CANCELLED)
            return NetResult("Change DNS", False, res.stderr or res.stdout, details=res.stderr, code=ResultCode.FAILED)
        # Post-condition: verify connection shows new DNS (best-effort)
        verify = CommandRunner.run(["nmcli", "con", "show", conn_name])
        if verify.success and server not in verify.stdout:
            logger.warning("DNS change verification: %s not found in con show for %s", server, conn_name)
            return NetResult("Change DNS", False, f"DNS set reported success but {server} not in {conn_name} config", details=verify.stdout[:500], code=ResultCode.FAILED)
        dns_ok, host = self._check_dns_resolution()
        details = {"post_change_dns_ok": dns_ok, "probe": host or "none"}
        return NetResult("Change DNS", True, f"DNS set to {server} on {conn_name} ({device})", details=details, code=ResultCode.OK)

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
            return NetResult("Renew IP", False, "No interface detected", code=ResultCode.ERROR)
        if not _IFACE_TOKEN_RE.fullmatch(iface):
            return NetResult("Renew IP", False, f"Refusing invalid interface name: {iface!r}", code=ResultCode.ERROR)

        ip_before = self._get_iface_ipv4(iface)

        # Prefer NetworkManager; fall back to dhclient via helper verb modes.
        nm_error = ""
        nm_success = False
        last_res = None
        if shutil.which("nmcli"):
            res = CommandRunner.run_elevated(
                "renew-ip", {"iface": iface, "mode": "nmcli"}
            )
            last_res = res
            if res.success:
                nm_success = True
            else:
                nm_error = res.stderr or res.stdout
                if _elevated_is_cancelled(res):
                    return NetResult("Renew IP", False, "Authentication cancelled by user", details=res.stderr, code=ResultCode.CANCELLED)

        if nm_success:
            ip_after = self._get_iface_ipv4(iface)
            # Post-condition: interface should have IPv4 if we could read before
            if ip_after is None and ip_before is not None:
                return NetResult(
                    "Renew IP",
                    False,
                    f"IP renewal reported success but {iface} has no IPv4 address",
                    details={"before": ip_before, "after": None},
                    code=ResultCode.FAILED,
                )
            gw_ip = self.get_gateway_ip()
            gw_ok = None
            if gw_ip:
                ping = CommandRunner.run(["ping", "-c", "1", "-W", "2", gw_ip])
                gw_ok = ping.success
                if not ping.success:
                    logger.warning("Post-renew gateway ping failed for %s gw=%s", iface, gw_ip)
            if ip_before and ip_after and ip_before != ip_after:
                msg = f"IP changed {ip_before} -> {ip_after}"
            elif ip_after:
                msg = f"IP retained {ip_after} (lease reapplied)" if ip_before else f"IP {ip_after}"
            else:
                msg = "executed on {} — IP not verifiable".format(iface)
            details = {"iface": iface, "old_ip": ip_before, "new_ip": ip_after, "changed": ip_before != ip_after if ip_before and ip_after else False, "gateway_ok": gw_ok}
            return NetResult("Renew IP", True, msg, details=details, data={"iface": iface, "ip_before": ip_before, "ip_after": ip_after}, code=ResultCode.EXECUTED)

        # nmcli missing or failed -> try dhclient fallback (PR5: do not auto-escalate if nmcli failed due to cancel; handled above)
        if not shutil.which("dhclient"):
            detail = nm_error or "dhclient not available"
            if last_res and _elevated_is_cancelled(last_res):
                return NetResult("Renew IP", False, "Authentication cancelled by user", details=detail, code=ResultCode.CANCELLED)
            if last_res and "helper-missing" in (last_res.stderr or "").lower():
                return NetResult("Renew IP", False, "Privileged helper not installed (helper-missing). Run: ./scripts/install-polkit-policy.sh", details=detail, code=ResultCode.ERROR)
            return NetResult("Renew IP", False, f"DHCP renewal failed on {iface}", details=detail, code=ResultCode.ERROR)

        res = CommandRunner.run_elevated(
            "renew-ip", {"iface": iface, "mode": "dhclient"}, timeout=30
        )
        if not res.success:
            if _elevated_is_cancelled(res):
                return NetResult("Renew IP", False, "Authentication cancelled by user", details=res.stderr, code=ResultCode.CANCELLED)
            if "helper-missing" in (res.stderr or "").lower():
                return NetResult("Renew IP", False, "Privileged helper not installed (helper-missing). Run: ./scripts/install-polkit-policy.sh", details=res.stderr, code=ResultCode.ERROR)
            logger.error("DHCP renewal failed for %s: %s", iface, res.stderr)
            return NetResult(
                "Renew IP",
                False,
                f"DHCP renewal failed on {iface}. Try Infrastructure tab for a full stack reset.",
                details=res.stderr or nm_error,
                code=ResultCode.FAILED,
            )

        ip_after = self._get_iface_ipv4(iface)
        if ip_after is None and ip_before is not None:
            return NetResult(
                "Renew IP",
                False,
                f"dhclient reported success but {iface} has no IPv4",
                details={"before": ip_before},
                code=ResultCode.FAILED,
            )
        details = {"before": ip_before or "none", "after": ip_after or "none"}
        return NetResult("Renew IP", True, f"IP renewed on {iface}", details=details, data={"iface": iface, "ip_before": ip_before, "ip_after": ip_after}, code=ResultCode.EXECUTED)

    def reset_tcp_ip_stack(self) -> NetResult:
        """
        Reinicia el servicio NetworkManager. Verifies service active post-restart.
        
        Riesgo: Alto (Desconexión total temporal de todas las interfaces).
        Tiempo: 5s - 15s.
        Reversibilidad: Sí (El servicio vuelve a subir automáticamente).
        """
        res = CommandRunner.run_elevated("reset-stack")
        if not res.success:
            if _elevated_is_cancelled(res):
                return NetResult("Reset Stack", False, "Authentication cancelled by user", details=res.stderr, code=ResultCode.CANCELLED)
            return NetResult("Reset Stack", False, res.stderr or res.stdout or "Stack reset failed", details=res.stderr, code=ResultCode.FAILED)
        # Post-condition: wait briefly for NetworkManager to become active (PR6 SEM-04 poll)
        import time
        for _ in range(15):
            if CommandRunner.is_service_active("NetworkManager"):
                return NetResult("Reset Stack", True, "Stack reset successful (NetworkManager active)", code=ResultCode.OK)
            time.sleep(1)
        return NetResult("Reset Stack", False, "Stack restart reported success but NetworkManager not active", details="service still inactive after 15s", code=ResultCode.FAILED)

    def restart_adapter(self) -> NetResult:
        """
        Baja y sube la interfaz de red por defecto. Verifies operstate UP post-cycle.
        
        Riesgo: Medio (Corte de conexión en la interfaz específica).
        Tiempo: 2s - 5s.
        Reversibilidad: Sí (Subir manualmente con 'ip link set UP').
        """
        iface = self.get_default_interface()
        if not iface:
            return NetResult("Restart Adapter", False, "No interface detected", code=ResultCode.ERROR)
        if not _IFACE_TOKEN_RE.fullmatch(iface):
            return NetResult("Restart Adapter", False, f"Refusing invalid interface name: {iface!r}", code=ResultCode.ERROR)

        res = CommandRunner.run_elevated("restart-adapter", {"iface": iface})
        if not res.success:
            if _elevated_is_cancelled(res):
                return NetResult("Restart Adapter", False, "Authentication cancelled by user", details=res.stderr, code=ResultCode.CANCELLED)
            return NetResult(
                "Restart Adapter",
                False,
                f"Failed to restart {iface}",
                details=res.stderr or res.stdout,
                code=ResultCode.FAILED,
            )
        # Post-condition: PR6 SEM-03 use ip -j link show operstate poll up to 5s
        import time, json
        operstate_ok = False
        last_out = ""
        for _ in range(5):
            ip_check = CommandRunner.run(["ip", "-j", "link", "show", iface])
            if ip_check.success:
                try:
                    data = json.loads(ip_check.stdout)
                    if data and isinstance(data, list):
                        state = data[0].get("operstate") or data[0].get("state") or ""
                        if state == "UP":
                            operstate_ok = True
                            last_out = ip_check.stdout[:500]
                            break
                except json.JSONDecodeError:
                    pass
                # Fallback to text parse  # sf-str: allow ip link output not localized, low-risk display parse TODO: remove when json path covers all kernels
                txt = CommandRunner.run(["ip", "-o", "link", "show", iface])
                if "state UP" in txt.stdout or "UP" in txt.stdout:  # sf-str: allow ip link output not localized, low-risk display parse TODO: json-only
                    operstate_ok = True
                    last_out = txt.stdout[:500]
                    break
                last_out = txt.stdout[:500]
            time.sleep(1)
        if not operstate_ok:
            return NetResult("Restart Adapter", False, f"Adapter {iface} not UP after restart", details=last_out[:300], code=ResultCode.FAILED)
        ip_after = self._get_iface_ipv4(iface)
        details = {"operstate": "UP", "ip": ip_after or "none"}
        return NetResult("Restart Adapter", True, f"Adapter {iface} restarted", details=details, code=ResultCode.OK)

    @staticmethod
    def read_firewall_status() -> str:
        """Read UFW state without initializing the NetworkMedic singleton."""
        res = CommandRunner.run(["ufw", "status"])
        if "inactive" in res.stdout.lower():  # sf-str: allow ufw output not localized, low-risk display parse
            return "OFF"
        if "active" in res.stdout.lower():  # sf-str: allow ufw output not localized, low-risk display parse
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
        res = CommandRunner.run_elevated("toggle-firewall", {"action": action})
        if not res.success:
            return NetResult(
                "Firewall",
                False,
                f"ufw {action} failed",
                details=res.stderr or res.stdout,
            )

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
        res = CommandRunner.run_elevated("iface-add-dummy", {"iface": iface})
        if res.success:
            with self._state_lock:
                self._created_ifaces.add(iface)
                self._save_state()
            return NetResult("Virtual Adapter", True, f"Created: {iface}")
        return NetResult("Virtual Adapter", False, res.stderr)
