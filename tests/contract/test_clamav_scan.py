"""ClamAV boundary contract tests."""

from __future__ import annotations

import pytest
from smart_rag_core.gateways.clamav import ClamAvClient, ScanDisposition

from tests.contract.integration_support import (
    clamav_reachable,
    packet8_clamav,
    read_process_env,
)

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _require_clamav() -> ClamAvClient:
    """Return a ClamAV client or skip/xfail based on gate flags."""

    host, port = packet8_clamav()
    if not clamav_reachable(host=host, port=port):
        require = read_process_env("SMART_RAG_REQUIRE_CLAMAV")
        if require == "1":
            pytest.fail("SMART_RAG_REQUIRE_CLAMAV=1 but ClamAV is unreachable")
        pytest.skip(f"ClamAV unreachable at {host}:{port}")
    return ClamAvClient(host=host, port=port, timeout_seconds=30.0)


def test_ping_is_health_only_not_scan_readiness() -> None:
    """PING proves daemon response only."""

    client = _require_clamav()
    assert client.ping() is True


def test_eicar_detected_and_clean_file_passes() -> None:
    """EICAR is infected; benign bytes are clean when signatures are fresh."""

    client = _require_clamav()
    engine = client.read_engine_info()
    client.assert_scan_ready(engine)
    infected = client.scan_stream(EICAR, engine_info=engine)
    assert infected.disposition is ScanDisposition.INFECTED
    clean = client.scan_stream(b"hello-clean-fixture\n", engine_info=engine)
    assert clean.disposition is ScanDisposition.CLEAN
