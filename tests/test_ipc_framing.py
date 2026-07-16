from netmedic.ipc_framing import encode_message, parse_message, recv_message


def test_encode_message_uses_newline_delimiter():
    payload = encode_message({"action": "ping", "params": {}})
    assert payload.endswith(b"\n")
    assert parse_message(payload[:-1]) == {"action": "ping", "params": {}}


class _FakeSocket:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

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