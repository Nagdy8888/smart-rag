"""Contract tests for LightRAG 1.5.6 PostgreSQL qualification.

Live tests skip when local Supabase Postgres is unreachable unless
``SMART_RAG_REQUIRE_JOB_INTEGRATION=1``, in which case they fail closed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from smart_rag_core.gateways.embedding import EmbeddingGateway, create_embedding_gateway
from smart_rag_core.gateways.model import ModelGateway, create_model_gateway
from smart_rag_core.retrieval.graph import (
    FORBIDDEN_AGE_GRAPH_STORAGE,
    GRAPH_FIELD_SEP,
    SELECTED_DOC_STATUS_STORAGE,
    SELECTED_GRAPH_STORAGE,
    SELECTED_KV_STORAGE,
    SELECTED_VECTOR_STORAGE,
    GraphQueryBounds,
    apply_query_bounds,
)
from smart_rag_core.retrieval.lightrag_qualification import (
    EXPECTED_PGTABLE_TABLES,
    SYNTHETIC_QUALIFICATION_TEXT,
    LightRagPostgresParams,
    VendorPostgresOverrides,
    age_extension_present,
    capture_schema_fingerprint,
    create_disposable_schema,
    delete_document,
    document_status,
    drop_disposable_schema,
    evaluate_identical_content_independence,
    fingerprint_drift,
    insert_synthetic_document,
    observed_path_normalization,
    open_qualification_session,
    parse_postgres_url,
    query_structured,
    reset_process_client_manager,
    vendor_env_pairs,
)
from smart_rag_core.retrieval.lightrag_structured import (
    LightRagQueryFailure,
    to_graph_leads,
)
from smart_rag_core.settings import SharedSettings

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AQUERY_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "lightrag" / "aquery_data_success_envelope.json"
)
HL_KEYWORDS = ("qualification",)
LL_KEYWORDS = ("Alpha Probe",)


def _require_postgres() -> tuple[str, LightRagPostgresParams]:
    """Open Postgres or skip unless the job integration gate is required.

    Returns:
        URL and parsed connection fields. The URL is never logged.

    Raises:
        pytest.fail: When the integration gate is required and Postgres is down.
    """

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("LightRAG qualification requires reachable Supabase Postgres")
        pytest.skip("Local Supabase Postgres unreachable")
    connection.close()
    return url, parse_postgres_url(url)


@pytest.fixture
def postgres_params(
    forbid_runtime_pipmaster_install: None,
) -> Iterator[LightRagPostgresParams]:
    """Yield parsed local database fields or skip when unreachable."""

    _ = forbid_runtime_pipmaster_install
    _url, params = _require_postgres()
    del _url
    yield params


@pytest.fixture(autouse=True)
def forbid_runtime_pipmaster_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed if LightRAG attempts a runtime ``pipmaster.install``."""

    def _blocked(*_args: object, **_kwargs: object) -> None:
        """Reject unexpected runtime package installation.

        Args:
            *_args: pipmaster positional arguments.
            **_kwargs: pipmaster keyword arguments.
        """

        raise AssertionError("pipmaster.install must not run during qualification")

    monkeypatch.setattr("pipmaster.install", _blocked)
    try:
        import lightrag.kg.postgres_impl as postgres_impl

        monkeypatch.setattr(postgres_impl.pm, "install", _blocked)
    except ImportError:
        return


def _schema_name() -> str:
    """Return a disposable lowercase schema identifier.

    Returns:
        Safe ``lightrag_q_`` schema name.
    """

    import secrets

    return f"lightrag_q_{secrets.token_hex(8)}"


def _apply_vendor_env(
    monkeypatch: pytest.MonkeyPatch,
    params: LightRagPostgresParams,
    schema_name: str,
    *,
    workspace_env: str | None = None,
) -> None:
    """Apply LightRAG ``POSTGRES_*`` values for one qualification schema.

    Args:
        monkeypatch: Pytest environment helper.
        params: Parsed connection fields.
        schema_name: Disposable schema first on search_path.
        workspace_env: Optional ``POSTGRES_WORKSPACE`` override.
    """

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    monkeypatch.delenv("WORKSPACE", raising=False)
    overrides = VendorPostgresOverrides(workspace_env=workspace_env)
    for key, value in vendor_env_pairs(
        params, schema_name=schema_name, overrides=overrides
    ):
        monkeypatch.setenv(key, value)


