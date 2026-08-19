"""Unit tests for governed mock embeddings."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    EmbeddingResponse,
    MockEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    create_embedding_gateway,
)
from smart_rag_core.gateways.model import ModelGatewayUnavailableError
from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkKind,
    ChunkProvenance,
)
from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.ingestion.embeddings.policy import EMBEDDING_DIMENSIONS
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddingBatchInput,
    EmbeddingGateError,
    EmbeddingService,
    _chunk_set_hash,
)
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
)
from smart_rag_core.settings import AgentSettings

from tests.unit.typed_attrs import module_attr


def _chunk(text: str) -> CanonicalChunk:
    """Build one passage chunk with stable provenance versions.

    Args:
        text: Raw chunk text used as embedding input.

    Returns:
        Canonical chunk with a fresh id and fixture hashes.
    """

    return CanonicalChunk(
        chunk_id=uuid4(),
        chunk_index=0,
        kind=ChunkKind.PASSAGE,
        raw_text=text,
        token_count=10,
        provenance=ChunkProvenance(
            parser_version="parser_v1",
            cleaning_version="cleaning_v1",
            chunking_version="chunking_v1",
            tokenizer_version="cl100k_base_v1",
            dedup_policy_version="dedup_v1",
            normalized_content_hash="abc123",
        ),
    )


def test_mock_embedding_is_deterministic_and_finite() -> None:
    """Mock vectors are stable, sized, and finite."""

    first = mock_embedding_vector("annual leave policy")
    second = mock_embedding_vector("annual leave policy")
    assert len(first) == EMBEDDING_DIMENSIONS
    assert first == second
    assert all(abs(value) <= 1.0 for value in first)


def test_embedding_gateway_replay_is_stable() -> None:
    """Gateway replay returns identical vectors and request IDs for same inputs."""

    async def _run() -> None:
        """Replay one embedding request and assert identical responses."""

        gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
        request = EmbeddingRequest(
            operation_key="op-1",
            inputs=("annual leave policy", "warehouse safety"),
            model="text-embedding-3-large",
            dimensions=EMBEDDING_DIMENSIONS,
        )
        first = await gateway.embed(request)
        second = await gateway.embed(request)
        assert first.vectors == second.vectors
        assert first.provider_request_id == second.provider_request_id

    asyncio.run(_run())


def test_embedding_service_denies_real_company_without_provider_verification() -> None:
    """Governance gate blocks real company content when provider settings unverified."""

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))

    class _Connection:
        """Connection double that must not be used when governance denies."""

        def cursor(self) -> object:
            """Fail if the service opens a cursor after a governance deny.

            Returns:
                Never returns; always raises.

            Raises:
                AssertionError: Database was reached unexpectedly.
            """

            raise AssertionError("database should not be reached")

    service = EmbeddingService(_Connection(), gateway=gateway)  # type: ignore[arg-type]
    batch = EmbeddingBatchInput(
        version_id=uuid4(),
        document_title="Policy",
        chunks=(_chunk("annual leave policy"),),
        chunking_config_hash="cfg",
        operation_key="embed:1",
        governance=ExternalProcessingDecisionInput(
            attestation_present=True,
            category=CategoryDisposition.ALLOWED,
            review_approved=True,
            scan_evidence_current=True,
            provider_settings_verified=False,
            policy_version_matches=True,
            content_class=ContentClass.REAL_COMPANY,
        ),
    )
    with pytest.raises(Exception, match="unverified_provider_settings"):
        service.embed_version(batch)


def test_embedding_gateway_sync_wrapper() -> None:
    """Synchronous ingestion nodes can await gateway batches via asyncio.run."""

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
    response = asyncio.run(
        gateway.embed(
            EmbeddingRequest(
                operation_key="sync",
                inputs=("probe",),
                model="text-embedding-3-large",
                dimensions=EMBEDDING_DIMENSIONS,
            )
        )
    )
    assert len(response.vectors) == 1
    assert response.estimated_cost_usd == Decimal("0")


def test_embedding_timeout_after_provider_success_records_failed_ledger() -> None:
    """Timeout after the mock provider returns still records a failed ledger row."""

    class _TimeoutAdapter:
        """Adapter that succeeds at the provider then times out in the client."""

        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            """Raise TimeoutError after the caller would have seen provider work.

            Args:
                request: Unused embedding request.

            Returns:
                Never returns; always raises.

            Raises:
                TimeoutError: Simulated client timeout.
            """

            raise TimeoutError("client timed out after provider success")

    class _Cursor:
        """In-memory cursor that records SQL for ledger assertions."""

        def __init__(self) -> None:
            """Start with an empty statement log."""

            self.statements: list[str] = []

        def __enter__(self) -> _Cursor:
            """Enter the context manager and return this cursor.

            Returns:
                The same cursor instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, sql: str, _params: object = None) -> None:
            """Append one SQL string to the statement log.

            Args:
                sql: Statement text.
                _params: Unused bind parameters.
            """

            self.statements.append(sql)

        def fetchone(self) -> tuple[object, ...]:
            """Return a stub row matching the last executed statement.

            Returns:
                Ledger id, attempt count, or a null placeholder tuple.
            """

            if "record_embedding_ledger" in self.statements[-1]:
                return (uuid4(),)
            if "attempt_count" in self.statements[-1]:
                return (2,)
            return (None,)

    class _Connection:
        """Connection double that reuses one in-memory cursor."""

        def __init__(self) -> None:
            """Create the shared cursor used by ``cursor`` and ``execute``."""

            self.cursor_obj = _Cursor()

        def cursor(self) -> _Cursor:
            """Return the shared in-memory cursor.

            Returns:
                The same ``_Cursor`` instance for the connection.
            """

            return self.cursor_obj

        def execute(self, sql: str, params: object = None) -> _Cursor:
            """Execute through the shared cursor and return it.

            Args:
                sql: Statement text.
                params: Bind parameters forwarded to the cursor.

            Returns:
                The shared cursor after ``execute``.
            """

            self.cursor_obj.execute(sql, params)
            return self.cursor_obj

    gateway = EmbeddingGateway(_TimeoutAdapter())
    connection = _Connection()
    service = EmbeddingService(connection, gateway=gateway)  # type: ignore[arg-type]
    service._admission.assert_can_enqueue_ingestion = lambda **_kwargs: None  # type: ignore[method-assign]
    batch = EmbeddingBatchInput(
        version_id=uuid4(),
        document_title="Policy",
        chunks=(_chunk("annual leave policy"),),
        chunking_config_hash="cfg",
        operation_key="embed:timeout",
        governance=ExternalProcessingDecisionInput(
            attestation_present=True,
            category=CategoryDisposition.ALLOWED,
            review_approved=True,
            scan_evidence_current=True,
            provider_settings_verified=True,
            policy_version_matches=True,
            content_class=ContentClass.SYNTHETIC,
        ),
    )
    with pytest.raises(Exception, match="embedding_timeout_after_provider"):
        service.embed_version(batch)
    joined = " ".join(connection.cursor_obj.statements)
    assert "record_embedding_ledger" in joined


