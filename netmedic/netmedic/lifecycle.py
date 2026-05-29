import os
import logging
import fcntl
from pathlib import Path
from netmedic.config import Config

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
        self._lock_fd = None

    def acquire_lock(self):
        """Intenta adquirir el lock de instancia única."""
        try:
            self._lock_fd = open(self.lock_file, "w")
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
            return True
        except (IOError, BlockingIOError):
            return False

    def cleanup(self):
        """Realiza el cleanup garantizado de todos los recursos de estado."""
        logging.info("Ejecutando limpieza centralizada de recursos...")
        if self._lock_fd:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                self._lock_fd.close()
            except:
                pass
        
        files_to_remove = [self.pid_file, self.sock_file, self.lock_file]
        for path in files_to_remove:
            if path.exists():
                try:
                    os.remove(path)
                    logging.debug(f"Removido recurso de estado: {path}")
                except Exception as e:
                    logging.error(f"Error removiendo {path}: {e}")
        logging.info("Limpieza centralizada finalizada.")

    def write_pid(self):
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        os.chmod(self.pid_file, 0o600)
