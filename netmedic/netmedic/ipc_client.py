import socket
import json
import os
import threading
import time
import logging
from gi.repository import GLib

class PilotClient:
    """Cliente con conexión persistente y pool de hilos para latencia cero."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PilotClient, cls).__new__(cls)
                cls._instance.sock = None
                cls._instance._connect()
        return cls._instance

    def _connect(self):
        max_retries = 5
        backoff = 1
        for i in range(max_retries):
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(os.path.expanduser("~/.local/state/netmedic/ipc.sock"))
                return
            except (ConnectionRefusedError, FileNotFoundError):
                logging.warning(f"Intento {i+1} de conexión al socket fallido. Reintentando en {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
        self.sock = None

    def ask(self, action, params, callback):
        def _task():
            if self.sock is None:
                GLib.idle_add(callback, {"status": "error", "message": "Sin conexión al orquestador"})
                return
            try:
                payload = json.dumps({"action": action, "params": params})
                self.sock.sendall(payload.encode() + b'\n')
                data = self.sock.recv(4096)
                result = json.loads(data.decode())
                GLib.idle_add(callback, result)
            except (BrokenPipeError, ConnectionResetError):
                self._connect()
                GLib.idle_add(callback, {"status": "error", "message": "Conexión perdida, reintentando..."})
        
        threading.Thread(target=_task, daemon=True).start()
