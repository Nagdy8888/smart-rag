"""Bounded Redis-protocol client for private Valkey limit and cache instances.

Connections are created per command and never at import time. Named ACL users
are a Phase 10 remainder; local Compose uses ``requirepass`` on an isolated
network per ADR-private-service-tls. Application keys always use prefixes
``limits:`` and ``cache:``.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Protocol
from urllib.parse import unquote, urlparse

LIMITS_KEY_PREFIX = "limits:"
CACHE_KEY_PREFIX = "cache:"


class ValkeyProtocolError(RuntimeError):
    """Raised when the Valkey RESP reply cannot be parsed."""


class ValkeyTimeoutError(TimeoutError):
    """Raised when connect or command time exceeds the configured bound."""


class ValkeyClient(Protocol):
    """Minimal command surface used by rate limits and retrieval cache."""

    def ping(self) -> bool:
        """Return True when PING succeeds inside the timeout."""
        ...

    def incr(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter and refresh its TTL. Returns the new value."""
        ...

    def get(self, key: str) -> bytes | None:
        """Return a raw value or None on miss."""
        ...

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """Set a value with a mandatory TTL."""
        ...

    def delete(self, key: str) -> None:
        """Delete one key. Missing keys are ignored."""
        ...


@dataclass(frozen=True, slots=True)
class _ValkeyTarget:
    """Parsed Redis URL without logging the password."""

    host: str
    port: int
    password: str | None
    db: int


