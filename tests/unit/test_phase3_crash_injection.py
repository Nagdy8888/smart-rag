"""Fault-injection tests for Packet 8 crash points."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from smart_rag_core.gateways.clamav import ClamAvClient, ClamAvEngineInfo
from smart_rag_core.gateways.storage import StorageGatewayError
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.scan import ObjectScanInput, scan_object_bytes
from smart_rag_core.retrieval.bm25_indexer import Bm25ProjectionRow

from tests.unit.typed_attrs import set_attr


def test_storage_download_mid_crash_does_not_scan() -> None:
    """Storage mid-download failure never reaches ClamAV or scan evidence."""

    class _Storage:
        """Storage double that fails before any bytes are returned."""

        def download_object(self, *, bucket: str, object_path: str) -> bytes:
            """Raise StorageGatewayError without returning object bytes.

            Args:
                bucket: Unused bucket name.
                object_path: Unused object path.

            Returns:
                Never returns; always raises.

            Raises:
                StorageGatewayError: Simulated mid-download crash.
            """

            raise StorageGatewayError("connection reset mid-download")

    clamav = MagicMock(spec=ClamAvClient)
    with pytest.raises(StorageGatewayError, match="mid-download"):
        scan_object_bytes(
            _Storage(),  # type: ignore[arg-type]
            clamav,
            ObjectScanInput(
                bucket="documents-quarantine",
                path="a/b/c.bin",
                expected_hash="abc",
                expected_bytes=3,
            ),
        )
    clamav.read_engine_info.assert_not_called()
    clamav.scan_stream.assert_not_called()


def test_scan_mid_crash_before_scan_event() -> None:
    """ClamAV crash after download/hash leaves no scan_stream result to persist."""

    payload = b"fixture-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    class _Storage:
        """Storage double that returns fixture bytes then lets ClamAV crash."""

        def download_object(self, *, bucket: str, object_path: str) -> bytes:
            """Return the fixture payload for hash comparison.

            Args:
                bucket: Unused bucket name.
                object_path: Unused object path.

            Returns:
                The precomputed fixture bytes.
            """

            return payload

    clamav = MagicMock(spec=ClamAvClient)
    clamav.read_engine_info.return_value = ClamAvEngineInfo(
        engine_version="ClamAV 1.4.3",
        functionality_level="90",
        signature_databases=(),
    )
    clamav.scan_stream.side_effect = RuntimeError("clamd killed mid-scan")
    with pytest.raises(RuntimeError, match="mid-scan"):
        scan_object_bytes(
            _Storage(),  # type: ignore[arg-type]
            clamav,
            ObjectScanInput(
                bucket="documents-quarantine",
                path="a/b/c.bin",
                expected_hash=digest,
                expected_bytes=len(payload),
            ),
        )


def _projection_row(version_id: object, document_id: object) -> Bm25ProjectionRow:
    """Build one synthetic ParadeDB projection row."""

    return Bm25ProjectionRow(
        chunk_id=uuid4(),
        version_id=version_id,  # type: ignore[arg-type]
        document_id=document_id,  # type: ignore[arg-type]
        title_search="t",
        heading_search=None,
        alias_search=None,
        body_search="body",
        language="en",
        acl_scope_id="company_visible",
        is_current=False,
        visibility_generation=1,
        normalization_version="arabic_norm_v1",
        content_hash="abc",
    )


def test_bm25_mid_batch_crash_before_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash mid-upsert batch must not verify or flip Hybrid Ready."""

    monkeypatch.setattr(
        "smart_rag_core.ingestion.bm25_projection.DEFAULT_BM25_UPSERT_BATCH_SIZE",
        1,
    )
    version_id = uuid4()
    document_id = uuid4()
    service = Bm25ProjectionService(MagicMock(), MagicMock())
    calls = {"upsert": 0, "verify": 0}

    class _Indexer:
        """Indexer that crashes on the second upsert batch."""

        def ensure_projection_schema(self) -> None:
            """No-op schema ensure for the crash-injection fixture."""

            return None

        def upsert_batch(self, batch: object) -> None:
            """Increment the upsert counter and fail after the first batch.

            Args:
                batch: Unused projection batch.

            Raises:
                RuntimeError: Simulated mid-batch crash on the second call.
            """

            calls["upsert"] += 1
            if calls["upsert"] > 1:
                raise RuntimeError("bm25 mid-batch crash")

    class _Verifier:
        """Verifier that must never run after a mid-batch crash."""

        def verify_version(self, _version_id: object) -> object:
            """Fail the test if verify is reached after the upsert crash.

            Args:
                _version_id: Unused document version identifier.

            Returns:
                Never returns; always raises.

            Raises:
                AssertionError: Verify ran after a mid-batch crash.
            """

            calls["verify"] += 1
            raise AssertionError("verify must not run after mid-batch crash")

    service._indexer = _Indexer()  # type: ignore[method-assign]
    service._verifier = _Verifier()  # type: ignore[method-assign]
    service._load_projection_rows = lambda _vid: [  # type: ignore[method-assign]
        _projection_row(version_id, document_id),
        _projection_row(version_id, document_id),
    ]
    with pytest.raises(RuntimeError, match="mid-batch"):
        service.process_upsert_job(version_id=version_id, job_id=uuid4())
    assert calls["upsert"] == 2
    assert calls["verify"] == 0


def test_hybrid_ready_flip_blocked_before_bm25_verify() -> None:
    """finalize_hybrid_ready without a processing BM25 job is rejected.

    Live SQL is exercised in ``test_hybrid_lifecycle`` when Postgres is up;
    this unit test documents the service ordering: verify must precede finalize.
    """

    version_id = uuid4()
    service = Bm25ProjectionService(MagicMock(), MagicMock())

    class _Indexer:
        """Indexer that accepts every upsert without writing Hybrid Ready."""

        def ensure_projection_schema(self) -> None:
            """No-op schema ensure for the failed-verify fixture."""

            return None

        def upsert_batch(self, _batch: object) -> None:
            """Accept the batch without persisting a Hybrid Ready flip.

            Args:
                _batch: Unused projection batch.
            """

            return None

    class _FailedVerifier:
        """Verifier that always reports a failed BM25 check."""

        def verify_version(self, _version_id: object) -> object:
            """Return a stub result with ``passed`` set to False.

            Args:
                _version_id: Unused document version identifier.

            Returns:
                MagicMock whose ``passed`` attribute is False.
            """

            result = MagicMock()
            result.passed = False
            return result

    service._indexer = _Indexer()  # type: ignore[method-assign]
    service._verifier = _FailedVerifier()  # type: ignore[method-assign]
    service._load_projection_rows = lambda _vid: [  # type: ignore[method-assign]
        _projection_row(version_id, uuid4())
    ]
    supabase = MagicMock()
    set_attr(service, "_supabase", supabase)
    assert service.process_upsert_job(version_id=version_id, job_id=uuid4()) is False
    supabase.cursor.assert_not_called()
