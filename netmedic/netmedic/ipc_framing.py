"""Newline-delimited JSON framing for IPC messages."""
from __future__ import annotations

import json
from typing import Any, Dict

_MAX_MESSAGE_SIZE = 65_536


def encode_message(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"


def recv_message(sock, max_size: int = _MAX_MESSAGE_SIZE) -> bytes:
    """Read one newline-terminated JSON message from a socket."""
    buf = bytearray()
    while len(buf) < max_size:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf.extend(chunk)
        if b"\n" in buf:
            line, _remainder = buf.split(b"\n", 1)
            return line
    raise ValueError("IPC response incomplete")


def parse_message(data: bytes) -> Dict[str, Any]:
    return json.loads(data.decode("utf-8").strip())