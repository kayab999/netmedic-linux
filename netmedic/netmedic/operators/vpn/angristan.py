import logging
import os
import re
import hashlib
from pathlib import Path

from netmedic.models import CommandResult, NetResult
from netmedic.operators.vpn.base import VPNOperator, VPNClient
from netmedic.operators.base import OperatorStatus
from netmedic.config import Config
from netmedic.system import CommandRunner

logger = logging.getLogger(__name__)

class AngristanOperator(VPNOperator):
    """
    Implementación del operador VPN usando el script de Angristan.
    Commit Pinneado: 9c966d4 (para estabilidad garantizada).
    Referencia: https://github.com/angristan/openvpn-install
    """
    
    # URL apuntando a commit específico para evitar roturas por cambios upstream
    SCRIPT_URL = "https://raw.githubusercontent.com/angristan/openvpn-install/9c966d4/openvpn-install.sh"
    
    # Hash SHA256 del script oficial en el commit 9c966d4
    # Este valor es la 'Ancla de Confianza' del operador.
    EXPECTED_SHA256 = "65c3b53f652615598696ec062a4d3106540c43666f2722108ecf62a4b87e2f5b"

    # Ruta a la base de datos de certificados (Source of Truth)
    INDEX_TXT_PATH = "/etc/openvpn/server/easy-rsa/pki/index.txt"

    @property
    def name(self) -> str:
        return "OpenVPN (Angristan)"

    @property
    def slug(self) -> str:
        return "vpn-angristan"

    @property
    def description(self) -> str:
        return "Instalador y gestor de OpenVPN automatizado y seguro."

    def get_service_name(self) -> str:
        return "openvpn-server@server.service" 

    @property
    def script_path(self):
        return Config.get_operators_dir() / "openvpn-install.sh"

    def _hash_file_fd(self, fd: int) -> str:
        sha256_hash = hashlib.sha256()
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            sha256_hash.update(block)
        os.lseek(fd, 0, os.SEEK_SET)
        return sha256_hash.hexdigest()

    def _verify_integrity(self) -> bool:
        """SHA256 of the local installer must match the pinned expected digest."""
        if not self.script_path.exists():
            return False
        try:
            fd = os.open(str(self.script_path), os.O_RDONLY)
        except OSError as exc:
            logger.error("Cannot open VPN script for integrity check: %s", exc)
            return False
        try:
            actual_hash = self._hash_file_fd(fd)
            if actual_hash != self.EXPECTED_SHA256:
                logger.error(
                    "SHA256 mismatch for %s. Expected %s, got %s",
                    self.slug,
                    self.EXPECTED_SHA256,
                    actual_hash,
                )
                return False
            return True
        except Exception as e:
            logger.error("Error calculating hash for %s: %s", self.slug, e)
            return False
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def _execute_verified_script(self, env_vars: list, timeout: int) -> CommandResult:
        """Re-hash via open FD, stage a sealed copy, re-hash, then elevate.

        Narrows path-based TOCTOU on the user-writable operators directory by:
        1) hashing the open FD, 2) writing exclusively to XDG_RUNTIME_DIR,
        3) re-hashing the sealed path immediately before pkexec.
        Same-UID residual risk remains (documented in threat model).
        """
        import tempfile

        try:
            fd = os.open(str(self.script_path), os.O_RDONLY)
        except OSError as exc:
            return CommandResult(False, -1, "", f"Cannot open script: {exc}", [])

        sealed_path = None
        try:
            if self._hash_file_fd(fd) != self.EXPECTED_SHA256:
                return CommandResult(False, 126, "", "Security abort: Script integrity failure.", [])

            runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
            sealed_dir = Path(runtime) / "netmedic"
            sealed_dir.mkdir(mode=0o700, exist_ok=True)
            try:
                os.chmod(sealed_dir, 0o700)
            except OSError:
                pass

            sealed_path = sealed_dir / f"openvpn-install.{os.getpid()}.{os.getuid()}.sh"
            if sealed_path.exists():
                sealed_path.unlink()
            out_fd = os.open(
                str(sealed_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o700,
            )
            try:
                while True:
                    block = os.read(fd, 65536)
                    if not block:
                        break
                    os.write(out_fd, block)
                os.fsync(out_fd)
            finally:
                os.close(out_fd)

            sealed_fd = os.open(str(sealed_path), os.O_RDONLY)
            try:
                if self._hash_file_fd(sealed_fd) != self.EXPECTED_SHA256:
                    return CommandResult(
                        False, 126, "", "Security abort: Sealed script integrity failure.", []
                    )
            finally:
                os.close(sealed_fd)

            cmd = ["env"] + list(env_vars) + [str(sealed_path)]
            return CommandRunner.run(cmd, require_root=True, timeout=timeout)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            if sealed_path is not None:
                try:
                    sealed_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def check_status(self) -> NetResult:
        try:
            if not self.script_path.exists():
                return NetResult(self.name, True, OperatorStatus.NOT_INSTALLED.value, details="Script not found.")

            # Verificación de integridad en cada chequeo de estado
            if not self._verify_integrity():
                 return NetResult(self.name, False, OperatorStatus.ERROR.value, details="Script integrity check failed (SHA256 mismatch). Please re-install.")

            is_active = CommandRunner.is_service_active(self.get_service_name())
            status = OperatorStatus.RUNNING.value if is_active else OperatorStatus.STOPPED.value
            return NetResult(self.name, True, status)

        except Exception as e:
            logger.exception(f"Error checking status for {self.slug}")
            return NetResult(self.name, False, OperatorStatus.ERROR.value, details=str(e))

    def _download_script(self) -> NetResult:
        logger.info(f"Downloading installer from {self.SCRIPT_URL}")
        cmd = ["curl", "-sS", "-L", "-o", str(self.script_path), self.SCRIPT_URL]
        res = CommandRunner.run(cmd, timeout=60)
        
        if not res.success:
            return NetResult("Download Script", False, "Download failed", details=res.stderr)

        if not self.script_path.exists() or self.script_path.stat().st_size == 0:
            return NetResult("Download Script", False, "Empty or missing file")
        
        # Validar integridad inmediatamente tras descarga
        if not self._verify_integrity():
             return NetResult("Download Script", False, "Integrity check failed after download. The source might be compromised or the download corrupted.")

        try:
            with open(self.script_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if not first_line.startswith("#!") or "bash" not in first_line:
                     return NetResult("Download Script", False, "Invalid script header")
            # Owner-only execute/read — reduces casual overwrite without chmod.
            self.script_path.chmod(0o500)
        except Exception as e:
             return NetResult("Download Script", False, "Validation failed", details=str(e))

        return NetResult("Download Script", True, "Download verified")

    def install(self) -> NetResult:
        dl_res = self._download_script()
        if not dl_res.success: return dl_res

        env_vars = [
            "APPROVE_INSTALL=y",
            "APPROVE_IP=y",
            "IPV6_SUPPORT=n",
            "PORT_CHOICE=1",     # UDP 1194
            "PROTOCOL_CHOICE=1", # UDP
            "DNS=3",             # Cloudflare (1.1.1.1)
            "COMPRESSION_ENABLED=n",
            "CUSTOMIZE_ENC=n"
        ]

        logger.info("Starting installation of %s", self.slug)
        res = self._execute_verified_script(env_vars, timeout=300)
        
        if not res.success:
            return NetResult(self.name, False, "Installation failed", details=res.stderr)

        final_status = self.check_status()
        if final_status.message == OperatorStatus.RUNNING.value:
            return NetResult(self.name, True, "Installation successful")
        else:
             return NetResult(self.name, False, "Install success but service down", details=final_status.message)

    def list_clients(self) -> NetResult:
        """
        Lee directamente el archivo index.txt de EasyRSA.
        Formato: V <expire> <revoke> <serial> <unknown> /CN=client_name
        """
        # Verificamos primero si estamos instalados
        status = self.check_status()
        if status.message == OperatorStatus.NOT_INSTALLED.value:
            return NetResult(self.name, False, "VPN not installed")

        # Leemos el archivo protegido (requiere root)
        res = CommandRunner.run(["cat", self.INDEX_TXT_PATH], require_root=True)
        if not res.success:
            # Si falla cat, quizás no se ha creado PKI aún
            return NetResult(self.name, False, "Cannot read PKI index", details=res.stderr)

        clients = []
        try:
            for line in res.stdout.splitlines():
                parts = line.split('\t')
                if len(parts) < 6: continue
                
                status_flag = parts[0] # V=Valid, R=Revoked
                dn_field = parts[5]    # /CN=client_name
                
                # Extraer nombre
                cn_match = re.search(r'/CN=([^/]+)', dn_field)
                if not cn_match: continue
                
                client_name = cn_match.group(1)
                
                # Ignorar entradas de servidor u otros artefactos si los hay
                if client_name == "server": continue

                clients.append(VPNClient(
                    name=client_name,
                    active=(status_flag == 'V')
                ))
            
            return NetResult(self.name, True, "Client list retrieved", data=clients)
            
        except Exception as e:
            logger.exception("Error parsing client list")
            return NetResult(self.name, False, "Parse error", details=str(e))

    def _validate_client_name(self, name: str) -> bool:
        # Solo alfanuméricos y guiones
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))

    def add_client(self, name: str) -> NetResult:
        if not self._validate_client_name(name):
            return NetResult(self.name, False, "Invalid client name (use a-z, 0-9, -, _)")
        
        # Verificar duplicados
        current_clients = self.list_clients()
        if current_clients.success and current_clients.data:
            for c in current_clients.data:
                if c.name == name and c.active:
                    return NetResult(self.name, False, f"Client '{name}' already exists")

        env_vars = [
            "MENU_OPTION=1",
            f"CLIENT={name}",
            "PASS=1",
        ]
        logger.info("Adding VPN client: %s", name)
        res = self._execute_verified_script(env_vars, timeout=60)
        
        if not res.success:
            return NetResult(self.name, False, "Failed to execute add-client script", details=res.stderr)

        # Validación post-operación: Verificar que el cliente aparezca en el índice
        verify_res = self.list_clients()
        if verify_res.success and verify_res.data:
            for c in verify_res.data:
                if c.name == name and c.active:
                    return NetResult(self.name, True, f"Client '{name}' created and verified")
        
        return NetResult(self.name, False, f"Script reported success but client '{name}' was not found in PKI index")

    def revoke_client(self, name: str) -> NetResult:
        if not self._validate_client_name(name):
            return NetResult(self.name, False, "Invalid client name (use a-z, 0-9, -, _)")

        env_vars = [
            "MENU_OPTION=2",
            f"CLIENT={name}",
        ]
        logger.info("Revoking VPN client: %s", name)
        res = self._execute_verified_script(env_vars, timeout=60)

        if not res.success:
            return NetResult(self.name, False, "Failed to revoke client", details=res.stderr)

        verify_res = self.list_clients()
        if verify_res.success and verify_res.data:
            for client in verify_res.data:
                if client.name == name and not client.active:
                    return NetResult(self.name, True, f"Client '{name}' revoked and verified")

        return NetResult(
            self.name,
            False,
            f"Script reported success but client '{name}' was not marked revoked in PKI index",
        )

    def start_service(self) -> NetResult:
        """Starts the OpenVPN systemd unit when installed."""
        if not self.script_path.exists():
            return NetResult(self.name, False, OperatorStatus.NOT_INSTALLED.value, details="Script not found.")
        if not self._verify_integrity():
            return NetResult(self.name, False, OperatorStatus.ERROR.value, details="Script integrity check failed.")

        service = self.get_service_name()
        res = CommandRunner.run(["systemctl", "start", service], require_root=True, timeout=60)
        if CommandRunner.is_service_active(service):
            return NetResult(self.name, True, "VPN service started")
        return NetResult(self.name, False, "Failed to start VPN service", details=res.stderr)

    def restart_service(self) -> NetResult:
        """Restarts the OpenVPN systemd unit without touching NetworkManager."""
        if not self.script_path.exists():
            return NetResult(self.name, False, OperatorStatus.NOT_INSTALLED.value, details="VPN not installed.")
        if not self._verify_integrity():
            return NetResult(self.name, False, OperatorStatus.ERROR.value, details="Script integrity check failed.")

        service = self.get_service_name()
        res = CommandRunner.run(["systemctl", "restart", service], require_root=True, timeout=60)
        if CommandRunner.is_service_active(service):
            return NetResult(self.name, True, "VPN tunnel restarted")
        return NetResult(self.name, False, "Failed to restart VPN service", details=res.stderr)

    def stop(self) -> None:
        """Releases operator resources without stopping the system VPN service."""
        logger.info(
            "Operador %s liberado (servicio VPN del sistema permanece activo).",
            self.name,
        )
