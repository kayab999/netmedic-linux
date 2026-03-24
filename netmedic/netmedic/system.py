import subprocess
import shutil
import logging
import os
import re
from typing import List
from netmedic.models import CommandResult
from netmedic.config import Config

logger = logging.getLogger(__name__)

class CommandRunner:
    # Regex para detectar argumentos que suelen contener secretos
    SENSITIVE_PATTERNS = [
        r"(?i)password", r"(?i)pass", r"(?i)token", 
        r"(?i)key", r"(?i)secret", r"(?i)auth"
    ]

    @staticmethod
    def _redact_command(command: List[str]) -> str:
        """Redacta argumentos potencialmente sensibles para el log."""
        redacted = []
        it = iter(command)
        for arg in it:
            # Si el argumento actual parece una clave (ej: --password)
            # redactamos el SIGUIENTE argumento si no empieza por '-'
            if any(re.search(p, arg) for p in CommandRunner.SENSITIVE_PATTERNS):
                redacted.append(arg)
                try:
                    val = next(it)
                    if val.startswith("-"): # Es otro flag
                         redacted.append(val)
                    else:
                         redacted.append("<REDACTED>")
                except StopIteration:
                    break
            # O si el argumento contiene '=' (ej: --token=xyz)
            elif "=" in arg:
                if "=" in arg:
                    parts = arg.split("=", 1)
                    key = parts[0]
                    if any(re.search(p, key) for p in CommandRunner.SENSITIVE_PATTERNS):
                        redacted.append(f"{key}=<REDACTED>")
                    else:
                        redacted.append(arg)
            else:
                redacted.append(arg)
        return " ".join(redacted)

    @staticmethod
    def run(command: List[str], require_root: bool = False, timeout: int = None) -> CommandResult:
        """
        Ejecuta comandos con timeout, manejo de elevación y logging sanitizado.
        """
        if timeout is None:
            timeout = Config.get_default_timeout()

        final_cmd = command.copy()
        
        if require_root and os.geteuid() != 0:
            if not shutil.which("pkexec"):
                logger.error("pkexec not found, cannot elevate privileges")
                return CommandResult(False, 127, "", "pkexec no encontrado", final_cmd)
            final_cmd = ["pkexec"] + final_cmd

        cmd_str_redacted = CommandRunner._redact_command(final_cmd)
        logger.debug(f"Exec: {cmd_str_redacted}")

        try:
            proc = subprocess.run(
                final_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout
            )
            
            # Logging del resultado (Truncamos output muy largo)
            log_msg = f"Return: {proc.returncode}"
            if proc.stdout:
                log_msg += f" | Stdout: {proc.stdout.strip()[:200]}..." if len(proc.stdout) > 200 else f" | Stdout: {proc.stdout.strip()}"
            if proc.stderr:
                log_msg += f" | Stderr: {proc.stderr.strip()[:200]}..." if len(proc.stderr) > 200 else f" | Stderr: {proc.stderr.strip()}"
            
            logger.debug(log_msg)

            # Detección de cancelación de usuario en pkexec (códigos 126/127 son comunes)
            if proc.returncode in [126, 127] and require_root:
                # Heurística: pkexec devuelve 126/127 si se cierra la ventana
                if "dismissed" in proc.stderr.lower() or not proc.stderr:
                    logger.warning(f"Privilege elevation cancelled by user for: {cmd_str_redacted}")
                    return CommandResult(False, 126, "", "Autenticación cancelada por usuario", final_cmd)

            return CommandResult(
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                command=final_cmd
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout ({timeout}s) executing: {cmd_str_redacted}")
            return CommandResult(False, -1, "", f"Timeout ({timeout}s) excedido", final_cmd)
        except Exception as e:
            logger.exception(f"Exception executing: {cmd_str_redacted}")
            return CommandResult(False, -1, "", str(e), final_cmd)

    @staticmethod
    def is_service_active(service_name: str) -> bool:
        """
        Verifica el estado del servicio usando CommandRunner.
        """
        res = CommandRunner.run(
            ["systemctl", "is-active", "--quiet", service_name],
            timeout=5.0
        )
        return res.success
