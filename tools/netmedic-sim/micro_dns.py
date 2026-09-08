#!/usr/bin/env python3
"""Micro DNS responder for netmedic-sim scenario B.

Listens on 0.0.0.0:53 UDP, replies to ANY A query with 1.2.3.4 (or fixed).
No deps, no dnsmasq. Runs in router-ns (nmsim-*-r) as background job.

Response is minimal RFC 1035: copy QD, set QR=1, ANCOUNT=1, A record.
TTL 60, RDLENGTH 4.
"""
import socket
import struct
import sys

LISTEN = "0.0.0.0"
PORT = 53
FAKE_IP = "1.2.3.4"

def build_reply(data: bytes) -> bytes:
    if len(data) < 12:
        return b""
    txid = data[0:2]
    flags = 0x8180  # QR=1, RA=1, RCODE=0
    qdcount = struct.unpack("!H", data[4:6])[0]
    if qdcount < 1:
        return b""
    # Find end of QNAME
    pos = 12
    while pos < len(data) and data[pos] != 0:
        pos += 1 + data[pos]
    if pos + 5 > len(data):
        return b""
    pos += 5  # null + QTYPE(2) + QCLASS(2)
    qd = data[12:pos]
    # Header
    header = struct.pack("!HHHHHH", struct.unpack("!H", txid)[0], flags, qdcount, 1, 0, 0)
    # Answer: NAME pointer 0xC00C, TYPE A, CLASS IN, TTL 60, RDLEN 4, RDATA IP
    ip_parts = [int(x) for x in FAKE_IP.split(".")]
    answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + bytes(ip_parts)
    return header + qd + answer

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LISTEN, PORT))
    except OSError as exc:
        print(f"micro_dns bind failed {LISTEN}:{PORT}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"micro_dns listening {LISTEN}:{PORT} -> {FAKE_IP}", file=sys.stderr)
    while True:
        try:
            data, addr = sock.recvfrom(512)
            reply = build_reply(data)
            if reply:
                sock.sendto(reply, addr)
        except Exception as exc:
            print(f"micro_dns error: {exc}", file=sys.stderr)

if __name__ == "__main__":
    main()
