"""ClamAV ``clamd`` client for exact-object stream scanning.

``PING`` proves daemon responsiveness only. Scan readiness requires fresh signed
database metadata from ``STATS``/``VERSION`` and a successful bounded ``INSTREAM``
scan of the exact object bytes.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

SCAN_CONFIG_VERSION = "scan_v1"
SIGNATURE_MAX_AGE_HOURS = 24
DEFAULT_SCAN_MAX_BYTES = 104_857_600
DEFAULT_SCAN_TIMEOUT_SECONDS = 120.0


class ClamAvError(Exception):
    """Raised when ClamAV communication or readiness checks fail."""


class ScanDisposition(StrEnum):
    """Normalized scan outcomes mapped to ``app.scan_result``."""

    CLEAN = "clean"
    INFECTED = "infected"
    UNSCANNABLE = "unscannable"
    STALE_SIGNATURE = "stale_signature"
    OVER_LIMIT = "over_limit"
    HASH_MISMATCH = "hash_mismatch"


@dataclass(frozen=True, slots=True)
class SignatureDatabaseInfo:
    """One signature database entry reported by ``clamd`` ``STATS``."""

    name: str
    version: str
    timestamp: datetime | None


@dataclass(frozen=True, slots=True)
class ClamAvEngineInfo:
    """Engine and signature metadata captured before scanning."""

    engine_version: str
    functionality_level: str | None
    signature_databases: tuple[SignatureDatabaseInfo, ...]
    config_version: str = SCAN_CONFIG_VERSION


@dataclass(frozen=True, slots=True)
class ClamAvScanResult:
    """Result of scanning one exact byte stream."""

    disposition: ScanDisposition
    engine_info: ClamAvEngineInfo
    bytes_examined: int
    signature_db_ids: dict[str, str]
    signature_db_timestamp: datetime | None
    threat_name: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class ClamAvClient:
    """Minimal ``clamd`` TCP client for health, metadata, and ``INSTREAM`` scans."""

    host: str
    port: int = 3310
    timeout_seconds: float = DEFAULT_SCAN_TIMEOUT_SECONDS
    signature_max_age: timedelta = timedelta(hours=SIGNATURE_MAX_AGE_HOURS)
    max_scan_bytes: int = DEFAULT_SCAN_MAX_BYTES

    def ping(self) -> bool:
        """Return whether ``clamd`` responds to ``PING``.

        Returns:
            ``True`` when the daemon returns ``PONG``. This does **not** prove
            scan readiness or signature freshness.
        """

        response = self._command(b"zPING\0")
        return _clamd_text(response) == "PONG"

    def read_engine_info(self) -> ClamAvEngineInfo:
        """Read engine version and signature database metadata.

        Returns:
            Parsed engine and signature database metadata.

        Raises:
            ClamAvError: When daemon responses cannot be parsed.
        """

        version_raw = _clamd_text(self._command(b"zVERSION\0"))
        stats_raw = _clamd_text(self._command(b"zSTATS\0"))
        databases = _parse_stats(stats_raw)
        functionality = _parse_functionality(version_raw)
        return ClamAvEngineInfo(
            engine_version=version_raw,
            functionality_level=functionality,
            signature_databases=databases,
        )

    def assert_scan_ready(self, engine_info: ClamAvEngineInfo) -> datetime:
        """Fail closed when signatures are stale or unknown.

        Args:
            engine_info: Metadata from :meth:`read_engine_info`.

        Returns:
            The newest signature database timestamp used for the readiness gate.

        Raises:
            ClamAvError: When no database timestamps exist or the newest is too old.
        """

        timestamps = [
            db.timestamp
            for db in engine_info.signature_databases
            if db.timestamp is not None
        ]
        if not timestamps and engine_info.engine_version:
            parsed = _parse_version_signature_timestamp(engine_info.engine_version)
            if parsed is not None:
                timestamps = [parsed]
        if not timestamps:
            raise ClamAvError("signature database timestamps unavailable")
        newest = max(timestamps)
        age = datetime.now(tz=UTC) - newest
        if age > self.signature_max_age:
            raise ClamAvError(
                f"signature databases older than {self.signature_max_age}: age={age}"
            )
        return newest

    def scan_stream(
        self, data: bytes, *, engine_info: ClamAvEngineInfo
    ) -> ClamAvScanResult:
        """Scan one exact byte stream via ``INSTREAM`` (never a directory).

        Args:
            data: Exact object bytes to scan.
            engine_info: Metadata captured immediately before scanning.

        Returns:
            Normalized scan result. Oversize inputs fail closed as ``over_limit``.

        Raises:
            ClamAvError: On transport failures before a normalized result exists.
        """

        if len(data) > self.max_scan_bytes:
            return ClamAvScanResult(
                disposition=ScanDisposition.OVER_LIMIT,
                engine_info=engine_info,
                bytes_examined=0,
                signature_db_ids=_signature_ids(engine_info),
                signature_db_timestamp=_newest_signature_timestamp(engine_info),
                threat_name=None,
                detail=f"object exceeds scan max bytes {self.max_scan_bytes}",
            )

        try:
            newest = self.assert_scan_ready(engine_info)
        except ClamAvError as exc:
            return ClamAvScanResult(
                disposition=ScanDisposition.STALE_SIGNATURE,
                engine_info=engine_info,
                bytes_examined=0,
                signature_db_ids=_signature_ids(engine_info),
                signature_db_timestamp=_newest_signature_timestamp(engine_info),
                threat_name=None,
                detail=str(exc),
            )

        response = self._instream(data)
        disposition, threat, detail = _parse_scan_response(response)
        return ClamAvScanResult(
            disposition=disposition,
            engine_info=engine_info,
            bytes_examined=len(data),
            signature_db_ids=_signature_ids(engine_info),
            signature_db_timestamp=newest,
            threat_name=threat,
            detail=detail,
        )

    def _command(self, payload: bytes) -> bytes:
        """Send one ``clamd`` z-protocol command and read the NUL-terminated reply."""

        try:
            with socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_seconds,
            ) as sock:
                sock.sendall(payload)
                sock.shutdown(socket.SHUT_WR)
                return _recv_until_nul(sock)
        except OSError as exc:
            raise ClamAvError(f"clamd transport failure: {exc}") from exc

    def _instream(self, data: bytes) -> bytes:
        """Execute ``INSTREAM`` for one byte sequence."""

        try:
            with socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_seconds,
            ) as sock:
                sock.sendall(b"zINSTREAM\0")
                offset = 0
                while offset < len(data):
                    chunk = data[offset : offset + 8192]
                    sock.sendall(struct.pack("!I", len(chunk)))
                    sock.sendall(chunk)
                    offset += len(chunk)
                sock.sendall(struct.pack("!I", 0))
                return _recv_until_nul(sock)
        except OSError as exc:
            raise ClamAvError(f"clamd instream failure: {exc}") from exc


def _recv_until_nul(sock: socket.socket) -> bytes:
    """Read one clamd z-protocol reply, stopping at the first NUL.

    clamd keeps the TCP session open after ``zCOMMAND`` replies. Reading until
    EOF therefore blocks until the socket timeout instead of returning ``PONG``,
    ``VERSION``, ``STATS``, or ``INSTREAM`` results.

    Args:
        sock: Connected clamd socket with a read timeout.

    Returns:
        Raw reply bytes including the terminating NUL when present.

    Raises:
        OSError: When the socket read fails.
    """

    chunks: list[bytes] = []
    while True:
        part = sock.recv(4096)
        if not part:
            break
        chunks.append(part)
        if b"\x00" in part:
            break
    return b"".join(chunks)


def _clamd_text(raw: bytes) -> str:
    """Decode a ``clamd`` z-protocol payload, dropping trailing NULs.

    Args:
        raw: Bytes returned by ``clamd``.

    Returns:
        Unicode text without surrounding whitespace or NUL terminators.
    """

    return raw.decode("utf-8", errors="replace").strip("\x00 \t\r\n")


def _parse_version_signature_timestamp(version_raw: str) -> datetime | None:
    """Parse the CVD date from a ``clamd`` ``VERSION`` string.

    Args:
        version_raw: Example ``ClamAV 1.5.4/28087/Sun Aug  9 06:24:56 2026``.

    Returns:
        Timezone-aware UTC timestamp, or ``None`` when the date is absent.
    """

    from email.utils import parsedate_to_datetime

    parts = version_raw.split("/")
    if len(parts) < 3:
        return None
    try:
        parsed = parsedate_to_datetime(parts[2].strip())
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_stats(raw: str) -> tuple[SignatureDatabaseInfo, ...]:
    """Parse ``STATS`` lines of the form ``name:version:timestamp``."""

    databases: list[SignatureDatabaseInfo] = []
    for line in raw.splitlines():
        parts = line.strip().split(":")
        if len(parts) < 2:
            continue
        name = parts[0]
        version = parts[1]
        timestamp: datetime | None = None
        if len(parts) >= 3 and parts[2].isdigit():
            timestamp = datetime.fromtimestamp(int(parts[2]), tz=UTC)
        databases.append(
            SignatureDatabaseInfo(name=name, version=version, timestamp=timestamp)
        )
    return tuple(databases)


def _parse_functionality(version_raw: str) -> str | None:
    """Extract functionality level token from ``VERSION`` output when present."""

    if "/" not in version_raw:
        return None
    tail = version_raw.split("/", 1)[1]
    return tail.split()[0] if tail else None


def _parse_scan_response(raw: bytes) -> tuple[ScanDisposition, str | None, str]:
    """Map ``clamd`` ``INSTREAM`` response text to disposition."""

    text = _clamd_text(raw)
    upper = text.upper()
    if not text:
        return ScanDisposition.UNSCANNABLE, None, "empty clamd response"
    if "FOUND" in upper:
        threat = text.split(":", 1)[-1].strip() if ":" in text else text
        return ScanDisposition.INFECTED, threat, text
    if "OK" in upper and "FOUND" not in upper:
        return ScanDisposition.CLEAN, None, text
    if "ENCRYPTED" in upper or "PASSWORD" in upper:
        return ScanDisposition.UNSCANNABLE, None, text
    if "LIMIT EXCEEDED" in upper or "MAX" in upper:
        return ScanDisposition.OVER_LIMIT, None, text
    if "ERROR" in upper:
        return ScanDisposition.UNSCANNABLE, None, text
    return ScanDisposition.UNSCANNABLE, None, text


def _signature_ids(engine_info: ClamAvEngineInfo) -> dict[str, str]:
    """Build signature database id/version map for persistence."""

    return {db.name: db.version for db in engine_info.signature_databases}


def _newest_signature_timestamp(engine_info: ClamAvEngineInfo) -> datetime | None:
    """Return the newest signature timestamp when any exist."""

    timestamps = [
        db.timestamp
        for db in engine_info.signature_databases
        if db.timestamp is not None
    ]
    return max(timestamps) if timestamps else None
