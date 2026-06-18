import os
import logging
import fcntl
from netmedic.config import Config

logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Gestor centralizado del ciclo de vida y estado de la aplicación.
    Establece una única fuente de verdad para PID, Sockets, Lock y cleanup.
    """

    def __init__(self):
        self.state_dir = Config.get_state_dir()
        self.pid_file = self.state_dir / "ipc.pid"
        self.sock_file = self.state_dir / "ipc.sock"
        self.lock_file = self.state_dir / "netmedic.lock"
        self.token_file = self.state_dir / "ipc.token"
        self._lock_fd = None

    def _is_process_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _try_acquire_lock(self) -> bool:
        try:
            self._lock_fd = open(self.lock_file, "w")
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
            return True
        except (IOError, BlockingIOError):
            if self._lock_fd:
                try:
                    self._lock_fd.close()
                except OSError:
                    pass
                self._lock_fd = None
            return False

    def acquire_lock(self):
        """Intenta adquirir el lock de instancia única, recuperando locks huérfanos."""
        if self._try_acquire_lock():
            return True

        if self.lock_file.exists():
            try:
                pid = int(self.lock_file.read_text().strip())
                if not self._is_process_alive(pid):
                    logger.warning("Eliminando lock huérfano del PID %d", pid)
                    self.lock_file.unlink(missing_ok=True)
                    return self._try_acquire_lock()
            except (ValueError, OSError):
                logger.warning("Lock corrupto detectado, eliminando.")
                self.lock_file.unlink(missing_ok=True)
                return self._try_acquire_lock()

        return False

    def cleanup(self):
        """Realiza el cleanup garantizado de todos los recursos de estado."""
        logger.info("Ejecutando limpieza centralizada de recursos...")
        if self._lock_fd:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                self._lock_fd.close()
            except OSError:
                pass
            self._lock_fd = None

        files_to_remove = [self.pid_file, self.sock_file, self.lock_file, self.token_file]
        for path in files_to_remove:
            if path.exists():
                try:
                    os.remove(path)
                    logger.debug("Removido recurso de estado: %s", path)
                except OSError as e:
                    logger.error("Error removiendo %s: %s", path, e)
        logger.info("Limpieza centralizada finalizada.")

    def write_pid(self):
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        os.chmod(self.pid_file, 0o600)