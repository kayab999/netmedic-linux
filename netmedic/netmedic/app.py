import gi
import logging
import sys
import os
import signal
import fcntl
import argparse
import time
from logging.handlers import RotatingFileHandler
from netmedic.config import Config
from netmedic.ui import MainWindow
from netmedic.network import NetworkMedic
from netmedic.ipc_bridge import NetMedicIPCServer

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

_medic_instance = None

def handle_signals(signum, frame):
    """Handler para señales de terminación con cleanup garantizado."""
    sig_name = signal.Signals(signum).name
    logging.info(f"Received signal {sig_name} ({signum}). Starting emergency cleanup...")
    
    # 1. Cleanup de emergencia sin dependencias externas
    try:
        from netmedic.ipc_bridge import SOCK_FILE, PID_FILE
        for path in [SOCK_FILE, PID_FILE]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass
        
    # 2. Cleanup completo usando instancia global si está disponible
    try:
        if _medic_instance is not None:
            _medic_instance.cleanup()
    except Exception as e:
        logging.error(f"Cleanup failed: {e}")
    
    sys.exit(0)

def main():
    global _medic_instance
    # ... args parser ...
    
    # 3. Inicialización
    _medic_instance = NetworkMedic()
    
    # 4. Lock e IPC (resto de lógica...)

_lock_fd = None

def acquire_instance_lock():
    """
    Usa fcntl para asegurar que solo una instancia de la app corre a la vez.
    Mantiene el file descriptor abierto durante toda la vida del proceso.
    """
    global _lock_fd
    lock_file = Config.get_state_dir() / "netmedic.lock"
    
    try:
        # Abrir o crear el archivo de lock
        _lock_fd = open(lock_file, "w")
        # Intentar obtener un lock exclusivo sin bloquear (NB = Non-blocking)
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Escribir el PID actual por si sirve de diagnóstico
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        return True
    except (IOError, BlockingIOError):
        return False

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
    if not acquire_instance_lock():
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

    # 4. Iniciar el servidor IPC
    def mock_dispatcher(action, params):
        logging.info(f"Comando recibido vía IPC: {action} con params: {params}")
        return {"status": "success", "data": f"Comando {action} recibido por el Orquestador"}

    ipc_server = NetMedicIPCServer(action_dispatcher=mock_dispatcher)
    ipc_server.start()

    # 5. Inicialización de App
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
        ipc_server.stop()

if __name__ == "__main__":
    main()
