import logging
import os
import re
import signal
import subprocess
import shutil
from typing import List, Optional
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
            # Prioridad: argumentos con '=' (ej: --token=xyz)
            if "=" in arg:
                parts = arg.split("=", 1)
                key = parts[0]
                if any(re.search(p, key) for p in CommandRunner.SENSITIVE_PATTERNS):
                    redacted.append(f"{key}=<REDACTED>")
                else:
                    redacted.append(arg)
            # Luego: argumentos flag (ej: --password)
            elif any(re.search(p, arg) for p in CommandRunner.SENSITIVE_PATTERNS):
                redacted.append(arg)
                try:
                    val = next(it)
                    if val.startswith("-"): # Es otro flag
                         redacted.append(val)
                    else:
                         redacted.append("<REDACTED>")
                except StopIteration:
                    break
            else:
                redacted.append(arg)
        return " ".join(redacted)

    @staticmethod
    def run(command: List[str], require_root: bool = False, timeout: Optional[int] = None) -> CommandResult:
        """
        Ejecuta comandos con timeout, manejo de elevación y logging sanitizado.
        """
        if timeout is None:
            timeout = Config.get_default_timeout()

        final_cmd = command.copy()
        
        if require_root and os.geteuid() != 0:
            if not shutil.which("pkexec"):
                logger.error("pkexec not found, cannot elevate privileges")
                return CommandResult(False, 127, "", "pkexec not found", final_cmd)
            final_cmd = ["pkexec"] + final_cmd

        cmd_str_redacted = CommandRunner._redact_command(final_cmd)
        logger.debug(f"Exec: {cmd_str_redacted}")

        proc = None
        try:
            proc = subprocess.Popen(
                final_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            stdout, stderr = proc.communicate(timeout=timeout)

            log_msg = f"Return: {proc.returncode}"
            if stdout:
                log_msg += (
                    f" | Stdout: {stdout.strip()[:200]}..."
                    if len(stdout) > 200
                    else f" | Stdout: {stdout.strip()}"
                )
            if stderr:
                log_msg += (
                    f" | Stderr: {stderr.strip()[:200]}..."
                    if len(stderr) > 200
                    else f" | Stderr: {stderr.strip()}"
                )
            logger.debug(log_msg)

            if proc.returncode in (126, 127) and require_root:
                stderr_lower = (stderr or "").lower()
                if "dismissed" in stderr_lower:
                    logger.warning("Privilege elevation cancelled by user for: %s", cmd_str_redacted)
                    return CommandResult(False, 126, "", "Authentication cancelled by user", final_cmd)
                if proc.returncode == 127 and "not found" in stderr_lower:
                    return CommandResult(False, 127, "", stderr.strip(), final_cmd)

            return CommandResult(
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=(stdout or "").strip(),
                stderr=(stderr or "").strip(),
                command=final_cmd,
            )
        except subprocess.TimeoutExpired:
            logger.error("Timeout (%ss) executing: %s", timeout, cmd_str_redacted)
            if proc is not None:
                CommandRunner._terminate_process_group(proc)
            return CommandResult(False, -1, "", f"Timeout ({timeout}s) exceeded", final_cmd)
        except Exception as e:
            logger.exception(f"Exception executing: {cmd_str_redacted}")
            return CommandResult(False, -1, "", str(e), final_cmd)

    @staticmethod
    def _terminate_process_group(proc: subprocess.Popen) -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except Exception:
            logger.debug("Failed to terminate process group cleanly", exc_info=True)

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