def test_mock_embedding_response_mode_is_mock() -> None:
    """The mock adapter still returns mode=mock through the gateway."""

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
    response = asyncio.run(
        gateway.embed(
            EmbeddingRequest(
                operation_key="mode",
                inputs=("annual leave policy",),
                model="text-embedding-3-large",
                dimensions=EMBEDDING_DIMENSIONS,
            )
        )
    )
    assert response.mode == "mock"
    assert len(response.vectors[0]) == EMBEDDING_DIMENSIONS


def test_create_embedding_gateway_mock_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MOCK_MODEL_MODE=true selects the deterministic adapter."""

    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    gateway = create_embedding_gateway(AgentSettings())
    adapter: object = module_attr(gateway, "_adapter")
    assert isinstance(adapter, MockEmbeddingAdapter)


def test_create_embedding_gateway_openai_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MOCK_MODEL_MODE=false with a key selects the OpenAI adapter."""

    monkeypatch.setenv("MOCK_MODEL_MODE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-adapter")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    gateway = create_embedding_gateway(AgentSettings())
    adapter: object = module_attr(gateway, "_adapter")
    assert isinstance(adapter, OpenAIEmbeddingAdapter)


def test_create_embedding_gateway_fail_closed_without_key() -> None:
    """Real-model embeddings fail closed when OPENAI_API_KEY is missing."""

    settings = MagicMock()
    settings.mock_model_mode = False
    settings.openai_api_key = None
    settings.apply_langsmith_sdk_flags.return_value = {}
    with pytest.raises(ModelGatewayUnavailableError, match="OPENAI_API_KEY"):
        create_embedding_gateway(settings)


