import os
import socket
import json
import threading
import logging
from typing import Callable, Dict, Any, Optional

from netmedic.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)

_MAX_MESSAGE_SIZE = 65_536


class NetMedicIPCServer:
    def __init__(self, action_dispatcher: Callable[[str, Dict[str, Any]], Dict[str, Any]], lifecycle: LifecycleManager):
        self.sock_file = str(lifecycle.sock_file)
        self.action_dispatcher = action_dispatcher
        self.running = False
        self.server: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if os.path.exists(self.sock_file):
            os.remove(self.sock_file)

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.sock_file)
        os.chmod(self.sock_file, 0o600)
        self.server.listen(5)
        self.running = True

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logger.info("IPC Server en línea. Escuchando en %s", self.sock_file)

    def _recv_message(self, conn: socket.socket) -> bytes:
        """Reads until a complete JSON payload is received or the connection closes."""
        chunks = []
        total = 0
        while total < _MAX_MESSAGE_SIZE:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            try:
                json.loads(b"".join(chunks).decode("utf-8").strip())
                return b"".join(chunks)
            except json.JSONDecodeError:
                continue
        raise ValueError("IPC payload inválido o excede el tamaño máximo.")

    def _listen_loop(self):
        while self.running and self.server:
            try:
                self.server.settimeout(1.0)
                try:
                    conn, _ = self.server.accept()
                except socket.timeout:
                    continue

                with conn:
                    try:
                        data = self._recv_message(conn)
                    except ValueError as exc:
                        response = json.dumps({"status": "error", "message": str(exc)})
                        conn.sendall(response.encode("utf-8"))
                        continue

                    if data:
                        response = self._handle_payload(data)
                        conn.sendall(response.encode("utf-8"))
            except OSError:
                if self.running:
                    logger.error("Fallo en loop IPC", exc_info=True)
            except Exception:
                if self.running:
                    logger.error("Fallo en loop IPC", exc_info=True)

    def _handle_payload(self, data: bytes) -> str:
        try:
            payload = json.loads(data.decode("utf-8").strip())
            action = payload.get("action")
            params = payload.get("params", {})
            result = self.action_dispatcher(action, params)
            return json.dumps(result)
        except json.JSONDecodeError:
            return json.dumps({"status": "error", "message": "Payload JSON inválido."})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"Fallo interno del IPC: {exc}"})

    def stop(self):
        """Cierre seguro del socket durante el cleanup de NetMedic."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
            self.server = None
        logger.info("IPC Server detenido.")