"""Unit tests for hybrid-index scan and governance loading."""

from __future__ import annotations

from uuid import uuid4

import pytest
from smart_rag_agents.ingestion.index_graph import (
    IngestionIndexState,
    allow_index_without_scan,
    content_class_from_payload,
    declared_category_disposition,
    index_scan_gate_allows,
    load_external_processing_input,
    mark_parsing_for_index,
    provider_matrix_verified,
)
from smart_rag_core.ingestion.limits import EXTERNAL_PROCESSING_POLICY_VERSION
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
)


def _index_state(
    *, attestation: str | None, category: str | None
) -> IngestionIndexState:
    """Build a compact index-graph state for governance unit tests.

    Args:
        attestation: Attestation policy version, or ``None``.
        category: Declared category label.

    Returns:
        Typed index state with unused fields filled by fixtures.
    """

    return {
        "job_id": str(uuid4()),
        "lease_token": "unused",
        "document_id": str(uuid4()),
        "version_id": str(uuid4()),
        "operation_key": "index:fixture",
        "storage_bucket": "documents-originals",
        "storage_path": "file.txt",
        "content_hash": "a" * 64,
        "byte_size": 12,
        "media_type": "text/plain",
        "filename": "file.txt",
        "document_title": "Fixture",
        "declared_category": category,
        "attestation_policy_version": attestation,
        "review_approved": True,
        "content_class": "real_company",
        "graph_eligible": False,
        "crawl_run_id": None,
        "status": "parsing",
        "chunk_set_hash": None,
        "bm25_job_id": None,
        "detail": "",
    }


def test_content_class_does_not_default_to_synthetic() -> None:
    """Missing or unknown payload class is real company, never synthetic."""

    assert content_class_from_payload(None) is ContentClass.REAL_COMPANY
    assert content_class_from_payload("real_company") is ContentClass.REAL_COMPANY
    assert content_class_from_payload("website") is ContentClass.REAL_COMPANY
    assert content_class_from_payload("synthetic") is ContentClass.SYNTHETIC


def test_declared_category_maps_website_to_allowed() -> None:
    """Website crawl category is an allowed disposition for governance."""

    assert declared_category_disposition("website") is CategoryDisposition.ALLOWED
    assert declared_category_disposition(None) is CategoryDisposition.UNKNOWN
    assert declared_category_disposition("secret") is CategoryDisposition.PROHIBITED


def test_provider_matrix_verified_is_exact_true() -> None:
    """Unverified or missing matrix flags stay fail-closed."""

    assert provider_matrix_verified({}) is False
    assert provider_matrix_verified({"subprocessor_matrix_verified": False}) is False
    assert provider_matrix_verified({"subprocessor_matrix_verified": "true"}) is False
    assert provider_matrix_verified({"subprocessor_matrix_verified": True}) is True


def test_load_external_processing_uses_db_backed_flags() -> None:
    """Index governance does not hardcode scan/policy/provider success."""

    state = _index_state(
        attestation=EXTERNAL_PROCESSING_POLICY_VERSION,
        category="website",
    )
    denied = load_external_processing_input(
        state=state,
        scan_evidence_current=False,
        configurable={},
        content_class=ContentClass.REAL_COMPANY,
        review_approved=False,
    )
    assert denied.scan_evidence_current is False
    assert denied.policy_version_matches is True
    assert denied.provider_settings_verified is False
    assert denied.content_class is ContentClass.REAL_COMPANY

    allowed = load_external_processing_input(
        state=state,
        scan_evidence_current=True,
        configurable={"subprocessor_matrix_verified": True},
        content_class=ContentClass.REAL_COMPANY,
        review_approved=True,
    )
    assert allowed.scan_evidence_current is True
    assert allowed.provider_settings_verified is True