def test_openai_adapter_fail_closed_without_key() -> None:
    """The OpenAI adapter constructor rejects a blank key."""

    with pytest.raises(ModelGatewayUnavailableError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingAdapter(api_key="   ")


def _governance() -> ExternalProcessingDecisionInput:
    """Return synthetic embedding governance that passes the deny-by-default gates.

    Returns:
        Decision input used by ledger skip / loop unit tests.
    """

    return ExternalProcessingDecisionInput(
        attestation_present=True,
        category=CategoryDisposition.ALLOWED,
        review_approved=True,
        scan_evidence_current=True,
        provider_settings_verified=True,
        policy_version_matches=True,
        content_class=ContentClass.SYNTHETIC,
    )


def test_embedding_service_skips_provider_when_ledger_completed() -> None:
    """A completed ledger row with vectors must not call the embedding provider."""

    chunk = _chunk("annual leave policy")
    chunk_set_hash = _chunk_set_hash((chunk,))
    vector = list(mock_embedding_vector("annual leave policy"))
    ledger_id = uuid4()
    called = {"embed": 0}

    class _Adapter:
        """Provider that must not run when the ledger already completed."""

        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            """Count unexpected provider calls.

            Args:
                request: Unused embedding request.

            Returns:
                Never returns; the test asserts this is not called.

            Raises:
                AssertionError: Provider was reached.
            """

            called["embed"] += 1
            raise AssertionError(f"provider must not run: {request.operation_key}")

    class _Cursor:
        """Cursor that returns a completed ledger payload."""

        def __init__(self) -> None:
            """Start with an empty statement log."""

            self.statements: list[str] = []

        def __enter__(self) -> _Cursor:
            """Return this cursor.

            Returns:
                The same cursor instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, sql: str, _params: object = None) -> None:
            """Append one SQL string.

            Args:
                sql: Statement text.
                _params: Unused bind parameters.
            """

            self.statements.append(sql)

        def fetchone(self) -> tuple[object, ...]:
            """Return completed ledger rows for skip-path queries.

            Returns:
                Ledger id/status/result_ref, or attempt count.
            """

            latest = self.statements[-1]
            if "FROM app.embedding_operation_ledger" in latest and "status" in latest:
                return (
                    ledger_id,
                    "completed",
                    {"chunk_set_hash": chunk_set_hash, "vectors": [vector]},
                )
            if "attempt_count" in latest:
                return (3,)
            return (None,)

    class _Connection:
        """Connection double that reuses one in-memory cursor."""

        def __init__(self) -> None:
            """Create the shared cursor."""

            self.cursor_obj = _Cursor()

        def cursor(self) -> _Cursor:
            """Return the shared cursor.

            Returns:
                The in-memory cursor.
            """

            return self.cursor_obj

    gateway = EmbeddingGateway(_Adapter())
    connection = _Connection()
    service = EmbeddingService(connection, gateway=gateway)  # type: ignore[arg-type]
    result = service.embed_version(
        EmbeddingBatchInput(
            version_id=uuid4(),
            document_title="Policy",
            chunks=(chunk,),
            chunking_config_hash="cfg",
            operation_key="embed:replay",
            governance=_governance(),
        )
    )
    assert called["embed"] == 0
    assert result.ledger_id == ledger_id
    assert result.provider_request_id == "ledger_replay"
    assert result.embedded[0].embedding == vector


def test_embedding_service_fails_closed_when_completed_vectors_missing() -> None:
    """Completed ledger rows without vectors must not call the provider."""

    chunk = _chunk("annual leave policy")
    chunk_set_hash = _chunk_set_hash((chunk,))

    class _Cursor:
        """Cursor that returns a completed row with no vectors."""

        def __init__(self) -> None:
            """Start with an empty statement log."""

            self.statements: list[str] = []

        def __enter__(self) -> _Cursor:
            """Return this cursor.

            Returns:
                The same cursor instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, sql: str, _params: object = None) -> None:
            """Append one SQL string.

            Args:
                sql: Statement text.
                _params: Unused bind parameters.
            """

            self.statements.append(sql)

        def fetchone(self) -> tuple[object, ...]:
            """Return a completed ledger row missing vectors.

            Returns:
                Ledger id, status, and result_ref without vectors.
            """

            return (
                uuid4(),
                "completed",
                {"chunk_set_hash": chunk_set_hash},
            )

    class _Connection:
        """Connection double that reuses one in-memory cursor."""

        def __init__(self) -> None:
            """Create the shared cursor."""

            self.cursor_obj = _Cursor()

        def cursor(self) -> _Cursor:
            """Return the shared cursor.

            Returns:
                The in-memory cursor.
            """

            return self.cursor_obj

    class _Adapter:
        """Provider that must not run on a corrupt completed ledger."""

        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            """Fail if the provider is reached.

            Args:
                request: Unused embedding request.

            Returns:
                Never returns.

            Raises:
                AssertionError: Provider was reached.
            """

            raise AssertionError(f"provider must not run: {request.operation_key}")

    service = EmbeddingService(_Connection(), gateway=EmbeddingGateway(_Adapter()))  # type: ignore[arg-type]
    with pytest.raises(EmbeddingGateError, match="embedding_ledger_vectors_missing"):
        service.embed_version(
            EmbeddingBatchInput(
                version_id=uuid4(),
                document_title="Policy",
                chunks=(chunk,),
                chunking_config_hash="cfg",
                operation_key="embed:missing-vectors",
                governance=_governance(),
            )
        )


