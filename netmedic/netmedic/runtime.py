import argparse
import logging
import os
import signal
import sys
import time
import warnings
from logging.handlers import RotatingFileHandler
from types import FrameType
from typing import Callable, List, Optional

from netmedic.config import Config
from netmedic.network import NetworkMedic
from netmedic.ipc_bridge import NetMedicIPCServer
from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_security import IPCSession
from netmedic.lifecycle import LifecycleManager
from netmedic.teardown import run_all as run_teardown_callbacks

_medic_instance = None
_ipc_server = None
_ipc_session = None
_lifecycle_manager = LifecycleManager()
_shutting_down = False


def get_medic_instance() -> Optional[NetworkMedic]:
    return _medic_instance


def get_ipc_session() -> IPCSession:
    global _ipc_session
    if _ipc_session is None:
        _ipc_session = IPCSession()
    return _ipc_session


def handle_signals(signum: int, frame: Optional[FrameType]) -> None:
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    sig_name = signal.Signals(signum).name
    logging.info("Received signal %s (%s). Starting emergency cleanup...", sig_name, signum)

    run_teardown_callbacks()

    if _ipc_server is not None:
        _ipc_server.stop()

    if _ipc_session is not None:
        _ipc_session.cleanup()

    _lifecycle_manager.cleanup()

    try:
        if _medic_instance is not None:
            _medic_instance.cleanup()
    except Exception as exc:
        logging.error("Cleanup failed: %s", exc)

    try:
        from netmedic.gui import quit_gui_if_running
        quit_gui_if_running()
    except Exception:  # noqa: S110 (GUI teardown during shutdown; must not block exit)
        pass

    sys.exit(0)


def setup_logging(headless: bool = False) -> None:
    log_file = Config.get_log_file()

    if not log_file.exists():
        log_file.touch(mode=0o600)
    else:
        os.chmod(log_file, 0o600)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_048_576,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO if headless else logging.DEBUG)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Route warnings (e.g. NetResult.success UserWarning) to netmedic.log
    # Chosen to stay outside DeprecationWarning filter shadowing — see test_canary_shim
    logging.captureWarnings(True)
    warnings.filterwarnings("always", category=UserWarning)
    # Silence noisy DeprecationWarnings from PyGObject/GLib etc. — would flood netmedic.log
    # Must be AFTER captureWarnings (which does simplefilter("always"))
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    logging.info("=== NetMedic Session Started ===")
    logging.info(
        "Log file: %s (Permissions: %s)",
        log_file,
        oct(log_file.stat().st_mode & 0o777),
    )


def bootstrap(headless: bool = False) -> bool:
    """
    Shared startup: logging, lock, IPC server.
    Returns False if another instance is already running.
    """
    global _medic_instance, _ipc_server, _ipc_session

    try:
        setup_logging(headless=headless)
    except Exception as exc:
        print(f"CRITICAL: Failed to setup logging: {exc}", file=sys.stderr)

    lock_acquired = False
    try:
        if not _lifecycle_manager.acquire_lock():
            msg = "NetMedic is already running. Only one active instance is allowed."
            logging.error(msg)
            if not headless:
                try:
                    from netmedic.gui import show_error_dialog
                    show_error_dialog(msg)
                except Exception:
                    print(msg, file=sys.stderr)
            else:
                print(msg, file=sys.stderr)
            return False

        lock_acquired = True
        _lifecycle_manager.write_pid()

        _medic_instance = NetworkMedic()
        _ipc_session = IPCSession()
        _ipc_session.issue_token()

        dispatcher = create_action_dispatcher(_medic_instance, _ipc_session)
        _ipc_server = NetMedicIPCServer(dispatcher, _lifecycle_manager)
        _ipc_server.start()
        return True
    except Exception:
        if lock_acquired:
            _lifecycle_manager.cleanup()
        raise


def shutdown() -> None:
    global _ipc_server, _ipc_session, _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    run_teardown_callbacks()

    if _ipc_server is not None:
        _ipc_server.stop()
    if _ipc_session is not None:
        _ipc_session.cleanup()
    _lifecycle_manager.cleanup()

    try:
        if _medic_instance is not None:
            _medic_instance.cleanup()
    except Exception as exc:
        logging.error("Cleanup failed during shutdown: %s", exc)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NetMedic: Network Diagnostic & Repair Tool")
    parser.add_argument("--headless", action="store_true", help="Run without GUI (background mode)")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print install/runtime health and exit (no daemon)",
    )
    parser.add_argument(
        "--status-json",
        action="store_true",
        help="Same as --status but JSON output",
    )
    parser.add_argument(
        "--require-privileged",
        action="store_true",
        help="With --status, exit 1 unless privileged_ready is true",
    )
    return parser.parse_args(argv)


GUI_INSTALL_HINT = (
    "NetMedic GUI is unavailable because PyGObject/GTK3 is not installed.\n"
    "Install the GUI extra and the system GTK3/GObject packages, for example:\n"
    "  pip install 'netmedic[gui]'\n"
    "For diagnostics without GTK:\n"
    "  netmedic --headless"
)


def _is_missing_gi(exc: BaseException) -> bool:
    name = getattr(exc, "name", "") or ""
    return name == "gi" or name.startswith("gi.")


def _is_gui_dependency_error(exc: BaseException) -> bool:
    if _is_missing_gi(exc):
        return True
    text = str(exc).lower()
    return "namespace gtk" in text or "libgtk" in text or "gtk-3" in text


def load_gui() -> Callable[[], None]:
    """Import the GUI entry point or exit with an actionable message."""
    try:
        from netmedic.gui import run_gui
    except (ImportError, ValueError) as exc:
        if _is_gui_dependency_error(exc):
            print(GUI_INSTALL_HINT, file=sys.stderr)
            sys.exit(1)
        raise
    return run_gui


def run(
    headless: bool = False,
    *,
    status: bool = False,
    status_json: bool = False,
    require_privileged: bool = False,
) -> None:
    if status or status_json:
        from netmedic.status import print_status

        sys.exit(
            print_status(
                as_json=bool(status_json),
                require_privileged=bool(require_privileged),
            )
        )

    # Resolve the GUI before starting the daemon: a missing PyGObject must be a
    # clear install hint, not a partially started headless process.
    run_gui = None if headless else load_gui()

    signal.signal(signal.SIGINT, handle_signals)
    signal.signal(signal.SIGTERM, handle_signals)
    signal.signal(signal.SIGHUP, handle_signals)

    if not bootstrap(headless=headless):
        sys.exit(1)

    try:
        if headless:
            logging.info("Running in HEADLESS mode. GUI disabled.")
            while True:
                time.sleep(10)
        else:
            assert run_gui is not None
            run_gui()
    except Exception as exc:
        logging.critical("Unhandled Application Error: %s", exc, exc_info=True)
        if not headless:
            try:
                from netmedic.gui import show_error_dialog

                show_error_dialog(
                    f"{type(exc).__name__}: {exc}",
                    title="NetMedic failed to start",
                )
            except Exception:
                print(f"NetMedic failed to start: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        shutdown()