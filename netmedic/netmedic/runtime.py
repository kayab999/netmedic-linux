import argparse
import logging
import os
import signal
import sys
import time
from logging.handlers import RotatingFileHandler

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


def get_medic_instance():
    return _medic_instance


def get_ipc_session() -> IPCSession:
    global _ipc_session
    if _ipc_session is None:
        _ipc_session = IPCSession()
    return _ipc_session


def handle_signals(signum, frame):
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

    sys.exit(0)


def setup_logging(headless: bool = False):
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


def shutdown():
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="NetMedic: Network Diagnostic & Repair Tool")
    parser.add_argument("--headless", action="store_true", help="Run without GUI (background mode)")
    return parser.parse_args(argv)


def run(headless: bool = False):
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
            from netmedic.gui import run_gui
            run_gui()
    except Exception as exc:
        logging.critical("Unhandled Application Error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        shutdown()