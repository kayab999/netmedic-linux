import socket
import json
import threading
import time
import logging

from netmedic.config import Config
from netmedic.ipc_framing import encode_message, recv_message, parse_message

logger = logging.getLogger(__name__)


class PilotClient:
    """Cliente IPC con conexión persistente y sincronización por hilo."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PilotClient, cls).__new__(cls)
                cls._instance.sock = None
                cls._instance._sock_lock = threading.Lock()
                cls._instance._session_token = None
                cls._instance._connect()
        return cls._instance

    @property
    def _sock_path(self) -> str:
        return str(Config.get_state_dir() / "ipc.sock")

    def _connect(self):
        max_retries = 5
        backoff = 1
        for i in range(max_retries):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self._sock_path)
                with self._sock_lock:
                    if self.sock:
                        try:
                            self.sock.close()
                        except OSError:
                            pass
                    self.sock = sock
                self._refresh_session_token()
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                logger.warning(
                    "Intento %d de conexión al socket fallido. Reintentando en %ds...",
                    i + 1,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
        with self._sock_lock:
            self.sock = None

    def _refresh_session_token(self):
        result = self._request_sync("get_session_token", {})
        if result.get("status") == "ok":
            self._session_token = result.get("session_token")

    def _request_sync(self, action, params):
        with self._sock_lock:
            if self.sock is None:
                return {"status": "error", "message": "Sin conexión al orquestador"}
            try:
                self.sock.sendall(encode_message({"action": action, "params": params}))
                data = recv_message(self.sock)
                return parse_message(data)
            except (BrokenPipeError, ConnectionResetError, OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("IPC sync request failed: %s", exc)
                return {"status": "error", "message": str(exc)}

    def ask(self, action, params, callback, *, confirmed: bool = False):
        def _task():
            from gi.repository import GLib

            request_params = dict(params)
            if confirmed:
                request_params["confirmed"] = True
                if self._session_token:
                    request_params["session_token"] = self._session_token
                else:
                    self._refresh_session_token()
                    request_params["session_token"] = self._session_token

            reconnect = False
            with self._sock_lock:
                if self.sock is None:
                    GLib.idle_add(callback, {"status": "error", "message": "Sin conexión al orquestador"})
                    return
                try:
                    self.sock.sendall(encode_message({"action": action, "params": request_params}))
                    data = recv_message(self.sock)
                    result = parse_message(data)
                    GLib.idle_add(callback, result)
                except (BrokenPipeError, ConnectionResetError, OSError, ValueError, json.JSONDecodeError):
                    reconnect = True

            if reconnect:
                self._connect()
                GLib.idle_add(callback, {"status": "error", "message": "Conexión perdida, reintentando..."})

        threading.Thread(target=_task, daemon=True).start()