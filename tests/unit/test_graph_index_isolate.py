"""Unit tests for isolated candidate graph index without live quarantine."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from smart_rag_core.gateways.embedding import EmbeddingProviderError
from smart_rag_core.jobs.exceptions import GraphWriterLostError
from smart_rag_core.jobs.graph_index_service import GraphIndexService
from smart_rag_core.jobs.graph_writer import GraphWriterGuard
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    GRAPH_SOURCE_INSERT_BATCH_SIZE,
    MAPPING_COVERAGE_OVERALL_MIN,
    MAPPING_SUPPORT_MIN,
)
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_EMBEDDING_PROVIDER_TIMEOUT_SECONDS,
    LIGHTRAG_EMBEDDING_VENDOR_TIMEOUT_SECONDS,
)
from smart_rag_core.retrieval.lightrag_adapter import LightRagRuntimeAdapter
from smart_rag_core.retrieval.lightrag_callbacks import CountedLightRagCallbacks
from smart_rag_core.retrieval.lightrag_indexer import LightRagGraphIndexer
from smart_rag_core.schema.enums import JobErrorCategory

from tests.unit.typed_attrs import set_attr, typed_attr


def _isolate_service() -> tuple[GraphIndexService, MagicMock]:
    """Build an index service whose live writer can be asserted.

    Returns:
        Service plus the writer mock.
    """

    connection = MagicMock()
    writer = MagicMock()
    admission = MagicMock()
    admission.create_graph_budget_reservation.return_value = uuid4()
    repository = MagicMock()
    repository.admission = admission
    indexer = MagicMock()
    indexer.adapter = MagicMock()
    service = GraphIndexService(
        connection,
        indexer=cast(LightRagGraphIndexer, indexer),
        writer=cast(GraphWriterGuard, writer),
        repository=cast(LightragIndexJobRepository, repository),
        mapper=MagicMock(),
    )
    return service, writer


def _index_job(*, isolate: bool) -> dict[str, object]:
    """Return a claimed index job mapping.

    Args:
        isolate: When true, the job rebuilds on ``{live}__rebuild``.

    Returns:
        Claimed ``lightrag_index_jobs`` row.
    """

    payload: dict[str, object] = {}
    if isolate:
        payload["isolate_candidate"] = True
    return {
        "id": str(uuid4()),
        "operation": "index",
        "payload_ref": payload,
        "document_id": str(uuid4()),
        "version_id": str(uuid4()),
    }


def test_provider_timeout_stays_below_lightrag_watchdog() -> None:
    """Raising the vendor watchdog is forbidden; the SDK bound is shorter."""

    assert LIGHTRAG_EMBEDDING_VENDOR_TIMEOUT_SECONDS == 30
    assert LIGHTRAG_EMBEDDING_PROVIDER_TIMEOUT_SECONDS == 20.0
    assert (
        LIGHTRAG_EMBEDDING_PROVIDER_TIMEOUT_SECONDS
        < LIGHTRAG_EMBEDDING_VENDOR_TIMEOUT_SECONDS
    )
    assert GRAPH_SOURCE_INSERT_BATCH_SIZE == 8
    assert MAPPING_COVERAGE_OVERALL_MIN == 0.90
    assert MAPPING_SUPPORT_MIN == 0.80
    from smart_rag_core.gateways.embedding import (
        OPENAI_EMBEDDING_TIMEOUT_SECONDS as gateway_embed_timeout,
    )
    from smart_rag_core.retrieval.graph import (
        OPENAI_EMBEDDING_TIMEOUT_SECONDS as graph_embed_timeout,
    )

    assert gateway_embed_timeout == graph_embed_timeout == 120.0


def test_isolate_embedding_timeout_does_not_quarantine_live() -> None:
    """Candidate timeout fails the job and leaves the live workspace."""

    service, writer = _isolate_service()
    service._index = AsyncMock(  # type: ignore[method-assign]
        side_effect=EmbeddingProviderError("embedding_timeout")
    )
    outcome = asyncio.run(
        service.process_claimed_job(
            _index_job(isolate=True), job_lease_token=str(uuid4())
        )
    )
    assert outcome.kind == "failed"
    assert outcome.error_category is JobErrorCategory.TRANSIENT
    assert outcome.last_error == "embedding_timeout"
    writer.quarantine.assert_not_called()


def test_isolate_rate_limit_does_not_quarantine_live() -> None:
    """HTTP 429 on the candidate is transient and does not quarantine live."""

    service, writer = _isolate_service()
    service._index = AsyncMock(  # type: ignore[method-assign]
        side_effect=EmbeddingProviderError("embedding_rate_limited")
    )
    outcome = asyncio.run(
        service.process_claimed_job(
            _index_job(isolate=True), job_lease_token=str(uuid4())
        )
    )
    assert outcome.kind == "failed"
    writer.quarantine.assert_not_called()


def test_isolate_lease_loss_does_not_quarantine_live() -> None:
    """Worker crash during isolate must not flip the live workspace."""

    service, writer = _isolate_service()
    writer.verify_lock_and_lease.side_effect = GraphWriterLostError("job_lease_lost")
    outcome = asyncio.run(
        service.process_claimed_job(
            _index_job(isolate=True), job_lease_token=str(uuid4())
        )
    )
    assert outcome.kind == "failed"
    assert outcome.last_error == "job_lease_lost"
    writer.quarantine.assert_not_called()


def test_live_index_timeout_still_quarantines() -> None:
    """Non-isolated index timeouts keep the existing quarantine path."""

    service, writer = _isolate_service()
    service._index = AsyncMock(  # type: ignore[method-assign]
        side_effect=EmbeddingProviderError("embedding_timeout")
    )
    outcome = asyncio.run(
        service.process_claimed_job(
            _index_job(isolate=False), job_lease_token=str(uuid4())
        )
    )
    assert outcome.kind == "quarantined"
    writer.quarantine.assert_called_once()


def test_bind_workspace_retargets_vendor_storage() -> None:
    """Candidate rebuilds must retarget the attached engine, not reopen it."""

    adapter = LightRagRuntimeAdapter.__new__(LightRagRuntimeAdapter)
    adapter.workspace = "company_default"
    set_attr(
        adapter,
        "rag",
        SimpleNamespace(
            workspace="company_default",
            full_docs=SimpleNamespace(workspace="company_default"),
            text_chunks=SimpleNamespace(workspace="company_default"),
        ),
    )
    adapter.bind_workspace("company_default__rebuild")
    assert adapter.workspace == "company_default__rebuild"
    rag = typed_attr(adapter, "rag")
    assert rag.workspace == "company_default__rebuild"
    assert rag.full_docs.workspace == "company_default__rebuild"


def test_ensure_pipeline_status_uses_bound_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate rebuilds must init in-memory pipeline_status, not DDL."""

    adapter = LightRagRuntimeAdapter.__new__(LightRagRuntimeAdapter)
    adapter.workspace = "company_default__rebuild"
    seen: dict[str, str | None] = {}

    async def _fake_init(*, workspace: str | None = None) -> None:
        """Capture the vendor pipeline-status workspace.

        Args:
            workspace: Bound LightRAG workspace.
        """

        seen["workspace"] = workspace

    monkeypatch.setattr(
        "lightrag.kg.shared_storage.initialize_pipeline_status",
        _fake_init,
    )
    asyncio.run(adapter.ensure_pipeline_status())
    assert seen["workspace"] == "company_default__rebuild"