def test_allow_index_without_scan_requires_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scan-skip fixtures work only when APP_ENV=test and the flag is true."""

    monkeypatch.setenv("APP_ENV", "local")
    assert allow_index_without_scan({"allow_index_without_scan": True}) is False
    monkeypatch.setenv("APP_ENV", "test")
    assert allow_index_without_scan({"allow_index_without_scan": True}) is True
    assert allow_index_without_scan({}) is False


def test_index_scan_gate_fixture_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test fixtures may skip the scan query when both gates are set."""

    monkeypatch.setenv("APP_ENV", "test")
    allowed = index_scan_gate_allows(
        connection=object(),  # type: ignore[arg-type]
        version_id=uuid4(),
        content_hash=None,
        crawl_run_id=None,
        configurable={"allow_index_without_scan": True},
    )
    assert allowed is True


class _StatusCursor:
    """Cursor that returns one version status."""

    def __init__(self, status: str) -> None:
        """Store the status returned by ``fetchone``.

        Args:
            status: Public document-version status.
        """

        self._status = status

    def execute(self, query: str, params: object = None) -> None:
        """Ignore SQL. Unit tests do not open Postgres.

        Args:
            query: Unused SQL.
            params: Unused bind parameters.
        """

        del query, params

    def fetchone(self) -> tuple[str]:
        """Return the scripted status.

        Returns:
            One-element status tuple.
        """

        return (self._status,)

    def __enter__(self) -> _StatusCursor:
        """Return the cursor.

        Returns:
            This cursor.
        """

        return self

    def __exit__(self, *_exc: object) -> bool:
        """Do not suppress errors.

        Returns:
            False.
        """

        return False


class _StatusConnection:
    """Connection that reports one version status and records commits."""

    def __init__(self, status: str) -> None:
        """Store the scripted status.

        Args:
            status: Public document-version status.
        """

        self.status = status
        self.commits = 0
        self.rollbacks = 0

    def execute(self, query: str, params: object = None) -> _StatusConnection:
        """Ignore SET ROLE and unused statements.

        Args:
            query: Unused SQL.
            params: Unused bind parameters.

        Returns:
            This connection.
        """

        del query, params
        return self

    def cursor(self) -> _StatusCursor:
        """Return a cursor that yields the scripted status.

        Returns:
            Status cursor.
        """

        return _StatusCursor(self.status)

    def commit(self) -> None:
        """Record a commit."""

        self.commits += 1

    def rollback(self) -> None:
        """Record a rollback."""

        self.rollbacks += 1

    def __enter__(self) -> _StatusConnection:
        """Return the connection.

        Returns:
            This connection.
        """

        return self

    def __exit__(self, *_exc: object) -> bool:
        """Do not suppress errors.

        Returns:
            False.
        """

        return False


def test_mark_parsing_refreshes_already_indexed_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """graph_ineligible skips parse/scan and returns indexed after term sync."""

    connection = _StatusConnection("graph_ineligible")
    version_id = uuid4()
    captured: dict[str, object] = {}

    def fake_refresh(
        connected: object,
        *,
        version_id: object,
    ) -> int:
        """Record the refresh call.

        Args:
            connected: Fake connection.
            version_id: Version passed by the node.

        Returns:
            Inserted-term count.
        """

        captured["connection"] = connected
        captured["version_id"] = version_id
        return 12

    monkeypatch.setattr(
        "smart_rag_agents.ingestion.index_graph.psycopg.connect",
        lambda _url: connection,
    )
    monkeypatch.setattr(
        "smart_rag_agents.ingestion.index_graph.refresh_indexed_title_search_terms",
        fake_refresh,
    )
    state = _index_state(
        attestation=EXTERNAL_PROCESSING_POLICY_VERSION,
        category="internal",
    )
    state["status"] = "index_pending"
    state["version_id"] = str(version_id)
    result = mark_parsing_for_index(
        state,
        {"configurable": {"postgres_url": "postgresql://unused"}},
    )
    assert result["status"] == "indexed"
    assert result["detail"] == "search_terms_refreshed:12"
    assert captured["version_id"] == version_id
    assert connection.commits == 1
    assert connection.rollbacks == 0
