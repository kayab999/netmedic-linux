"""Newline-delimited JSON framing for IPC messages."""
from __future__ import annotations

import json
import socket
from typing import Any, Dict, Optional

_MAX_MESSAGE_SIZE = 65_536
IPC_SOCKET_TIMEOUT = 30.0


def encode_message(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"


def recv_message(
    sock,
    max_size: int = _MAX_MESSAGE_SIZE,
    timeout: Optional[float] = IPC_SOCKET_TIMEOUT,
) -> bytes:
    """Read one newline-terminated JSON message from a socket."""
    if timeout is not None:
        sock.settimeout(timeout)
    buf = bytearray()
    # A delimiter exactly at max_size is valid, so read at most one byte past
    # the limit to detect it. Never accept or retain a longer line.
    while len(buf) <= max_size:
        remaining = max_size + 1 - len(buf)
        try:
            chunk = sock.recv(min(4096, remaining))
        except socket.timeout as exc:
            raise ValueError("IPC response timed out") from exc
        if not chunk:
            break
        buf.extend(chunk)
        if b"\n" in buf:
            line, _remainder = buf.split(b"\n", 1)
            if len(line) > max_size:
                raise ValueError(
                    f"IPC message exceeds maximum size of {max_size} bytes"
                )
            return line
    if not buf:
        raise ValueError("IPC connection closed before response")
    if len(buf) > max_size:
        raise ValueError(f"IPC message exceeds maximum size of {max_size} bytes")
    raise ValueError("IPC response incomplete")


def parse_message(data: bytes) -> Dict[str, Any]:
    return json.loads(data.decode("utf-8").strip())