def test_isolate_index_initializes_pipeline_before_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Isolated index binds the rebuild workspace then inits pipeline_status."""

    from smart_rag_core.retrieval.graph import GraphIndexEnqueueResult

    service, writer = _isolate_service()
    writer.workspace_key = "company_default"
    adapter = MagicMock()
    adapter.ensure_pipeline_status = AsyncMock()
    adapter.callbacks.counts = SimpleNamespace(embed=0, entity_extract=0, other=0)
    typed_attr(service, "_indexer").adapter = adapter
    service._revalidate_index_eligibility = MagicMock()  # type: ignore[method-assign]
    service._assert_version_still_pending = MagicMock()  # type: ignore[method-assign]
    set_attr(typed_attr(service, "_mapper"), "set_map_workspace_key", MagicMock())
    set_attr(
        typed_attr(service, "_mapper"),
        "map_after_vendor_success",
        AsyncMock(
            return_value=SimpleNamespace(
                maps_verified=False,
                reason="coverage_below_threshold",
                pending_switch=False,
                workspace_state="building",
            )
        ),
    )
    source = SimpleNamespace(
        enveloped_text=lambda: "passage",
        source_token="g.txt",  # noqa: S106
    )
    manifest = SimpleNamespace(sources=(source,), source_ids=("v:c",))

    def _load_manifest(*_args: object, **_kwargs: object) -> object:
        """Return the fixture passage manifest.

        Args:
            *_args: Unused loader args.
            **_kwargs: Unused loader kwargs.

        Returns:
            Passage manifest fixture.
        """

        return manifest

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_index_service.load_version_passage_manifest",
        _load_manifest,
    )
    insert = AsyncMock(
        return_value=GraphIndexEnqueueResult(
            document_id="v:c",
            track_id="track",
            status="processed",
        )
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_index_service.insert_passage_batches",
        insert,
    )
    job = _index_job(isolate=True)
    asyncio.run(
        typed_attr(service, "_index")(
            job=job,
            payload=cast(dict[str, object], job["payload_ref"]),
            job_id=uuid4(),
            job_lease_token=str(uuid4()),
            reservation_id=uuid4(),
        )
    )
    adapter.bind_workspace.assert_any_call("company_default__rebuild")
    assert adapter.ensure_pipeline_status.await_count >= 1
    assert insert.await_count == 1


def test_isolate_pipeline_uninitialized_does_not_quarantine_live() -> None:
    """Missing candidate pipeline_status fails the job, not live."""

    from smart_rag_core.retrieval.lightrag_indexer import GraphIndexerError

    service, writer = _isolate_service()
    set_attr(
        service,
        "_index",
        AsyncMock(side_effect=GraphIndexerError("pipeline_status_uninitialized")),
    )
    outcome = asyncio.run(
        service.process_claimed_job(
            _index_job(isolate=True), job_lease_token=str(uuid4())
        )
    )
    assert outcome.kind == "failed"
    assert outcome.last_error == "pipeline_status_uninitialized"
    writer.quarantine.assert_not_called()


def test_embedding_callback_cooperative_lease_hook() -> None:
    """Lease cancellation runs before the embedding gateway is called."""

    gateway = MagicMock()
    gateway.embed = AsyncMock()
    callbacks = CountedLightRagCallbacks(
        embedding_gateway=gateway,
        model_gateway=MagicMock(),
    )

    def _cancel() -> None:
        """Simulate a cancelled writer lease.

        Raises:
            GraphWriterLostError: Cooperative cancellation.
        """

        raise GraphWriterLostError("job_lease_lost")

    callbacks.pre_provider_hook = _cancel
    with pytest.raises(GraphWriterLostError, match="job_lease_lost"):
        asyncio.run(callbacks.embedding_texts(["passage"]))
    gateway.embed.assert_not_called()
