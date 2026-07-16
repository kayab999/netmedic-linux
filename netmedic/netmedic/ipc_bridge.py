import json
import logging
import os
import socket
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from netmedic.ipc_framing import IPC_SOCKET_TIMEOUT, encode_message, recv_message
from netmedic.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)

_MAX_WORKERS = 4
_SO_PEERCRED = 17


def _peer_credentials(conn: socket.socket) -> tuple[int, int]:
    """Return (pid, uid) for the connected peer, or (-1, -1) if unavailable."""
    try:
        cred = conn.getsockopt(socket.SOL_SOCKET, _SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, _gid = struct.unpack("3i", cred)
        return pid, uid
    except OSError:
        return -1, -1


class NetMedicIPCServer:
    def __init__(self, action_dispatcher: Callable[..., Dict[str, Any]], lifecycle: LifecycleManager):
        self.sock_file = str(lifecycle.sock_file)
        self.action_dispatcher = action_dispatcher
        self.running = False
        self.server: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self._pool = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="IPCWorker")

    def start(self):
        if os.path.exists(self.sock_file):
            os.remove(self.sock_file)

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.sock_file)
        os.chmod(self.sock_file, 0o600)
        self.server.listen(5)
        self.running = True

        self.thread = threading.Thread(target=self._listen_loop, daemon=True, name="IPCListener")
        self.thread.start()
        logger.info("IPC server listening on %s", self.sock_file)

    def _listen_loop(self):
        while self.running and self.server:
            try:
                self.server.settimeout(1.0)
                try:
                    conn, _ = self.server.accept()
                except socket.timeout:
                    continue
                self._pool.submit(self._handle_connection, conn)
            except OSError:
                if self.running:
                    logger.error("IPC accept loop failure", exc_info=True)
            except Exception:
                if self.running:
                    logger.error("IPC accept loop failure", exc_info=True)

    def _handle_connection(self, conn: socket.socket):
        peer_pid, peer_uid = _peer_credentials(conn)
        with conn:
            try:
                data = recv_message(conn, timeout=IPC_SOCKET_TIMEOUT)
            except ValueError as exc:
                conn.sendall(encode_message({"status": "error", "message": str(exc)}))
                return

            if data:
                result = self._handle_payload(data, peer_pid=peer_pid, peer_uid=peer_uid)
                conn.sendall(encode_message(result))
            else:
                conn.sendall(encode_message({"status": "error", "message": "Empty request."}))

    def _handle_payload(self, data: bytes, *, peer_pid: int, peer_uid: int) -> Dict[str, Any]:
        try:
            payload = json.loads(data.decode("utf-8").strip())
            action = payload.get("action")
            params = payload.get("params", {})
            return self.action_dispatcher(
                action, params, peer_pid=peer_pid, peer_uid=peer_uid
            )
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON payload."}
        except Exception:
            logger.exception("IPC payload handling failed")
            return {"status": "error", "message": "Internal IPC error."}

    def stop(self):
        """Gracefully stop the IPC server."""
        self.running = False
        self._pool.shutdown(wait=True, cancel_futures=False)
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
            self.server = None
        logger.info("IPC server stopped.")