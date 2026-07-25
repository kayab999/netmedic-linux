import json
import socket
import threading

import pytest

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_bridge import NetMedicIPCServer
from netmedic.ipc_framing import recv_message
from netmedic.ipc_security import IPCSession
from netmedic.ipc_sync_client import SyncIPCClient
from netmedic.lifecycle import LifecycleManager


@pytest.fixture
def ipc_server(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    lifecycle = LifecycleManager()
    session = IPCSession()
    session.issue_token()

    from netmedic.network import NetworkMedic

    server = NetMedicIPCServer(create_action_dispatcher(NetworkMedic(), session), lifecycle)
    server.start()
    yield server, session, str(lifecycle.sock_file)
    server.stop()


def test_unix_socket_round_trip(ipc_server):
    _, session, sock_path = ipc_server
    client = SyncIPCClient(sock_path=sock_path)

    token_result = client.request("get_session_token")
    assert token_result["status"] == "ok"
    assert token_result["session_token"] == session.get_token()

    status_result = client.request("network_status")
    assert status_result["status"] == "ok"
    assert "message" in status_result


def test_oversized_payload_rejected(ipc_server):
    _, _, sock_path = ipc_server
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(sock_path)
    try:
        try:
            sock.sendall(b"x" * 70000 + b"\n")
        except BrokenPipeError:
            # Server may close early after size violation; that is a valid reject.
            return
        try:
            data = recv_message(sock, timeout=5.0)
            payload = json.loads(data.decode())
            assert payload["status"] == "error"
        except (ValueError, BrokenPipeError, ConnectionResetError):
            # Connection closed without a clean JSON error is still a rejection.
            pass
    finally:
        sock.close()


def test_ipc_server_handles_concurrent_clients(ipc_server):
    _, _, sock_path = ipc_server
    results = []
    lock = threading.Lock()

    def worker():
        client = SyncIPCClient(sock_path=sock_path)
        result = client.request("donate")
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == 3
    assert all(item.get("status") == "ok" for item in results)