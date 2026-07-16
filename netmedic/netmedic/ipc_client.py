import json
import logging
import queue
import socket
import threading

from netmedic.config import Config
from netmedic.ipc_framing import IPC_SOCKET_TIMEOUT, encode_message, parse_message, recv_message

logger = logging.getLogger(__name__)


class PilotClient:
    """IPC client using one connection per request (matches server lifecycle)."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._session_token = None
                cls._instance._queue: queue.Queue = queue.Queue(maxsize=32)
                cls._instance._worker = threading.Thread(
                    target=cls._instance._worker_loop,
                    daemon=True,
                    name="PilotClientIPC",
                )
                cls._instance._worker.start()
        return cls._instance

    @classmethod
    def reset_singleton(cls):
        """Test helper: drop cached client state."""
        with cls._lock:
            cls._instance = None

    @property
    def _sock_path(self) -> str:
        return str(Config.get_state_dir() / "ipc.sock")

    def is_available(self) -> bool:
        import os
        return os.path.exists(self._sock_path)

    def _request(self, action: str, params: dict) -> dict:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._sock_path)
            sock.sendall(encode_message({"action": action, "params": params}))
            data = recv_message(sock, timeout=IPC_SOCKET_TIMEOUT)
            return parse_message(data)
        except (ConnectionRefusedError, FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("IPC request failed: %s", exc)
            return {"status": "error", "message": str(exc)}
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _refresh_session_token(self):
        result = self._request("get_session_token", {})
        if result.get("status") == "ok":
            self._session_token = result.get("session_token")

    def _worker_loop(self):
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            action, params, callback, confirmed = item
            try:
                request_params = dict(params)
                if confirmed:
                    request_params["confirmed"] = True
                    if not self._session_token:
                        self._refresh_session_token()
                    request_params["session_token"] = self._session_token

                result = self._request(action, request_params)
                if (
                    confirmed
                    and result.get("status") == "error"
                    and "token" in result.get("message", "").lower()
                ):
                    self._refresh_session_token()
                    request_params["session_token"] = self._session_token
                    result = self._request(action, request_params)

                from gi.repository import GLib

                GLib.idle_add(callback, result)
            except Exception as exc:
                logger.exception("IPC worker error")
                from gi.repository import GLib

                GLib.idle_add(callback, {"status": "error", "message": str(exc)})
            finally:
                self._queue.task_done()

    def shutdown(self, timeout: float = 2.0):
        """Stop the worker thread (best-effort)."""
        try:
            self._queue.put(None, timeout=1.0)
        except queue.Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=timeout)

    def ask(self, action, params, callback, *, confirmed: bool = False):
        try:
            self._queue.put((action, params, callback, confirmed), timeout=1.0)
        except queue.Full:
            from gi.repository import GLib

            GLib.idle_add(
                callback,
                {"status": "error", "message": "IPC client queue is full. Try again shortly."},
            )