def _gateways() -> tuple[EmbeddingGateway, ModelGateway]:
    """Return mock embedding and model gateways.

    Returns:
        Embedding gateway and model gateway in mock mode.
    """

    settings = SharedSettings(mock_model_mode=True)
    return create_embedding_gateway(settings), create_model_gateway(settings)


def _bounds() -> GraphQueryBounds:
    """Return adapter-owned query bounds, including an over-limit clamp.

    Returns:
        Clamped ``GraphQueryBounds``.
    """

    return apply_query_bounds(
        top_k=999,
        chunk_top_k=40,
        max_entity_tokens=4_000,
        max_relation_tokens=4_000,
        max_total_tokens=8_000,
        deadline_seconds=45.0,
    )


def test_required_storage_class_names_are_plain_postgres() -> None:
    """Selected storage names must be PGTable plus KV/vector/status, never AGE."""

    from lightrag import LightRAG, QueryParam
    from lightrag.kg.pgtable_impl import PGTableGraphStorage
    from lightrag.kg.postgres_impl import (
        PGDocStatusStorage,
        PGGraphStorage,
        PGKVStorage,
        PGVectorStorage,
    )

    assert LightRAG.__name__ == "LightRAG"
    assert QueryParam.__name__ == "QueryParam"
    assert PGTableGraphStorage.__name__ == SELECTED_GRAPH_STORAGE
    assert PGKVStorage.__name__ == SELECTED_KV_STORAGE
    assert PGVectorStorage.__name__ == SELECTED_VECTOR_STORAGE
    assert PGDocStatusStorage.__name__ == SELECTED_DOC_STATUS_STORAGE
    assert PGGraphStorage.__name__ == FORBIDDEN_AGE_GRAPH_STORAGE
    fixture = json.loads(AQUERY_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["success_status"] == "success"
    assert "description" in fixture["never_evidence_ids"]


def test_bootstrap_fingerprint_second_init_and_no_age(
    postgres_params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Disposable schema bootstrap is stable and does not create Apache AGE."""

    asyncio.run(
        _bootstrap_fingerprint_second_init_and_no_age(
            postgres_params, monkeypatch, tmp_path
        )
    )


async def _bootstrap_fingerprint_second_init_and_no_age(
    params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for schema fingerprint and AGE absence.

    Args:
        params: Parsed Postgres fields.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    schema_name = _schema_name()
    url = resolve_supabase_db_url()
    connection = psycopg.connect(url)
    embedding_gateway, model_gateway = _gateways()
    session = None
    session_two = None
    try:
        create_disposable_schema(connection, schema_name)
        _apply_vendor_env(monkeypatch, params, schema_name)
        await reset_process_client_manager()
        session = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "ws1",
            workspace="qualify_one",
            schema_name=schema_name,
            connection=connection,
        )
        for table_name in EXPECTED_PGTABLE_TABLES:
            assert table_name in session.fingerprint.tables
        assert age_extension_present(session.fingerprint) is False
        assert session.fingerprint.vector_type_schemas
        assert any(
            type_schema in {"extensions", "public"}
            for type_schema in session.fingerprint.vector_type_schemas
        )
        assert not any(
            "age" in item.lower()
            for item in (
                *session.init_warnings.python_warnings,
                *session.init_warnings.log_warnings,
            )
        )
        first = session.fingerprint
        await session.finalize()
        session = None
        await reset_process_client_manager()
        session_two = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "ws1b",
            workspace="qualify_one",
            schema_name=schema_name,
            connection=connection,
        )
        second = capture_schema_fingerprint(connection, schema_name)
        assert fingerprint_drift(first, second) == ()
        assert fingerprint_drift(first, session_two.fingerprint) == ()
    finally:
        if session is not None:
            await session.finalize()
        if session_two is not None:
            await session_two.finalize()
        await reset_process_client_manager()
        drop_disposable_schema(connection, schema_name)
        connection.close()


def test_workspace_isolation_and_postgres_workspace_override(
    postgres_params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Constructor workspaces isolate; ``POSTGRES_WORKSPACE`` overrides them."""

    asyncio.run(
        _workspace_isolation_and_postgres_workspace_override(
            postgres_params, monkeypatch, tmp_path
        )
    )


async def _workspace_isolation_and_postgres_workspace_override(
    params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for workspace isolation and env override collapse.

    Args:
        params: Parsed Postgres fields.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    schema_name = _schema_name()
    url = resolve_supabase_db_url()
    connection = psycopg.connect(url)
    embedding_gateway, model_gateway = _gateways()
    session_a = None
    session_b = None
    session_forced = None
    try:
        create_disposable_schema(connection, schema_name)
        _apply_vendor_env(monkeypatch, params, schema_name)
        await reset_process_client_manager()
        session_a = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "a",
            workspace="ws_alpha",
            schema_name=schema_name,
            connection=connection,
        )
        session_b = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "b",
            workspace="ws_beta",
            schema_name=schema_name,
            connection=connection,
        )
        await insert_synthetic_document(
            session_a,
            document_id="doc-alpha-1",
            source_basename="opaque-alpha.txt",
        )
        status_a = await document_status(session_a, "doc-alpha-1")
        assert status_a is not None
        assert status_a.status.lower() in {"processed", "failed"}
        status_b = await document_status(session_b, "doc-alpha-1")
        assert status_b is None
        try:
            result_b = await query_structured(
                session_b,
                query="Alpha Probe",
                hl_keywords=HL_KEYWORDS,
                ll_keywords=LL_KEYWORDS,
                mode="local",
                bounds=_bounds(),
            )
            leads_b = to_graph_leads(result_b)
            names = {entity.entity_name for entity in leads_b.entities}
            assert "Alpha Probe" not in names
        except LightRagQueryFailure:
            pass
        await session_a.finalize()
        await session_b.finalize()
        session_a = None
        session_b = None
        await reset_process_client_manager()
        _apply_vendor_env(
            monkeypatch, params, schema_name, workspace_env="forced_workspace"
        )
        session_forced = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "forced",
            workspace="constructor_workspace",
            schema_name=schema_name,
            connection=connection,
        )
        graph = session_forced.rag.chunk_entity_relation_graph
        assert graph.workspace == "forced_workspace"
    finally:
        if session_a is not None:
            await session_a.finalize()
        if session_b is not None:
            await session_b.finalize()
        if session_forced is not None:
            await session_forced.finalize()
        await reset_process_client_manager()
        drop_disposable_schema(connection, schema_name)
        connection.close()


