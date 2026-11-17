import logging
import os
import re
from pathlib import Path

from netmedic.config import Config
from netmedic.models import NetResult, ResultCode
from netmedic.operators.vpn.base import VPNOperator, VPNClient
from netmedic.operators.base import OperatorStatus
from netmedic.system import CommandRunner

logger = logging.getLogger(__name__)


class AngristanOperator(VPNOperator):
    """
    Implementación del operador VPN usando el script de Angristan.
    Commit Pinneado: 9c966d4 (para estabilidad garantizada).
    Referencia: https://github.com/angristan/openvpn-install

    F2: el instalador está vendorizado en el repositorio y lo instala el
    paquete como /usr/lib/netmedic/scripts/openvpn-install.sh (root:root).
    El daemon ya no descarga, hashea ni sella el script: sólo nombra el
    ``script_id`` y el helper root verifica el pin antes de ejecutarlo.
    """

    # Pinned upstream commit (provenance only; see docs/VPN_REPIN.md).
    PIN_COMMIT = "9c966d4"

    # Shown to operators on every pin failure (B-9: name the resolution).
    REPIN_HINT = (
        "See docs/VPN_REPIN.md (vendored bytes + SHA256 must be updated "
        "together; verify upstream provenance before re-pinning)."
    )

    # Source of truth for client certificates.
    INDEX_TXT_PATH = "/etc/openvpn/server/easy-rsa/pki/index.txt"

    # Completion marker for the server install. Replaces the old check for a
    # user-writable copy of the installer, which no longer exists.
    INSTALL_MARKER_PATH = "/etc/openvpn/server/server.conf"

    # Fixed helper allowlist id; the path never crosses IPC.
    SCRIPT_ID = "openvpn-install"

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

    def _installed(self) -> bool:
        return Path(self.INSTALL_MARKER_PATH).is_file()

    def check_status(self) -> NetResult:
        try:
            if not self._installed():
                return NetResult(
                    self.name,
                    True,
                    OperatorStatus.NOT_INSTALLED.value,
                    details="OpenVPN server config not found.",
                )

            is_active = CommandRunner.is_service_active(self.get_service_name())
            status = OperatorStatus.RUNNING.value if is_active else OperatorStatus.STOPPED.value
            return NetResult(self.name, True, status)

        except Exception as e:
            logger.exception(f"Error checking status for {self.slug}")
            return NetResult(self.name, False, OperatorStatus.ERROR.value, details=str(e))

    def install(self) -> NetResult:
        logger.info("Starting installation of %s", self.slug)
        res = CommandRunner.run_elevated(
            "vpn-install",
            {
                "port": 1194,
                "protocol": "udp",
                "dns": "cloudflare",
                "client_ipv6": False,
                "client": "client",
            },
            timeout=300,
        )

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

        # Privileged PKI index read via fixed helper verb (no caller path — F2).
        res = CommandRunner.run_elevated("vpn-list", {})
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
        if current_clients.code == ResultCode.OK and current_clients.data:
            for c in current_clients.data:
                if c.name == name and c.active:
                    return NetResult(self.name, False, f"Client '{name}' already exists")

        logger.info("Adding VPN client: %s", name)
        res = CommandRunner.run_elevated(
            "vpn-add-client", {"name": name}, timeout=60
        )

        if not res.success:
            return NetResult(self.name, False, "Failed to execute add-client script", details=res.stderr)

        # F4: persist the delivered .ovpn under the user data dir (0700/0600).
        if res.artifact:
            try:
                client_dir = Config.get_data_dir() / "vpn-clients"
                client_dir.mkdir(parents=True, exist_ok=True)
                client_dir.chmod(0o700)
                target = client_dir / f"{name}.ovpn"
                fd = os.open(
                    str(target),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    os.write(fd, res.artifact.encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError as exc:
                logger.warning("Could not persist .ovpn for %s: %s", name, exc)

        # Validación post-operación: Verificar que el cliente aparezca en el índice
        verify_res = self.list_clients()
        if verify_res.code == ResultCode.OK and verify_res.data:
            for c in verify_res.data:
                if c.name == name and c.active:
                    return NetResult(self.name, True, f"Client '{name}' created and verified")

        return NetResult(self.name, False, f"Script reported success but client '{name}' was not found in PKI index")

    def revoke_client(self, name: str) -> NetResult:
        if not self._validate_client_name(name):
            return NetResult(self.name, False, "Invalid client name (use a-z, 0-9, -, _)")

        logger.info("Revoking VPN client: %s", name)
        res = CommandRunner.run_elevated(
            "vpn-revoke-client", {"name": name}, timeout=60
        )

        if not res.success:
            return NetResult(self.name, False, "Failed to revoke client", details=res.stderr)

        verify_res = self.list_clients()
        if verify_res.code == ResultCode.OK and verify_res.data:
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
        if not self._installed():
            return NetResult(
                self.name,
                False,
                OperatorStatus.NOT_INSTALLED.value,
                details="OpenVPN server config not found.",
            )

        service = self.get_service_name()
        res = CommandRunner.run_elevated(
            "vpn-start-service", {"service": service}, timeout=60
        )
        if CommandRunner.is_service_active(service):
            return NetResult(self.name, True, "VPN service started")
        return NetResult(
            self.name, False, "Failed to start VPN service", details=res.stderr or res.stdout
        )

    def restart_service(self) -> NetResult:
        """Restarts the OpenVPN systemd unit without touching NetworkManager."""
        if not self._installed():
            return NetResult(
                self.name,
                False,
                OperatorStatus.NOT_INSTALLED.value,
                details="VPN not installed.",
            )

        service = self.get_service_name()
        res = CommandRunner.run_elevated(
            "vpn-restart-service", {"service": service}, timeout=60
        )
        if CommandRunner.is_service_active(service):
            return NetResult(self.name, True, "VPN tunnel restarted")
        return NetResult(
            self.name, False, "Failed to restart VPN service", details=res.stderr or res.stdout
        )

    def stop(self) -> None:
        """Releases operator resources without stopping the system VPN service."""
        logger.info(
            "Operador %s liberado (servicio VPN del sistema permanece activo).",
            self.name,
        )
