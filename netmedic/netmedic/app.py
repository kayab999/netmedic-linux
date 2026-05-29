import gi
import logging
import sys
import os
import signal
import argparse
import time
from logging.handlers import RotatingFileHandler
from netmedic.config import Config
from netmedic.ui import MainWindow
from netmedic.network import NetworkMedic
from netmedic.ipc_bridge import NetMedicIPCServer
from netmedic.lifecycle import LifecycleManager

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

_medic_instance = None
_lifecycle_manager = LifecycleManager()

def handle_signals(signum, frame):
    """Handler para señales de terminación con cleanup centralizado."""
    sig_name = signal.Signals(signum).name
    logging.info(f"Received signal {sig_name} ({signum}). Starting emergency cleanup...")
    
    # 1. Cleanup centralizado (archivos estado + lock)
    _lifecycle_manager.cleanup()
        
    # 2. Cleanup operadores/app
    try:
        if _medic_instance is not None:
            _medic_instance.cleanup()
    except Exception as e:
        logging.error(f"Cleanup failed: {e}")
    
    sys.exit(0)

def main():
    # 0. Parsing de argumentos
    parser = argparse.ArgumentParser(description="NetMedic: Network Diagnostic & Repair Tool")
    parser.add_argument("--headless", action="store_true", help="Run without GUI (background mode)")
    args = parser.parse_args()

    # 1. Registrar handlers de señales de sistema
    signal.signal(signal.SIGINT, handle_signals)
    signal.signal(signal.SIGTERM, handle_signals)

    # 2. Setup Logging
    try:
        setup_logging()
    except Exception as e:
        print(f"CRITICAL: Failed to setup logging: {e}", file=sys.stderr)

    # 3. Bloqueo de instancia única (OS-level)
    if not _lifecycle_manager.acquire_lock():
        msg = "NetMedic ya está en ejecución. Solo se permite una instancia activa."
        logging.error(msg)
        if not args.headless:
            try:
                show_error_dialog(msg)
            except:
                print(msg, file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)
        
    _lifecycle_manager.write_pid() # Registrar PID tras adquirir lock exitosamente

    # 4. Inicialización de App
    global _medic_instance
    _medic_instance = NetworkMedic()
    
    try:
        GLib.set_prgname("netmedic")
        GLib.set_application_name("NetMedic")
        
        if args.headless:
            logging.info("Running in HEADLESS mode. GUI disabled.")
            while True:
                time.sleep(10)
        else:
            win = MainWindow()
            win.show_all()
            Gtk.main()
            
    except Exception as e:
        logging.critical(f"Unhandled Application Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        _lifecycle_manager.cleanup() # Garantía final de cleanup


def show_error_dialog(message):
    """Muestra un diálogo de error GTK simple."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Error de Instancia"
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()

def setup_logging():
    """
    Configura logging rotativo a archivo y consola.
    Aplica seguridad estricta (0o600) al archivo de log.
    """
    log_file = Config.get_log_file()
    
    # Asegurar que el archivo existe para poder hacer chmod
    if not log_file.exists():
        log_file.touch(mode=0o600)
    else:
        os.chmod(log_file, 0o600)

    # Formato profesional: Timestamp | Level | Module | Message
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    handlers = []

    # 1. File Handler (Rotativo: 1MB, guarda 3 backups)
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=1_048_576, # 1MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    handlers.append(file_handler)

    # 2. Console Handler (Para desarrollo/terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG) 
    handlers.append(console_handler)

    # Root Logger Config
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Capturamos todo, los handlers filtran
    
    # Limpiar handlers previos para evitar duplicados si se recarga
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    for h in handlers:
        root_logger.addHandler(h)
    
    logging.info(f"=== NetMedic Session Started ===")
    logging.info(f"Log file: {log_file} (Permissions: {oct(log_file.stat().st_mode & 0o777)})")

def main():
    # 0. Parsing de argumentos
    parser = argparse.ArgumentParser(description="NetMedic: Network Diagnostic & Repair Tool")
    parser.add_argument("--headless", action="store_true", help="Run without GUI (background mode)")
    args = parser.parse_args()

    # 1. Registrar handlers de señales de sistema
    signal.signal(signal.SIGINT, handle_signals)
    signal.signal(signal.SIGTERM, handle_signals)

    # 2. Setup Logging
    try:
        setup_logging()
    except Exception as e:
        print(f"CRITICAL: Failed to setup logging: {e}", file=sys.stderr)

    # 3. Bloqueo de instancia única (OS-level)
    if not _lifecycle_manager.acquire_lock():
        msg = "NetMedic ya está en ejecución. Solo se permite una instancia activa."
        logging.error(msg)
        if not args.headless:
            try:
                show_error_dialog(msg)
            except:
                print(msg, file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)
        
    _lifecycle_manager.write_pid() # Registrar PID tras adquirir lock exitosamente

    # 4. Inicialización de App
    global _medic_instance
    _medic_instance = NetworkMedic()

    try:
        GLib.set_prgname("netmedic")
        GLib.set_application_name("NetMedic")

        if args.headless:
            logging.info("Running in HEADLESS mode. GUI disabled.")
            while True:
                time.sleep(10)
        else:
            win = MainWindow()
            win.show_all()
            Gtk.main()

    except Exception as e:
        logging.critical(f"Unhandled Application Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        _lifecycle_manager.cleanup() # Garantía final de cleanup