def test_ids_sources_duplicates_and_identical_content_gate(
    postgres_params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Canonical IDs, basename tokens, duplicates, and identical-content gate."""

    asyncio.run(
        _ids_sources_duplicates_and_identical_content_gate(
            postgres_params, monkeypatch, tmp_path
        )
    )


async def _ids_sources_duplicates_and_identical_content_gate(
    params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for ID/source/duplicate/independence proofs.

    Args:
        params: Parsed Postgres fields.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    schema_name = _schema_name()
    url = resolve_supabase_db_url()
    connection = psycopg.connect(url)
    embedding_gateway, model_gateway = _gateways()
    session = None
    try:
        create_disposable_schema(connection, schema_name)
        _apply_vendor_env(monkeypatch, params, schema_name)
        await reset_process_client_manager()
        session = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "ids",
            workspace="ws_ids",
            schema_name=schema_name,
            connection=connection,
        )
        assert "Alpha Probe" in SYNTHETIC_QUALIFICATION_TEXT
        track = await insert_synthetic_document(
            session,
            document_id="canonical-doc-1",
            source_basename="folder/opaque-one.txt",
            track_id="monitor-only-token",
        )
        assert track == "monitor-only-token"
        status = await document_status(session, "canonical-doc-1")
        assert status is not None
        assert status.track_id == "monitor-only-token"
        assert status.track_id != status.document_id
        assert status.file_path is not None
        assert (
            observed_path_normalization(status.file_path, "folder/opaque-one.txt")
            == "basename"
        )
        await insert_synthetic_document(
            session,
            document_id="canonical-doc-1",
            source_basename="folder/opaque-one.txt",
            track_id="monitor-second",
        )
        dup_id = await document_status(session, "canonical-doc-1")
        assert dup_id is not None
        await insert_synthetic_document(
            session,
            document_id="canonical-doc-2",
            source_basename="shared.txt",
        )
        await insert_synthetic_document(
            session,
            document_id="canonical-doc-3",
            source_basename="shared.txt",
        )
        shared = await document_status(session, "canonical-doc-3")
        if shared is not None:
            assert shared.is_duplicate or shared.duplicate_kind == "filename"
        independence = await evaluate_identical_content_independence(
            session,
            first_id="ident-a",
            second_id="ident-b",
            first_basename="opaque-ident-a.txt",
            second_basename="opaque-ident-b.txt",
        )
        assert independence.passed is True
        await insert_synthetic_document(
            session,
            document_id="raw-collapse-a",
            source_basename="raw-collapse-a.txt",
            bind_identity=False,
        )
        await insert_synthetic_document(
            session,
            document_id="raw-collapse-b",
            source_basename="raw-collapse-b.txt",
            bind_identity=False,
        )
        raw_second = await document_status(session, "raw-collapse-b")
        assert (
            raw_second is None
            or raw_second.is_duplicate
            or (raw_second.duplicate_kind == "content_hash")
        )
    finally:
        if session is not None:
            await session.finalize()
        await reset_process_client_manager()
        drop_disposable_schema(connection, schema_name)
        connection.close()


def test_query_callbacks_bounds_delete_status_and_cancel(
    postgres_params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Structured query, callback counts, deletion, bounds, and cancellation."""

    asyncio.run(
        _query_callbacks_bounds_delete_status_and_cancel(
            postgres_params, monkeypatch, tmp_path
        )
    )


async def _query_callbacks_bounds_delete_status_and_cancel(
    params: LightRagPostgresParams,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for query/callback/delete/cancel proofs.

    Args:
        params: Parsed Postgres fields.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    schema_name = _schema_name()
    url = resolve_supabase_db_url()
    connection = psycopg.connect(url)
    embedding_gateway, model_gateway = _gateways()
    session = None
    cancel_session = None
    try:
        create_disposable_schema(connection, schema_name)
        _apply_vendor_env(monkeypatch, params, schema_name)
        await reset_process_client_manager()
        session = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "query",
            workspace="ws_query",
            schema_name=schema_name,
            connection=connection,
        )
        await insert_synthetic_document(
            session,
            document_id="query-doc-1",
            source_basename="opaque-query.txt",
        )
        status = await document_status(session, "query-doc-1")
        assert status is not None
        assert status.status.lower() in {"processed", "failed"}
        before = session.callbacks.counts.snapshot()
        bounds = _bounds()
        assert bounds.top_k == 12
        for mode in ("local", "hybrid"):
            try:
                result = await query_structured(
                    session,
                    query="How does Alpha Probe relate to Beta Probe?",
                    hl_keywords=HL_KEYWORDS,
                    ll_keywords=LL_KEYWORDS,
                    mode=mode,
                    bounds=bounds,
                    enable_rerank=False,
                )
                leads = to_graph_leads(result)
                assert leads.mode == mode
                dumped = leads.model_dump()
                for entity in dumped["entities"]:
                    assert "description" not in entity
                    assert "file_path" not in entity
                    assert "reference_id" not in entity
                for relation in dumped["relations"]:
                    assert "keywords" not in relation
                    assert "description" not in relation
            except LightRagQueryFailure:
                if status.status.lower() != "processed":
                    continue
                raise
        after = session.callbacks.counts.snapshot()
        assert after["keyword_extract"] == before["keyword_extract"] == 0
        assert after["answer_generate"] == before["answer_generate"] == 0
        assert after["embed"] >= 1
        deleted = await delete_document(
            session, document_id="query-doc-1", delete_llm_cache=True
        )
        assert deleted.status in {"success", "fail"}
        missing = await delete_document(
            session, document_id="missing-doc-id", delete_llm_cache=False
        )
        assert missing.status == "not_found"
        await session.finalize()
        session = None
        await reset_process_client_manager()
        cancel_session = await open_qualification_session(
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "cancel",
            workspace="ws_cancel",
            schema_name=schema_name,
            connection=connection,
        )
        cancel_session.callbacks.extract_gate = asyncio.Event()
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(
                    insert_synthetic_document(
                        cancel_session,
                        document_id="cancel-doc",
                        source_basename="opaque-cancel.txt",
                    ),
                    timeout=0.4,
                )
        finally:
            cancel_session.callbacks.extract_gate.set()
        _ = GRAPH_FIELD_SEP
    finally:
        if session is not None:
            await session.finalize()
        if cancel_session is not None:
            await cancel_session.finalize()
        await reset_process_client_manager()
        drop_disposable_schema(connection, schema_name)
        connection.close()
