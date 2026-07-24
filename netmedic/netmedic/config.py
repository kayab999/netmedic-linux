import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    APP_NAME = "netmedic"

    @staticmethod
    def get_state_dir() -> Path:
        """Return ~/.local/state/netmedic (logs, runtime state)."""
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        app_state = base / Config.APP_NAME
        Config._ensure_dir(app_state)
        return app_state

    @staticmethod
    def get_data_dir() -> Path:
        """Return ~/.local/share/netmedic (scripts, persistent data)."""
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
        app_data = base / Config.APP_NAME
        Config._ensure_dir(app_data)
        return app_data

    @staticmethod
    def get_operators_dir() -> Path:
        """Central directory for external operator scripts and binaries."""
        path = Config.get_data_dir() / "operators"
        Config._ensure_dir(path)
        return path

    @staticmethod
    def get_log_file() -> Path:
        return Config.get_state_dir() / "netmedic.log"

    @staticmethod
    def get_audit_log_file() -> Path:
        return Config.get_state_dir() / "audit.log"

    @staticmethod
    def get_default_timeout() -> int:
        """Default timeout for short commands (30s)."""
        return 30

    @staticmethod
    def get_long_timeout() -> int:
        """Timeout for heavy installs/downloads (300s)."""
        return 300

    @staticmethod
    def _ensure_dir(path: Path):
        """Ensure directory exists with mode 0700 and is owned by this user."""
        if not path.exists():
            path.mkdir(parents=True, mode=0o700, exist_ok=True)
        else:
            current_mode = path.stat().st_mode & 0o777
            if current_mode != 0o700:
                os.chmod(path, 0o700)

        try:
            st = path.stat()
            if st.st_uid != os.getuid():
                raise PermissionError(
                    f"State/data directory {path} is not owned by the current user "
                    f"(owner uid={st.st_uid}, self={os.getuid()})."
                )
            if (st.st_mode & 0o777) != 0o700:
                os.chmod(path, 0o700)
        except OSError as exc:
            logger.error("Failed to verify directory security for %s: %s", path, exc)
            raise
