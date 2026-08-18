"""Probe clamd PING from the same network as the worker."""

from __future__ import annotations

import socket

sock = socket.create_connection(("clamav", 3310), 5)
sock.sendall(b"zPING\0")
print(repr(sock.recv(64)))
sock.close()