def test_embedding_service_nested_running_loop_does_not_crash() -> None:
    """Embed from a running event loop uses a dedicated thread instead of asyncio.run."""

    class _Cursor:
        """Cursor that returns pending ledger rows then insert ids."""

        def __init__(self) -> None:
            """Start with an empty statement log."""

            self.statements: list[str] = []

        def __enter__(self) -> _Cursor:
            """Return this cursor.

            Returns:
                The same cursor instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, sql: str, _params: object = None) -> None:
            """Append one SQL string.

            Args:
                sql: Statement text.
                _params: Unused bind parameters.
            """

            self.statements.append(sql)

        def fetchone(self) -> tuple[object, ...]:
            """Return pending ledger, insert id, or attempt count.

            Returns:
                Stub row matching the last statement.
            """

            latest = self.statements[-1]
            if "record_embedding_ledger" in latest:
                return (uuid4(),)
            if "attempt_count" in latest:
                return (1,)
            if "FROM app.embedding_operation_ledger" in latest:
                return (uuid4(), "pending", {})
            return (None,)

    class _Connection:
        """Connection double that reuses one in-memory cursor."""

        def __init__(self) -> None:
            """Create the shared cursor."""

            self.cursor_obj = _Cursor()

        def cursor(self) -> _Cursor:
            """Return the shared cursor.

            Returns:
                The in-memory cursor.
            """

            return self.cursor_obj

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
    connection = _Connection()
    service = EmbeddingService(connection, gateway=gateway)  # type: ignore[arg-type]
    service._admission.assert_can_enqueue_ingestion = lambda **_kwargs: None  # type: ignore[method-assign]
    batch = EmbeddingBatchInput(
        version_id=uuid4(),
        document_title="Policy",
        chunks=(_chunk("annual leave policy"),),
        chunking_config_hash="cfg",
        operation_key="embed:nested-loop",
        governance=_governance(),
    )

    async def _inner() -> None:
        """Invoke the sync embed wrapper while this loop is running."""

        result = service.embed_version(batch)
        assert len(result.embedded) == 1

    asyncio.run(_inner())


def test_openai_adapter_maps_data_by_index() -> None:
    """OpenAI ``data`` rows are ordered by ``index``, not list order."""

    first = [0.1, 0.2, 0.3, 0.4]
    second = [0.5, 0.6, 0.7, 0.8]

    class _Item:
        """One OpenAI embedding row with an explicit index."""

        def __init__(self, index: int, embedding: list[float]) -> None:
            """Store index and vector for adapter reordering tests.

            Args:
                index: OpenAI ``data[].index``.
                embedding: Vector values for that index.
            """

            self.index = index
            self.embedding = embedding

    class _Usage:
        """Stub usage counters for a two-input embeddings call."""

        prompt_tokens = 8
        total_tokens = 8

    class _Response:
        """Embeddings payload with rows reversed relative to input order."""

        def __init__(self) -> None:
            """Place index 1 before index 0 to prove reordering."""

            self.data = (_Item(1, second), _Item(0, first))
            self.usage = _Usage()
            self.id = "embd-index-test"

    def _create(_client: object, **kwargs: object) -> _Response:
        """Return the reversed-index stub after asserting create kwargs.

        Args:
            _client: Unused traced client.
            **kwargs: embeddings.create keyword arguments.

        Returns:
            Stub OpenAI embeddings response.
        """

        assert kwargs["model"] == "text-embedding-3-large"
        assert kwargs["encoding_format"] == "float"
        assert kwargs["dimensions"] == 4
        assert kwargs["input"] == ["First text", "Second text"]
        return _Response()

    adapter = OpenAIEmbeddingAdapter(api_key="sk-test")
    with (
        patch(
            "smart_rag_core.gateways.embedding.traced_openai_client",
            return_value=object(),
        ),
        patch(
            "smart_rag_core.gateways.embedding.traced_embeddings_create",
            _create,
        ),
    ):
        response = asyncio.run(
            adapter.embed(
                EmbeddingRequest(
                    operation_key="index",
                    inputs=("First text", "Second text"),
                    model="text-embedding-3-large",
                    dimensions=4,
                )
            )
        )
    assert response.mode == "openai"
    assert response.vectors[0] == tuple(first)
    assert response.vectors[1] == tuple(second)
    assert response.provider_request_id == "embd-index-test"


def test_openai_adapter_rejects_wrong_dimension() -> None:
    """A vector whose length does not match ``dimensions`` fails closed."""

    class _Item:
        """Embedding row whose vector length does not match ``dimensions``."""

        def __init__(self) -> None:
            """Store a two-float vector for a four-dimension request."""

            self.index = 0
            self.embedding = [0.1, 0.2]

    class _Usage:
        """Stub usage counters for a single mismatched embedding."""

        prompt_tokens = 1
        total_tokens = 1

    class _Response:
        """Embeddings payload with one undersized vector."""

        def __init__(self) -> None:
            """Attach the mismatched item and a request id."""

            self.data = (_Item(),)
            self.usage = _Usage()
            self.id = "embd-dim"

    adapter = OpenAIEmbeddingAdapter(api_key="sk-test")

    def _create(_client: object, **_kwargs: object) -> _Response:
        """Return a dimension-mismatched embedding payload.

        Args:
            _client: Unused traced client.
            **_kwargs: Unused embeddings.create kwargs.

        Returns:
            Stub OpenAI embeddings response.
        """

        return _Response()

    with (
        patch(
            "smart_rag_core.gateways.embedding.traced_openai_client",
            return_value=object(),
        ),
        patch(
            "smart_rag_core.gateways.embedding.traced_embeddings_create",
            _create,
        ),
    ):
        with pytest.raises(ValueError, match="embedding_dimension_mismatch"):
            asyncio.run(
                adapter.embed(
                    EmbeddingRequest(
                        operation_key="dim",
                        inputs=("probe",),
                        model="text-embedding-3-large",
                        dimensions=4,
                    )
                )
            )


def test_embed_inputs_in_batches_emits_count_only_progress() -> None:
    """Gateway calls split on the default batch size without copying canary text."""

    from smart_rag_core.ingestion.embeddings.service import _embed_inputs_in_batches
    from smart_rag_core.ingestion.limits import DEFAULT_EMBEDDING_BATCH_SIZE

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
    canary = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"
    texts = tuple(f"token-{index}" for index in range(DEFAULT_EMBEDDING_BATCH_SIZE + 1))
    seen: list[tuple[str, dict[str, int]]] = []

    def _progress(stage: str, counts: dict[str, int]) -> None:
        """Capture batch progress counters.

        Args:
            stage: Progress stage token.
            counts: Integer counters.
        """

        seen.append((stage, dict(counts)))

    response = _embed_inputs_in_batches(
        gateway,
        operation_key="op-batch",
        contextual_inputs=texts,
        progress=_progress,
    )
    assert len(response.vectors) == DEFAULT_EMBEDDING_BATCH_SIZE + 1
    assert len(seen) == 2
    assert seen[0] == (
        "embed_batch",
        {
            "batch_index": 1,
            "batch_count": 2,
            "chunks": DEFAULT_EMBEDDING_BATCH_SIZE,
        },
    )
    assert seen[1][1]["batch_index"] == 2
    assert seen[1][1]["chunks"] == 1
    assert canary not in str(seen)
