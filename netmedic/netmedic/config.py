import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def sys_executable_helper_module() -> str:
    """Return a marker path meaning 'invoke via python -m netmedic.helper_main'."""
    return f"{sys.executable}|-m|netmedic.helper_main"


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

    SYSTEM_HELPER_PATH = Path("/usr/libexec/netmedic/helper")
    SYSTEM_HELPER_LIB = Path("/usr/lib/netmedic")
    # Debian alternative location; some distros use /usr/lib instead of /usr/libexec
    SYSTEM_HELPER_ALT_PATH = Path("/usr/lib/netmedic/helper")

    @staticmethod
    def _any_helper_exists() -> bool:
        return Config.SYSTEM_HELPER_PATH.is_file() or Config.SYSTEM_HELPER_ALT_PATH.is_file()

    @staticmethod
    def use_privileged_helper() -> bool:
        """When true, elevated work goes through netmedic-helper via pkexec.

        Phase D: helper is the production path.
        - NETMEDIC_USE_HELPER=1/true → force on
        - NETMEDIC_USE_HELPER=0/false → force off (legacy only if allow_legacy_elevation)
        - unset → auto-on when system helper is installed
        """
        raw = os.environ.get("NETMEDIC_USE_HELPER", "").lower()
        if raw in ("0", "false", "no"):
            return False
        if raw in ("1", "true", "yes"):
            return True
        return Config._any_helper_exists()

    @staticmethod
    def allow_legacy_elevation() -> bool:
        """Permit raw pkexec <tool> argv (tests / emergency only).

        Production must not set this. Tests set NETMEDIC_ALLOW_LEGACY_ELEVATION=1
        together with NETMEDIC_USE_HELPER=0.
        Fail-closed when running as root: env override ignored.
        """
        try:
            if os.geteuid() == 0:
                if os.environ.get("NETMEDIC_ALLOW_LEGACY_ELEVATION"):
                    logger.warning("Ignoring NETMEDIC_ALLOW_LEGACY_ELEVATION when euid==0")
                return False
        except Exception:
            pass
        return os.environ.get("NETMEDIC_ALLOW_LEGACY_ELEVATION", "").lower() in (
            "1",
            "true",
            "yes",
        )

    @staticmethod
    def get_helper_path() -> Path:
        """Resolve netmedic-helper executable path."""
        try:
            is_root = os.geteuid() == 0
        except Exception:
            is_root = False
        override = os.environ.get("NETMEDIC_HELPER_PATH")
        if override and not is_root:
            return Path(override)
        if override and is_root:
            logger.warning("Ignoring NETMEDIC_HELPER_PATH when euid==0")
        if Config.SYSTEM_HELPER_PATH.is_file():
            return Config.SYSTEM_HELPER_PATH
        if Config.SYSTEM_HELPER_ALT_PATH.is_file():
            return Config.SYSTEM_HELPER_ALT_PATH
        which = __import__("shutil").which("netmedic-helper")
        if which:
            return Path(which)
        # Development fallback: python -m netmedic.helper_main
        return Path(sys_executable_helper_module())

    @staticmethod
    def _ensure_dir(path: Path) -> None:
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