def parse_valkey_url(url: str) -> _ValkeyTarget:
    """Parse a Redis-protocol URL.

    Args:
        url: ``redis://`` or ``valkey://`` URL. Password may be in the
            userinfo.

    Returns:
        Host, port, optional password, and database index.

    Raises:
        ValueError: If the URL is missing a host or uses an unsupported
            scheme.
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "valkey", "rediss", "valkeys"}:
        raise ValueError("unsupported_valkey_scheme")
    host = parsed.hostname
    if host is None or host == "":
        raise ValueError("valkey_host_required")
    password = unquote(parsed.password) if parsed.password else None
    db = 0
    if parsed.path and parsed.path not in {"", "/"}:
        tail = parsed.path.lstrip("/")
        if tail.isdigit():
            db = int(tail)
    return _ValkeyTarget(
        host=host,
        port=parsed.port or 6379,
        password=password,
        db=db,
    )


def _encode_command(*parts: str | bytes) -> bytes:
    """Encode one RESP array command.

    Args:
        parts: Command name and arguments.

    Returns:
        Wire bytes including CRLF terminators.
    """

    chunks = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        payload = part if isinstance(part, bytes) else part.encode("utf-8")
        chunks.append(f"${len(payload)}\r\n".encode())
        chunks.append(payload)
        chunks.append(b"\r\n")
    return b"".join(chunks)


def _read_line(sock: socket.socket) -> bytes:
    """Read one CRLF-terminated RESP line.

    Args:
        sock: Connected socket.

    Returns:
        Line without the CRLF.

    Raises:
        ValkeyProtocolError: On EOF or oversized line.
    """

    buf = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ValkeyProtocolError("valkey_eof")
        buf.extend(chunk)
        if len(buf) > 65536:
            raise ValkeyProtocolError("valkey_line_too_long")
        if buf.endswith(b"\r\n"):
            return bytes(buf[:-2])


def _read_reply(sock: socket.socket) -> object:
    """Decode one RESP value.

    Args:
        sock: Connected socket.

    Returns:
        Decoded Python value.

    Raises:
        ValkeyProtocolError: On unexpected type prefix.
        ValkeyTimeoutError: Propagated from the socket timeout.
    """

    header = _read_line(sock)
    if not header:
        raise ValkeyProtocolError("valkey_empty_reply")
    prefix = header[:1]
    rest = header[1:]
    if prefix == b"+":
        return rest.decode("utf-8")
    if prefix == b"-":
        raise ValkeyProtocolError(rest.decode("utf-8", errors="replace"))
    if prefix == b":":
        return int(rest.decode("ascii"))
    if prefix == b"$":
        length = int(rest.decode("ascii"))
        if length < 0:
            return None
        data = bytearray()
        while len(data) < length + 2:
            chunk = sock.recv(length + 2 - len(data))
            if not chunk:
                raise ValkeyProtocolError("valkey_eof")
            data.extend(chunk)
        if not data.endswith(b"\r\n"):
            raise ValkeyProtocolError("valkey_bulk_terminator")
        return bytes(data[:-2])
    raise ValkeyProtocolError("valkey_unsupported_type")


class SocketValkeyClient:
    """Per-command TCP RESP client. Does not retain sockets across calls.

    Args constructor stores the URL and timeout only. No network occurs
    until a command runs.
    """

    def __init__(self, url: str, *, timeout_seconds: float) -> None:
        """Store connection parameters without opening a socket.

        Args:
            url: Redis-protocol URL including credentials.
            timeout_seconds: Combined connect and command timeout.

        Raises:
            ValueError: If the URL cannot be parsed.
        """

        self._target = parse_valkey_url(url)
        self._timeout = timeout_seconds

    def ping(self) -> bool:
        """Send PING after optional AUTH/SELECT.

        Returns:
            True when the server replies PONG.

        Raises:
            ValkeyTimeoutError: On timeout.
            ValkeyProtocolError: On protocol or AUTH failure.
        """

        reply = self._execute("PING")
        return reply == "PONG" or reply == b"PONG"

    def incr(self, key: str, ttl_seconds: int) -> int:
        """INCR then EXPIRE the counter so every counter has a TTL.

        Args:
            key: Prefixed application key.
            ttl_seconds: Mandatory TTL.

        Returns:
            New counter value.

        Raises:
            ValkeyTimeoutError: On timeout.
            ValkeyProtocolError: On protocol failure.
        """

        value = self._execute("INCR", key)
        if not isinstance(value, int):
            raise ValkeyProtocolError("valkey_incr_not_int")
        self._execute("EXPIRE", key, str(ttl_seconds))
        return value

    def get(self, key: str) -> bytes | None:
        """GET one key.

        Args:
            key: Prefixed application key.

        Returns:
            Raw bytes or None.
        """

        value = self._execute("GET", key)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        raise ValkeyProtocolError("valkey_get_unexpected")

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """SET with EX so cache entries always expire.

        Args:
            key: Prefixed application key.
            value: Raw payload.
            ttl_seconds: Mandatory TTL.
        """

        self._execute("SET", key, value, "EX", str(ttl_seconds))

    def delete(self, key: str) -> None:
        """DEL one key.

        Args:
            key: Prefixed application key.
        """

        self._execute("DEL", key)

    def _execute(self, *parts: str | bytes) -> object:
        """Open a socket, AUTH/SELECT, run one command, and close.

        Args:
            parts: RESP command tokens.

        Returns:
            Decoded reply.

        Raises:
            ValkeyTimeoutError: On socket timeout.
            ValkeyProtocolError: On protocol errors.
        """

        target = self._target
        try:
            with socket.create_connection(
                (target.host, target.port),
                timeout=self._timeout,
            ) as sock:
                sock.settimeout(self._timeout)
                if target.password:
                    sock.sendall(_encode_command("AUTH", target.password))
                    _read_reply(sock)
                if target.db:
                    sock.sendall(_encode_command("SELECT", str(target.db)))
                    _read_reply(sock)
                sock.sendall(_encode_command(*parts))
                return _read_reply(sock)
        except TimeoutError as exc:
            raise ValkeyTimeoutError("valkey_timeout") from exc
        except OSError as exc:
            raise ValkeyTimeoutError("valkey_unavailable") from exc


@dataclass
class MemoryValkeyClient:
    """In-process Valkey stand-in for unit tests. Never opens sockets."""

    _values: dict[str, bytes] = field(default_factory=dict[str, bytes])
    _expiry: dict[str, float] = field(default_factory=dict[str, float])
    _lock: Lock = field(default_factory=Lock)
    fail_closed: bool = False

    def ping(self) -> bool:
        """Return True unless ``fail_closed`` is set.

        Returns:
            Availability flag.

        Raises:
            ValkeyTimeoutError: When tests simulate an outage.
        """

        if self.fail_closed:
            raise ValkeyTimeoutError("valkey_unavailable")
        return True

    def incr(self, key: str, ttl_seconds: int) -> int:
        """Increment a memory counter with TTL.

        Args:
            key: Application key.
            ttl_seconds: Mandatory TTL.

        Returns:
            New integer value.
        """

        if self.fail_closed:
            raise ValkeyTimeoutError("valkey_unavailable")
        with self._lock:
            self._expire_locked(key)
            current = int(self._values.get(key, b"0"))
            current += 1
            self._values[key] = str(current).encode("ascii")
            self._expiry[key] = monotonic() + ttl_seconds
            return current

    def get(self, key: str) -> bytes | None:
        """Return a stored value when unexpired.

        Args:
            key: Application key.

        Returns:
            Raw bytes or None.
        """

        if self.fail_closed:
            raise ValkeyTimeoutError("valkey_unavailable")
        with self._lock:
            self._expire_locked(key)
            return self._values.get(key)

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """Store a value with TTL.

        Args:
            key: Application key.
            value: Payload.
            ttl_seconds: Mandatory TTL.
        """

        if self.fail_closed:
            raise ValkeyTimeoutError("valkey_unavailable")
        with self._lock:
            self._values[key] = value
            self._expiry[key] = monotonic() + ttl_seconds

    def delete(self, key: str) -> None:
        """Drop one key.

        Args:
            key: Application key.
        """

        if self.fail_closed:
            raise ValkeyTimeoutError("valkey_unavailable")
        with self._lock:
            self._values.pop(key, None)
            self._expiry.pop(key, None)

    def _expire_locked(self, key: str) -> None:
        """Drop ``key`` when its TTL has elapsed.

        Args:
            key: Application key.
        """

        expires_at = self._expiry.get(key)
        if expires_at is not None and monotonic() >= expires_at:
            self._values.pop(key, None)
            self._expiry.pop(key, None)
