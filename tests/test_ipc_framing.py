import socket
from unittest.mock import MagicMock

import pytest

from netmedic.ipc_framing import encode_message, parse_message, recv_message


def test_encode_message_uses_newline_delimiter():
    payload = encode_message({"action": "ping", "params": {}})
    assert payload.endswith(b"\n")
    assert parse_message(payload[:-1]) == {"action": "ping", "params": {}}


class _FakeSocket:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def settimeout(self, _timeout):
        return None

    def recv(self, size: int) -> bytes:
        if self._pos >= len(self._data):
            return b""
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_recv_message_reads_until_newline():
    sock = _FakeSocket(b'{"status":"ok"}\n')
    assert recv_message(sock) == b'{"status":"ok"}'
    assert parse_message(b'{"status":"ok"}') == {"status": "ok"}


def test_recv_message_timeout_raises():
    sock = MagicMock()
    sock.recv.side_effect = socket.timeout("timed out")
    with pytest.raises(ValueError, match="timed out"):
        recv_message(sock, timeout=1.0)


class _ChunkedSocket:
    """Return at most *chunk* bytes per recv, ignoring the requested size."""

    def __init__(self, data: bytes, chunk: int):
        self._data = data
        self._chunk = chunk
        self._pos = 0

    def settimeout(self, _timeout):
        return None

    def recv(self, size: int) -> bytes:
        if self._pos >= len(self._data):
            return b""
        take = min(size, self._chunk, len(self._data) - self._pos)
        chunk = self._data[self._pos : self._pos + take]
        self._pos += len(chunk)
        return chunk


def test_recv_message_accepts_limit_minus_one():
    sock = _FakeSocket(b"1234567\n")
    assert recv_message(sock, max_size=8) == b"1234567"


def test_recv_message_accepts_exact_limit():
    sock = _FakeSocket(b"12345678\n")
    assert recv_message(sock, max_size=8) == b"12345678"


def test_recv_message_accepts_exact_limit_split_before_delimiter():
    # The newline arrives alone after the buffer already holds max_size bytes.
    sock = _ChunkedSocket(b"12345678\n", chunk=4)
    assert recv_message(sock, max_size=8) == b"12345678"


def test_recv_message_rejects_limit_plus_one():
    sock = _FakeSocket(b"123456789\n")
    with pytest.raises(ValueError, match="exceeds maximum size"):
        recv_message(sock, max_size=8)


def test_recv_message_rejects_delimiter_after_limit_across_chunks():
    # 9 bytes then newline: the delimiter lies just past the limit and the
    # final read must not overrun into it.
    sock = _ChunkedSocket(b"123456789\n", chunk=4)
    with pytest.raises(ValueError, match="exceeds maximum size"):
        recv_message(sock, max_size=8)


def test_recv_message_rejects_large_overrun_in_one_chunk():
    # Old loop could read 4096 bytes past the check and accept a delimiter
    # beyond max_size.
    sock = _FakeSocket(b"x" * 11 + b"\n")
    with pytest.raises(ValueError, match="exceeds maximum size"):
        recv_message(sock, max_size=10)


def test_recv_message_still_reports_incomplete_without_delimiter():
    sock = _FakeSocket(b"1234567")
    with pytest.raises(ValueError, match="incomplete"):
        recv_message(sock, max_size=8)