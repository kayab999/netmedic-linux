import os
import logging
from pathlib import Path

class Config:
    APP_NAME = "netmedic"
    
    @staticmethod
    def get_state_dir() -> Path:
        """Retorna ~/.local/state/netmedic (Logs, estados de ejecución)"""
        xdg_state = os.environ.get('XDG_STATE_HOME')
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        app_state = base / Config.APP_NAME
        Config._ensure_dir(app_state)
        return app_state

    @staticmethod
    def get_data_dir() -> Path:
        """
        Retorna ~/.local/share/netmedic (Scripts, datos persistentes).
        Ubicación recomendada para archivos que el usuario desearía respaldar.
        """
        xdg_data = os.environ.get('XDG_DATA_HOME')
        base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
        app_data = base / Config.APP_NAME
        Config._ensure_dir(app_data)
        return app_data

    @staticmethod
    def get_operators_dir() -> Path:
        """Directorio centralizado para scripts y binarios de operadores externos."""
        path = Config.get_data_dir() / "operators"
        Config._ensure_dir(path)
        return path

    @staticmethod
    def get_log_file() -> Path:
        return Config.get_state_dir() / "netmedic.log"

    @staticmethod
    def get_default_timeout() -> int:
        """Timeout por defecto para comandos cortos (30s)."""
        return 30

    @staticmethod
    def get_long_timeout() -> int:
        """Timeout para instalaciones o descargas pesadas (300s)."""
        return 300

    @staticmethod
    def _ensure_dir(path: Path):
        """Asegura la existencia del directorio con permisos estrictos (700)."""
        if not path.exists():
            # mkdir con mode=0o700 aplica solo si el directorio se crea en esta llamada
            path.mkdir(parents=True, mode=0o700, exist_ok=True)
        else:
            # Si ya existe, forzamos permisos correctos por seguridad
            current_mode = path.stat().st_mode & 0o777
            if current_mode != 0o700:
                os.chmod(path, 0o700)
