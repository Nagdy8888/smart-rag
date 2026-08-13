"""Unit tests for ClamAV client response parsing."""

from __future__ import annotations

from smart_rag_core.gateways.clamav import (
    ClamAvClient,
    ClamAvEngineInfo,
    ScanDisposition,
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
