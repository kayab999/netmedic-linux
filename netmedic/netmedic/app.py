import gi
import logging
import sys
import os
import signal
from logging.handlers import RotatingFileHandler
from netmedic.config import Config
from netmedic.ui import MainWindow
from netmedic.network import NetworkMedic

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

def handle_signals(signum, frame):
    """Handler para señales de terminación."""
    sig_name = signal.Signals(signum).name
    logging.info(f"Received signal {sig_name} ({signum}). Starting emergency cleanup...")
    try:
        # Instanciamos (obtenemos el singleton) y limpiamos
        medic = NetworkMedic()
        res = medic.cleanup()
        logging.info(f"Cleanup result: {res.message}")
    except Exception as e:
        logging.error(f"Cleanup failed during signal handling: {e}")
    
    # Salir forzosamente si estamos en un signal handler
    sys.exit(0)

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
    # Nota: RotatingFileHandler puede recrear el archivo sin permisos estrictos al rotar.
    # En un entorno de alta seguridad, se usaría WatchedFileHandler + logrotate externo,
    # pero para esta utilidad desktop, forzamos permisos al iniciar.
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
    # Registrar handlers de señales de sistema
    signal.signal(signal.SIGINT, handle_signals)
    signal.signal(signal.SIGTERM, handle_signals)

    try:
        setup_logging()
    except Exception as e:
        # Fallback de emergencia si no podemos escribir logs
        print(f"CRITICAL: Failed to setup logging: {e}", file=sys.stderr)

    try:
        GLib.set_prgname("netmedic")
        GLib.set_application_name("NetMedic")
        win = MainWindow()
        win.show_all()
        Gtk.main()
    except Exception as e:
        logging.critical(f"Unhandled Application Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
