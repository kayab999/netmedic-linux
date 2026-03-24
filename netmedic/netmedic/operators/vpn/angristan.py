import logging
import re
import hashlib
from typing import List, Optional
from netmedic.models import NetResult, CommandResult
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

    def _verify_integrity(self) -> bool:
        """Calcula el SHA256 del script local y lo compara con el esperado."""
        if not self.script_path.exists():
            return False
        
        sha256_hash = hashlib.sha256()
        try:
            with open(self.script_path, "rb") as f:
                # Leer en bloques para eficiencia
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            actual_hash = sha256_hash.hexdigest()
            if actual_hash != self.EXPECTED_SHA256:
                logger.error(f"SHA256 mismatch for {self.slug}. Expected {self.EXPECTED_SHA256}, got {actual_hash}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error calculating hash for {self.slug}: {e}")
            return False

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
            self.script_path.chmod(0o700)
        except Exception as e:
             return NetResult("Download Script", False, "Validation failed", details=str(e))

        return NetResult("Download Script", True, "Download verified")

    def install(self) -> NetResult:
        dl_res = self._download_script()
        if not dl_res.success: return dl_res

        # Variables para instalación desatendida (Decisiones documentadas en diseño)
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
        
        # Verificación final de hash antes de ejecutar como root
        if not self._verify_integrity():
            return NetResult(self.name, False, "Security abort: Script tampered before execution.")

        cmd = ["env"] + env_vars + [str(self.script_path)]
        logger.info(f"Starting installation of {self.slug}")
        
        res = CommandRunner.run(cmd, require_root=True, timeout=300)
        
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

        # Verificación de integridad antes de manipulación
        if not self._verify_integrity():
            return NetResult(self.name, False, "Security abort: Script integrity failure.")

        # Ejecutar script modo menú: 1) Add new user
        # Variables: MENU_OPTION="1", CLIENT="name", PASS="1" (No password)
        env_vars = [
            "MENU_OPTION=1",
            f"CLIENT={name}",
            "PASS=1"
        ]
        
        cmd = ["env"] + env_vars + [str(self.script_path)]
        logger.info(f"Adding VPN client: {name}")
        
        res = CommandRunner.run(cmd, require_root=True, timeout=60)
        
        if res.success:
            return NetResult(self.name, True, f"Client '{name}' created")
        else:
            return NetResult(self.name, False, "Failed to create client", details=res.stderr)

    def revoke_client(self, name: str) -> NetResult:
        # Verificación de integridad antes de manipulación
        if not self._verify_integrity():
            return NetResult(self.name, False, "Security abort: Script integrity failure.")

        # Ejecutar script modo menú: 2) Revoke existing user
        # Variables: MENU_OPTION="2", CLIENT="name"
        env_vars = [
            "MENU_OPTION=2",
            f"CLIENT={name}"
        ]
        
        cmd = ["env"] + env_vars + [str(self.script_path)]
        logger.info(f"Revoking VPN client: {name}")
        
        res = CommandRunner.run(cmd, require_root=True, timeout=60)
        
        if res.success:
            # Por ahora confiamos en el script
            return NetResult(self.name, True, f"Client '{name}' revoked")
        else:
            return NetResult(self.name, False, "Failed to revoke client", details=res.stderr)
