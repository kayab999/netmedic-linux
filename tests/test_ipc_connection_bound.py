"""Regression: accepted IPC connections must be bounded, not just workers."""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from netmedic import ipc_bridge
from netmedic.ipc_bridge import NetMedicIPCServer
from netmedic.ipc_framing import recv_message


def _connect(path: Path, timeout: float = 2.0) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(path))
    return sock


def _request(path: Path) -> dict[str, Any]:
    sock = _connect(path, timeout=3.0)
    try:
        sock.sendall(b'{"action":"ping","params":{}}\n')
        return json.loads(recv_message(sock, timeout=3.0).decode())
    finally:
        sock.close()


def test_connection_limit_rejects_excess_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ipc_bridge, "_MAX_CONNECTIONS", 2)
    lifecycle = SimpleNamespace(sock_file=tmp_path / "netmedic.sock")
    server = NetMedicIPCServer(
        lambda action, params, **_: {"status": "ok", "message": "pong"},
        lifecycle,  # type: ignore[arg-type]
    )
    server.start()
    path = Path(lifecycle.sock_file)

    blockers: list[socket.socket] = []
    try:
        # Occupy every slot with clients that never send a complete message.
        for _ in range(2):
            blockers.append(_connect(path))
        time.sleep(0.2)

        excess = _connect(path)
        try:
            # The server must close it immediately instead of queueing it.
            assert excess.recv(1) == b""
        finally:
            excess.close()
    finally:
        for sock in blockers:
            sock.close()

    deadline = time.monotonic() + 5.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            assert _request(path) == {"status": "ok", "message": "pong"}
            break
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.05)
    else:
        server.stop()
        raise AssertionError(f"server did not recover after saturation: {last_error!r}")

    server.stop()
