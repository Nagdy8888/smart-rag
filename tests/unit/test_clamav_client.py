"""Unit tests for ClamAV client response parsing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smart_rag_core.gateways.clamav import (
    ClamAvClient,
    ClamAvEngineInfo,
    ScanDisposition,
    SignatureDatabaseInfo,
    _parse_scan_response,
    _parse_stats,
)


def test_parse_stats_reads_timestamp() -> None:
    """STATS lines map to signature database metadata."""

    databases = _parse_stats("daily.cld:27342:1700000000\n")
    assert len(databases) == 1
    assert databases[0].name == "daily.cld"
    assert databases[0].version == "27342"
    assert databases[0].timestamp is not None


def test_parse_scan_response_maps_found_to_infected() -> None:
    """FOUND responses become infected disposition."""

    disposition, threat, _detail = _parse_scan_response(
        b"stream: Eicar-Test-Signature FOUND"
    )
    assert disposition is ScanDisposition.INFECTED
    assert threat is not None


def test_parse_scan_response_maps_ok_to_clean() -> None:
    """OK responses become clean disposition."""

    disposition, threat, _detail = _parse_scan_response(b"stream: OK")
    assert disposition is ScanDisposition.CLEAN
    assert threat is None


def test_ping_accepts_null_terminated_pong() -> None:
    """Live clamd z-protocol terminates ``PONG`` with NUL."""

    from smart_rag_core.gateways.clamav import _clamd_text

    assert _clamd_text(b"PONG\x00") == "PONG"
    assert _parse_scan_response(b"stream: OK\x00")[0] is ScanDisposition.CLEAN


def test_version_string_supplies_signature_timestamp() -> None:
    """Modern clamd STATS omit CVD lines; VERSION still carries the date."""

    from smart_rag_core.gateways.clamav import _parse_version_signature_timestamp

    parsed = _parse_version_signature_timestamp(
        "ClamAV 1.5.4/28087/Sun Aug  9 06:24:56 2026"
    )
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 8


def test_oversize_stream_fails_closed_without_scan() -> None:
    """Oversize payloads fail closed as over_limit before INSTREAM."""

    client = ClamAvClient(host="unused", max_scan_bytes=16)
    result = client.scan_stream(
        b"x" * 32,
        engine_info=ClamAvEngineInfo(
            engine_version="ClamAV 1.4.3/1.4.3",
            functionality_level="90",
            signature_databases=(),
        ),
    )
    assert result.disposition is ScanDisposition.OVER_LIMIT
    assert result.bytes_examined == 0


def test_stale_signatures_fail_closed_without_instream() -> None:
    """Signatures older than 24h map to stale_signature before INSTREAM."""

    client = ClamAvClient(host="unused")
    stale = datetime.now(tz=UTC) - timedelta(hours=25)
    result = client.scan_stream(
        b"hello",
        engine_info=ClamAvEngineInfo(
            engine_version="ClamAV 1.4.3",
            functionality_level="90",
            signature_databases=(
                SignatureDatabaseInfo(
                    name="daily.cld",
                    version="1",
                    timestamp=stale,
                ),
            ),
        ),
    )
    assert result.disposition is ScanDisposition.STALE_SIGNATURE
    assert result.bytes_examined == 0


def test_incompatible_signatures_without_timestamps_fail_closed() -> None:
    """Healthy daemon with unusable signature metadata fails closed."""

    client = ClamAvClient(host="unused")
    result = client.scan_stream(
        b"hello",
        engine_info=ClamAvEngineInfo(
            engine_version="ClamAV 1.4.3",
            functionality_level="90",
            signature_databases=(
                SignatureDatabaseInfo(name="daily.cld", version="?", timestamp=None),
            ),
        ),
    )
    assert result.disposition is ScanDisposition.STALE_SIGNATURE
    assert "unavailable" in result.detail


def test_encrypted_scan_response_is_unscannable() -> None:
    """Encrypted/password ClamAV responses map to unscannable."""

    disposition, threat, detail = _parse_scan_response(b"stream: Encrypted.PDF ERROR")
    assert disposition is ScanDisposition.UNSCANNABLE
    assert threat is None
    assert "Encrypted" in detail


def test_archive_limit_exceeded_scan_response() -> None:
    """ClamAV archive expansion limits map to over_limit."""

    disposition, _threat, detail = _parse_scan_response(
        b"stream: MaxFileSize LIMIT EXCEEDED"
    )
    assert disposition is ScanDisposition.OVER_LIMIT
    assert "LIMIT" in detail.upper()
