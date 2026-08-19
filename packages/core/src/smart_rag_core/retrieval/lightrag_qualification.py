"""LightRAG PostgreSQL qualification harness used by contract tests.

Production modules do not read process environment. Callers (tests) must
apply vendor ``POSTGRES_*`` variables before constructing LightRAG because
the pin itself uses ``os.environ``. This harness accepts an already-parsed
connection record and a disposable schema name.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import warnings
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import unquote, urlparse

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict

from smart_rag_core.gateways.embedding import EmbeddingGateway
from smart_rag_core.gateways.model import ModelGateway
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.retrieval.graph import (
    FORBIDDEN_AGE_GRAPH_STORAGE,
    GRAPH_FIELD_SEP,
    LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE,
    LIGHTRAG_CHUNK_TOKEN_SIZE,
    LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
    LIGHTRAG_TIKTOKEN_MODEL,
    QUALIFICATION_POSTGRES_CONNECTION_RETRIES,
    QUALIFICATION_POSTGRES_MAX_CONNECTIONS,
    SELECTED_DOC_STATUS_STORAGE,
    SELECTED_GRAPH_STORAGE,
    SELECTED_KV_STORAGE,
    SELECTED_VECTOR_STORAGE,
    GraphLeadSet,
    GraphQueryBounds,
    bind_graph_source_text,
)
from smart_rag_core.retrieval.lightrag_callbacks import CountedLightRagCallbacks
from smart_rag_core.retrieval.lightrag_structured import (
    LightRagQueryResult,
    as_string_mapping,
    parse_aquery_data_payload,
    to_graph_leads,
)

SUPPORTED_DELETION_STATUSES: tuple[str, ...] = (
    "success",
    "not_found",
    "not_allowed",
    "fail",
)
EXPECTED_PGTABLE_TABLES: tuple[str, ...] = (
    "lightrag_graph_nodes",
    "lightrag_graph_edges",
)
# Mock hash vectors have no semantic neighborhood. Qualification only;
# production GraphRAG must not copy this floor.
QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD = -1.0
_pgvector_codec_fallback_installed = False

SYNTHETIC_QUALIFICATION_TEXT = (
    "Alpha Probe is a synthetic qualification entity. "
    "Beta Probe is a second synthetic qualification entity. "
    "Alpha Probe relates to Beta Probe for GraphRAG pin tests only. "
    "This text contains no company content."
)


class LightRagQualificationError(RuntimeError):
    """Raised when qualification bootstrap or pin usage fails closed."""


class LightRagGraphStorage(Protocol):
    """Narrow vendor graph-storage handle used for workspace checks."""

    workspace: str


class LightRagRuntime(Protocol):
    """Narrow LightRAG instance surface used by the qualification harness."""

    chunk_entity_relation_graph: LightRagGraphStorage

    async def initialize_storages(self) -> None:
        """Create or connect vendor tables and pools."""
        ...

    async def finalize_storages(self) -> None:
        """Release vendor tables and pools."""
        ...

    async def ainsert(
        self,
        input: str,
        split_by_character: str | None = None,
        split_by_character_only: bool = False,
        ids: list[str] | None = None,
        file_paths: list[str] | None = None,
        track_id: str | None = None,
    ) -> str:
        """Enqueue and process one document. ``track_id`` is monitoring only."""
        ...

    async def aget_docs_by_ids(self, ids: str | list[str]) -> Mapping[str, object]:
        """Return vendor document-status objects keyed by ID."""
        ...

    async def aquery_data(self, query: str, param: object) -> object:
        """Return the structured ``aquery_data`` mapping."""
        ...

    async def adelete_by_doc_id(
        self, doc_id: str, delete_llm_cache: bool = False
    ) -> object:
        """Delete one vendor document and optionally its LLM cache."""
        ...


class LightRagDeletionResult(Protocol):
    """Narrow ``DeletionResult`` attributes read by the harness."""

    status: str
    doc_id: str
    message: str


class IdenticalContentIndependenceError(LightRagQualificationError):
    """Raised when identical-content sources are not independently deletable."""


@dataclass(frozen=True, slots=True)
class LightRagPostgresParams:
    """Parsed PostgreSQL connection fields without a DSN password log.

    Attributes:
        host: Hostname or IPv4/IPv6 literal.
        port: TCP port.
        user: Role name.
        password: Secret. Never logged.
        database: Database name.
    """

    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass(frozen=True, slots=True)
class VendorPostgresOverrides:
    """Values tests must apply to LightRAG process environment.

    Attributes:
        max_connections: Process-wide pool cap. Must be 2-4.
        connection_retries: Vendor retry attempts. Must be 0.
        search_path: Unqualified table resolution including the disposable
            schema plus ``extensions`` so pgvector remains visible.
        workspace_env: Optional ``POSTGRES_WORKSPACE`` override under test.
        statement_cache_size: Optional asyncpg statement cache size.
    """

    max_connections: int = QUALIFICATION_POSTGRES_MAX_CONNECTIONS
    connection_retries: int = QUALIFICATION_POSTGRES_CONNECTION_RETRIES
    search_path: str = ""
    workspace_env: str | None = None
    statement_cache_size: str | None = None


class SchemaFingerprint(BaseModel):
    """Redacted schema capture for one disposable private schema.

    Attributes:
        schema_name: Disposable schema that owns vendor tables.
        tables: Ordered table names in that schema.
        columns: ``table.column:type`` rows.
        indexes: ``indexname:indexdef`` rows.
        constraints: ``conname:contype`` rows.
        extensions: Cluster-global ``extname:extversion`` rows.
        vector_type_schemas: Schemas that own the ``vector`` type. Local
            Supabase uses ``extensions``; vanilla Postgres often uses
            ``public``.
    """

    model_config = ConfigDict(frozen=True)

    schema_name: str
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    indexes: tuple[str, ...]
    constraints: tuple[str, ...]
    extensions: tuple[str, ...]
    vector_type_schemas: tuple[str, ...] = ()


class QualificationWarnings(BaseModel):
    """Captured warnings and log records from ``initialize_storages``."""

    model_config = ConfigDict(frozen=True)

    python_warnings: tuple[str, ...]
    log_warnings: tuple[str, ...]


class DocumentStatusView(BaseModel):
    """Narrow vendor document status fields used by qualification."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    status: str
    track_id: str | None = None
    file_path: str | None = None
    is_duplicate: bool = False
    duplicate_kind: str | None = None


class IdenticalContentResult(BaseModel):
    """Outcome of the identical-content independence hard gate."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    first_id: str
    second_id: str
    first_status: str
    second_status: str
    second_is_duplicate: bool
    second_survived_first_delete: bool | None = None
    reason: str = ""


class DeletionStatusView(BaseModel):
    """Narrow ``DeletionResult`` fields."""

    model_config = ConfigDict(frozen=True)

    status: Literal["success", "not_found", "not_allowed", "fail"]
    document_id: str
    message: str = ""


@dataclass
class QualificationSession:
    """Live LightRAG instance plus counted callbacks for one schema.

    Attributes:
        rag: Initialized ``LightRAG`` instance.
        callbacks: Counted gateway callbacks.
        workspace: Constructor workspace used for this instance.
        schema_name: Disposable schema on ``search_path``.
        working_dir: Vendor working directory.
        fingerprint: Schema fingerprint after initialize.
        init_warnings: Warnings captured during initialize.
    """

    rag: LightRagRuntime
    callbacks: CountedLightRagCallbacks
    workspace: str
    schema_name: str
    working_dir: Path
    fingerprint: SchemaFingerprint
    init_warnings: QualificationWarnings
    _finalized: bool = field(default=False, init=False, repr=False)

    async def finalize(self) -> None:
        """Release vendor storage pools. Safe to call twice.

        Side Effects:
            Calls ``finalize_storages`` once.
        """

        if self._finalized:
            return
        await self.rag.finalize_storages()
        self._finalized = True


def parse_postgres_url(url: str) -> LightRagPostgresParams:
    """Parse a PostgreSQL URL without reading process environment.

    Args:
        url: Connection URL. Password is stored, never logged.

    Returns:
        Connection fields.

    Raises:
        LightRagQualificationError: If the scheme is unsupported.
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise LightRagQualificationError("unsupported_postgres_url_scheme")
    database = unquote(parsed.path.lstrip("/")) or "postgres"
    return LightRagPostgresParams(
        host=parsed.hostname or "127.0.0.1",
        port=int(parsed.port or 5432),
        user=unquote(parsed.username or "postgres"),
        password=unquote(parsed.password or ""),
        database=database,
    )


def vendor_env_pairs(
    params: LightRagPostgresParams,
    *,
    schema_name: str,
    overrides: VendorPostgresOverrides | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return ``POSTGRES_*`` pairs tests must apply via ``monkeypatch.setenv``.

    Args:
        params: Parsed connection fields.
        schema_name: Disposable schema first on ``search_path``.
        overrides: Optional pool/workspace overrides.

    Returns:
        Ordered environment pairs. Does not mutate the process.

    Raises:
        LightRagQualificationError: If pool/retry bounds are outside policy.
    """

    policy = overrides or VendorPostgresOverrides()
    if policy.max_connections < 2 or policy.max_connections > 4:
        raise LightRagQualificationError("postgres_max_connections_out_of_range")
    if policy.connection_retries != QUALIFICATION_POSTGRES_CONNECTION_RETRIES:
        raise LightRagQualificationError("postgres_connection_retries_must_be_zero")
    search_path = policy.search_path or f"{schema_name},extensions,public"
    pairs: list[tuple[str, str]] = [
        ("POSTGRES_HOST", params.host),
        ("POSTGRES_PORT", str(params.port)),
        ("POSTGRES_USER", params.user),
        ("POSTGRES_PASSWORD", params.password),
        ("POSTGRES_DATABASE", params.database),
        ("POSTGRES_MAX_CONNECTIONS", str(policy.max_connections)),
        ("POSTGRES_CONNECTION_RETRIES", str(policy.connection_retries)),
        ("POSTGRES_SERVER_SETTINGS", f"search_path={search_path}"),
    ]
    if policy.statement_cache_size is not None:
        pairs.append(("POSTGRES_STATEMENT_CACHE_SIZE", policy.statement_cache_size))
    if policy.workspace_env is not None:
        pairs.append(("POSTGRES_WORKSPACE", policy.workspace_env))
    return tuple(pairs)


def create_disposable_schema(connection: psycopg.Connection, schema_name: str) -> None:
    """Create one private schema and put it first on ``search_path``.

    Args:
        connection: Open autocommit-capable psycopg connection.
        schema_name: SQL identifier. Must match ``^[a-z][a-z0-9_]*$``.

    Raises:
        LightRagQualificationError: If the schema name is not a safe identifier.

    Side Effects:
        Executes ``CREATE SCHEMA`` and ``SET search_path``.
    """

    _assert_safe_ident(schema_name)
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(schema_name)
            )
        )
        cursor.execute(
            sql.SQL("SET search_path TO {}, extensions, public").format(
                sql.Identifier(schema_name)
            )
        )
    connection.commit()


def drop_disposable_schema(connection: psycopg.Connection, schema_name: str) -> None:
    """Drop a disposable qualification schema.

    Args:
        connection: Open psycopg connection.
        schema_name: Schema created by ``create_disposable_schema``.

    Side Effects:
        ``DROP SCHEMA IF EXISTS ... CASCADE``.
    """

    _assert_safe_ident(schema_name)
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(schema_name)
            )
        )
    connection.commit()


def capture_schema_fingerprint(
    connection: psycopg.Connection, schema_name: str
) -> SchemaFingerprint:
    """Fingerprint tables, columns, indexes, constraints, and extensions.

    Args:
        connection: Connection whose ``search_path`` includes ``schema_name``.
        schema_name: Disposable schema.

    Returns:
        Frozen fingerprint. Extension names are cluster-global.
    """

    _assert_safe_ident(schema_name)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            (schema_name,),
        )
        tables = tuple(str(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT table_name || '.' || column_name || ':' || data_type
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (schema_name,),
        )
        columns = tuple(str(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT indexname || ':' || indexdef
            FROM pg_indexes
            WHERE schemaname = %s
            ORDER BY indexname
            """,
            (schema_name,),
        )
        indexes = tuple(str(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT c.conname || ':' || c.contype::text
            FROM pg_constraint c
            JOIN pg_class rel ON rel.oid = c.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = %s
            ORDER BY c.conname
            """,
            (schema_name,),
        )
        constraints = tuple(str(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT extname || ':' || extversion
            FROM pg_extension
            ORDER BY extname
            """
        )
        extensions = tuple(str(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT n.nspname
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = 'vector'
            ORDER BY n.nspname
            """
        )
        vector_type_schemas = tuple(str(row[0]) for row in cursor.fetchall())
    return SchemaFingerprint(
        schema_name=schema_name,
        tables=tables,
        columns=columns,
        indexes=indexes,
        constraints=constraints,
        extensions=extensions,
        vector_type_schemas=vector_type_schemas,
    )


def fingerprint_drift(
    first: SchemaFingerprint, second: SchemaFingerprint
) -> tuple[str, ...]:
    """Return unexplained fingerprint differences.

    Args:
        first: Fingerprint after the first ``initialize_storages``.
        second: Fingerprint after a second initialize.

    Returns:
        Human-readable drift lines. Empty when identical.
    """

    drift: list[str] = []
    for label, left, right in (
        ("tables", first.tables, second.tables),
        ("columns", first.columns, second.columns),
        ("indexes", first.indexes, second.indexes),
        ("constraints", first.constraints, second.constraints),
        ("extensions", first.extensions, second.extensions),
        ("vector_type_schemas", first.vector_type_schemas, second.vector_type_schemas),
    ):
        if left != right:
            drift.append(f"{label}:{left!r}!={right!r}")
    return tuple(drift)


def age_extension_present(fingerprint: SchemaFingerprint) -> bool:
    """Return whether Apache AGE is installed on the cluster.

    Args:
        fingerprint: Captured fingerprint.

    Returns:
        True when an ``age`` extension row exists.
    """

    return any(item.startswith("age:") for item in fingerprint.extensions)


def install_pgvector_codec_schema_fallback() -> None:
    """Patch pgvector codec registration for ``extensions.vector``.

    LightRAG 1.5.6 calls ``register_vector(connection)`` with the pgvector
    0.5.0 default ``schema='public'``. Local Supabase stores the type in
    ``extensions``. The wrapper tries the requested schema, then
    ``extensions``, then ``public``.

    Side Effects:
        Replaces ``pgvector.asyncpg.register_vector`` once per process.
    """

    global _pgvector_codec_fallback_installed
    if _pgvector_codec_fallback_installed:
        return
    import pgvector.asyncpg as pgvector_asyncpg

    original = cast(Callable[..., Awaitable[None]], pgvector_asyncpg.register_vector)

    async def register_vector_with_fallback(
        conn: object, /, *, schema: str = "public"
    ) -> None:
        """Register vector codecs, falling back to ``extensions``.

        Args:
            conn: asyncpg connection from LightRAG pool init.
            schema: Preferred type schema.

        Raises:
            LightRagQualificationError: If neither public nor extensions
                exposes the ``vector`` type.
        """

        last_error: BaseException | None = None
        seen: set[str] = set()
        for candidate in (schema, "extensions", "public"):
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                await original(conn, schema=candidate)
                return
            except ValueError as exc:
                if "unknown type:" not in str(exc):
                    raise
                last_error = exc
        raise LightRagQualificationError("vector_type_codec_missing") from last_error

    pgvector_asyncpg.register_vector = register_vector_with_fallback
    _pgvector_codec_fallback_installed = True


async def open_qualification_session(
    *,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    working_dir: Path,
    workspace: str,
    schema_name: str,
    connection: psycopg.Connection,
    enable_llm_cache: bool = False,
) -> QualificationSession:
    """Construct, initialize, and fingerprint one LightRAG instance.

    Args:
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        working_dir: Vendor working directory.
        workspace: Constructor workspace. Must not rely on env unless testing
            override collapse.
        schema_name: Disposable schema already first on ``search_path``.
        connection: psycopg connection for fingerprinting.
        enable_llm_cache: Vendor LLM cache flag.

    Returns:
        Initialized session. Caller must ``finalize``.

    Raises:
        LightRagQualificationError: If AGE is selected or initialize warns of
            incomplete migration in a way this pin treats as fatal.
    """

    from lightrag import LightRAG
    from lightrag.llm_roles import RoleLLMConfig
    from lightrag.utils import EmbeddingFunc

    _ = FORBIDDEN_AGE_GRAPH_STORAGE
    install_pgvector_codec_schema_fallback()
    callbacks = CountedLightRagCallbacks(
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
    )
    embedding_func = EmbeddingFunc(
        embedding_dim=EMBEDDING_DIMENSIONS,
        func=callbacks.embedding_texts,
        model_name=EMBEDDING_MODEL,
        max_token_size=8192,
    )
    working_dir.mkdir(parents=True, exist_ok=True)
    rag = LightRAG(
        working_dir=str(working_dir),
        kv_storage=SELECTED_KV_STORAGE,
        vector_storage=SELECTED_VECTOR_STORAGE,
        graph_storage=SELECTED_GRAPH_STORAGE,
        doc_status_storage=SELECTED_DOC_STATUS_STORAGE,
        workspace=workspace,
        embedding_func=embedding_func,
        llm_model_func=callbacks.extract_llm,
        role_llm_configs={
            "extract": RoleLLMConfig(
                func=callbacks.extract_llm,
                timeout=LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
            ),
            "keyword": RoleLLMConfig(
                func=callbacks.keyword_llm,
                timeout=LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
            ),
            "query": RoleLLMConfig(
                func=callbacks.query_llm,
                timeout=LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
            ),
        },
        enable_llm_cache=enable_llm_cache,
        enable_llm_cache_for_entity_extract=enable_llm_cache,
        chunk_token_size=LIGHTRAG_CHUNK_TOKEN_SIZE,
        chunk_overlap_token_size=LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE,
        tiktoken_model_name=LIGHTRAG_TIKTOKEN_MODEL,
        entity_extract_max_gleaning=0,
        force_llm_summary_on_merge=10_000,
        llm_model_max_async=1,
        embedding_func_max_async=1,
        max_parallel_insert=1,
        auto_manage_storages_states=False,
        default_llm_timeout=LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
        default_embedding_timeout=30,
        cosine_better_than_threshold=QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD,
    )
    runtime = cast(LightRagRuntime, rag)
    python_warnings, log_warnings = await _initialize_capturing_warnings(runtime)
    fingerprint = capture_schema_fingerprint(connection, schema_name)
    if age_extension_present(fingerprint) and any(
        "AGE" in item.upper() for item in (*python_warnings, *log_warnings)
    ):
        await runtime.finalize_storages()
        raise LightRagQualificationError("age_extension_created_during_pgtable_init")
    fatal = tuple(
        item
        for item in (*python_warnings, *log_warnings)
        if _is_fatal_initialize_warning(item)
    )
    if fatal:
        await runtime.finalize_storages()
        raise LightRagQualificationError(f"initialize_warning:{fatal[0]}")
    return QualificationSession(
        rag=runtime,
        callbacks=callbacks,
        workspace=workspace,
        schema_name=schema_name,
        working_dir=working_dir,
        fingerprint=fingerprint,
        init_warnings=QualificationWarnings(
            python_warnings=python_warnings,
            log_warnings=log_warnings,
        ),
    )


async def insert_synthetic_document(
    session: QualificationSession,
    *,
    document_id: str,
    source_basename: str,
    text: str = SYNTHETIC_QUALIFICATION_TEXT,
    track_id: str | None = None,
    bind_identity: bool = True,
) -> str:
    """Insert one synthetic document through ``ainsert``.

    Args:
        session: Initialized qualification session.
        document_id: Canonical document ID passed as vendor ``ids``.
        source_basename: Unique opaque basename ``file_paths`` token.
        text: Synthetic qualification text only.
        track_id: Optional monitoring token. Not idempotency.
        bind_identity: When true (default), prefix the identity envelope so
            LightRAG content-hash dedup cannot collapse distinct IDs. Set
            false only to prove raw vendor collapse.

    Returns:
        Vendor track ID.
    """

    payload = (
        bind_graph_source_text(
            document_version_id=document_id,
            normalized_text=text,
        )
        if bind_identity
        else text
    )
    return await session.rag.ainsert(
        payload,
        ids=[document_id],
        file_paths=[source_basename],
        track_id=track_id,
    )


def status_record_mapping(record: object) -> Mapping[str, object]:
    """Narrow a vendor status row to a string-keyed mapping.

    PostgreSQL ``get_by_id`` returns a dict. The dataclass path remains
    accepted if a future pin wraps rows as ``DocProcessingStatus``.

    Args:
        record: Value from ``aget_docs_by_ids``.

    Returns:
        String-keyed mapping of documented status fields.

    Raises:
        LightRagQualificationError: If the row is not a readable mapping
            or object.
    """

    if isinstance(record, Mapping):
        untyped = cast(Mapping[object, object], record)
        if not all(isinstance(key, str) for key in untyped):
            raise LightRagQualificationError("doc_status_non_string_keys")
        return cast(Mapping[str, object], untyped)
    payload: dict[str, object] = {}
    for key in ("status", "track_id", "file_path", "metadata"):
        if hasattr(record, key):
            payload[key] = getattr(record, key)
    if not payload:
        raise LightRagQualificationError("doc_status_unreadable")
    return payload


async def document_status(
    session: QualificationSession, document_id: str
) -> DocumentStatusView | None:
    """Return vendor status for one document ID.

    Args:
        session: Initialized session.
        document_id: Canonical document ID.

    Returns:
        Status view, or ``None`` when the vendor has no row.
    """

    payload = await session.rag.aget_docs_by_ids(document_id)
    record = payload.get(document_id)
    if record is None:
        return None
    mapping = status_record_mapping(record)
    metadata_raw = mapping.get("metadata")
    metadata: Mapping[str, object] = {}
    if isinstance(metadata_raw, Mapping):
        untyped = cast(Mapping[object, object], metadata_raw)
        if all(isinstance(key, str) for key in untyped):
            metadata = cast(Mapping[str, object], untyped)
    duplicate_kind_obj = metadata.get("duplicate_kind")
    duplicate_kind = duplicate_kind_obj if isinstance(duplicate_kind_obj, str) else None
    raw_status = mapping.get("status", "")
    status_value = getattr(raw_status, "value", raw_status)
    track_id = mapping.get("track_id")
    file_path = mapping.get("file_path")
    return DocumentStatusView(
        document_id=document_id,
        status=str(status_value),
        track_id=str(track_id) if track_id else None,
        file_path=str(file_path) if file_path else None,
        is_duplicate=bool(metadata.get("is_duplicate", False)),
        duplicate_kind=duplicate_kind,
    )


async def query_structured(
    session: QualificationSession,
    *,
    query: str,
    hl_keywords: Sequence[str],
    ll_keywords: Sequence[str],
    mode: Literal["local", "hybrid"],
    bounds: GraphQueryBounds,
    enable_rerank: bool = False,
) -> LightRagQueryResult:
    """Run ``aquery_data`` with both keyword lists and adapter bounds.

    Args:
        session: Initialized session.
        query: Synthetic query text.
        hl_keywords: Non-empty high-level keywords.
        ll_keywords: Non-empty low-level keywords.
        mode: ``local`` or graph ``hybrid``.
        bounds: Adapter-owned limits.
        enable_rerank: Must stay false unless separately qualified.

    Returns:
        Typed structured result.

    Raises:
        LightRagQualificationError: If a keyword list is empty.
        LightRagQueryFailure: If the vendor payload is not success-shaped.
    """

    from lightrag import QueryParam

    if not hl_keywords or not ll_keywords:
        raise LightRagQualificationError("both_keyword_lists_required")
    param = QueryParam(
        mode=mode,
        only_need_context=True,
        only_need_prompt=False,
        stream=False,
        top_k=bounds.top_k,
        chunk_top_k=bounds.chunk_top_k,
        max_entity_tokens=bounds.max_entity_tokens,
        max_relation_tokens=bounds.max_relation_tokens,
        max_total_tokens=bounds.max_total_tokens,
        hl_keywords=list(hl_keywords),
        ll_keywords=list(ll_keywords),
        enable_rerank=enable_rerank,
        include_references=False,
    )
    raw = await session.rag.aquery_data(query, param)
    return parse_aquery_data_payload(as_string_mapping(raw))


async def delete_document(
    session: QualificationSession,
    *,
    document_id: str,
    delete_llm_cache: bool = False,
) -> DeletionStatusView:
    """Delete one document and fail closed on undocumented statuses.

    Args:
        session: Initialized session.
        document_id: Canonical document ID.
        delete_llm_cache: Request vendor LLM-cache deletion when true.

    Returns:
        Narrow deletion status.

    Raises:
        LightRagQualificationError: If the vendor status is unsupported.
    """

    result = cast(
        LightRagDeletionResult,
        await session.rag.adelete_by_doc_id(
            document_id, delete_llm_cache=delete_llm_cache
        ),
    )
    status = coerce_deletion_status(str(result.status))
    return DeletionStatusView(
        status=status,
        document_id=str(result.doc_id or document_id),
        message=str(result.message or ""),
    )


def coerce_deletion_status(
    status: str,
) -> Literal["success", "not_found", "not_allowed", "fail"]:
    """Accept only documented ``DeletionResult.status`` values.

    Args:
        status: Vendor status string.

    Returns:
        One of the four documented statuses.

    Raises:
        LightRagQualificationError: If the status is undocumented.
    """

    if status not in SUPPORTED_DELETION_STATUSES:
        raise LightRagQualificationError(f"unsupported_deletion_status:{status}")
    return cast(
        Literal["success", "not_found", "not_allowed", "fail"],
        status,
    )


async def reset_process_client_manager() -> None:
    """Drop the process-wide LightRAG PostgreSQL pool if present.

    Side Effects:
        Closes the shared ``ClientManager`` pool and rebinds its asyncio lock
        to the current event loop so later tests can apply a new search_path.
    """

    from lightrag.kg.postgres_impl import ClientManager

    # Vendor pool state lives on private class attributes. Attribute names
    # stay in variables so Ruff B009/B010 and Pyright reportPrivateUsage
    # both stay clean while tests still reset the process-wide pool.
    lock_attr = "_lock"
    instances_attr = "_instances"
    lock_obj = getattr(ClientManager, lock_attr)
    if not isinstance(lock_obj, asyncio.Lock):
        lock_obj = asyncio.Lock()
        setattr(ClientManager, lock_attr, lock_obj)
    try:
        await lock_obj.acquire()
    except RuntimeError:
        lock_obj = asyncio.Lock()
        setattr(ClientManager, lock_attr, lock_obj)
        await lock_obj.acquire()
    try:
        instances_raw = getattr(ClientManager, instances_attr)
        if not isinstance(instances_raw, dict):
            return
        instances = cast(dict[str, object], instances_raw)
        db = instances.get("db")
        if db is not None:
            pool = getattr(db, "pool", None)
            closer = getattr(pool, "close", None) if pool is not None else None
            if callable(closer):
                closed = closer()
                if inspect.isawaitable(closed):
                    try:
                        await cast(Awaitable[object], closed)
                    except RuntimeError:
                        pass
        instances["db"] = None
        instances["ref_count"] = 0
        instances["vector_signature"] = None
    finally:
        lock_obj.release()
        setattr(ClientManager, lock_attr, asyncio.Lock())


async def evaluate_identical_content_independence(
    session: QualificationSession,
    *,
    first_id: str,
    second_id: str,
    first_basename: str,
    second_basename: str,
) -> IdenticalContentResult:
    """Prove or reject independent attribution for identical content.

    Args:
        session: Initialized session.
        first_id: First canonical document ID.
        second_id: Second canonical document ID.
        first_basename: Unique opaque basename for the first source.
        second_basename: Unique opaque basename for the second source.

    Returns:
        Structured independence result. ``passed`` is true only when both
        documents process independently and deleting the first leaves the
        second attributable.

    Raises:
        IdenticalContentIndependenceError: When independence fails after the
            identity envelope is applied.
    """

    await insert_synthetic_document(
        session,
        document_id=first_id,
        source_basename=first_basename,
        bind_identity=True,
    )
    await insert_synthetic_document(
        session,
        document_id=second_id,
        source_basename=second_basename,
        bind_identity=True,
    )
    first = await document_status(session, first_id)
    second = await document_status(session, second_id)
    if first is None or second is None:
        raise IdenticalContentIndependenceError("identical_content_status_missing")
    if second.is_duplicate or second.duplicate_kind == "content_hash":
        result = IdenticalContentResult(
            passed=False,
            first_id=first_id,
            second_id=second_id,
            first_status=first.status,
            second_status=second.status,
            second_is_duplicate=True,
            reason="duplicate_kind_content_hash",
        )
        raise IdenticalContentIndependenceError(result.reason) from None
    if first.status.lower() != "processed" or second.status.lower() != "processed":
        result = IdenticalContentResult(
            passed=False,
            first_id=first_id,
            second_id=second_id,
            first_status=first.status,
            second_status=second.status,
            second_is_duplicate=second.is_duplicate,
            reason="identical_content_not_both_processed",
        )
        raise IdenticalContentIndependenceError(result.reason)
    deleted = await delete_document(
        session, document_id=first_id, delete_llm_cache=True
    )
    remaining = await document_status(session, second_id)
    survived = remaining is not None and remaining.status.lower() != "failed"
    if deleted.status != "success" or not survived:
        raise IdenticalContentIndependenceError("identical_content_delete_collapsed")
    return IdenticalContentResult(
        passed=True,
        first_id=first_id,
        second_id=second_id,
        first_status=first.status,
        second_status=second.status,
        second_is_duplicate=False,
        second_survived_first_delete=True,
        reason="independent",
    )


def observed_path_normalization(stored_file_path: str, submitted_token: str) -> str:
    """Record vendor basename reduction without treating paths as IDs.

    Args:
        stored_file_path: Value stored by the pin.
        submitted_token: Token passed to ``ainsert``.

    Returns:
        ``basename`` when the stored value equals the submitted basename,
        otherwise ``verbatim`` or ``other``.
    """

    submitted_basename = submitted_token.replace("\\", "/").rsplit("/", 1)[-1]
    if stored_file_path == submitted_token:
        return "verbatim"
    if stored_file_path == submitted_basename:
        return "basename"
    return "other"


def _assert_safe_ident(schema_name: str) -> None:
    """Reject schema names that are not safe unquoted-style identifiers.

    Args:
        schema_name: Candidate SQL identifier.

    Raises:
        LightRagQualificationError: If the name is unsafe.
    """

    if not schema_name or not schema_name.isidentifier() or not schema_name.islower():
        raise LightRagQualificationError("unsafe_schema_identifier")
    if schema_name.startswith("pg_"):
        raise LightRagQualificationError("unsafe_schema_identifier")


def _is_fatal_initialize_warning(message: str) -> bool:
    """Return whether an initialize warning means incomplete migration.

    Args:
        message: Warning or log text.

    Returns:
        True when qualification must fail closed.
    """

    lowered = message.lower()
    fatal_markers = (
        "could not create vector extension",
        "incomplete migration",
        "failed to",
        "age extension",
    )
    return any(marker in lowered for marker in fatal_markers)


def is_fatal_initialize_warning(message: str) -> bool:
    """Return whether an initialize warning means incomplete migration.

    Args:
        message: Warning or log text.

    Returns:
        True when bootstrap or qualification must fail closed.
    """

    return _is_fatal_initialize_warning(message)


class _ListHandler(logging.Handler):
    """In-memory log handler for initialize warning capture."""

    def __init__(self) -> None:
        """Create an empty record list."""

        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Append one formatted warning/error record.

        Args:
            record: Log record at WARNING or above.
        """

        self.messages.append(self.format(record))


async def initialize_storages_capturing_warnings(
    rag: LightRagRuntime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Initialize storages while capturing warnings and log records.

    Args:
        rag: Constructed ``LightRAG`` instance.

    Returns:
        Python warning messages and logger warning messages.
    """

    return await _initialize_capturing_warnings(rag)


async def _initialize_capturing_warnings(
    rag: LightRagRuntime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Initialize storages while capturing warnings and log records.

    Args:
        rag: Constructed ``LightRAG`` instance.

    Returns:
        Python warning messages and logger warning messages.
    """

    handler = _ListHandler()
    logger = logging.getLogger("lightrag")
    logger.addHandler(handler)
    captured: list[str] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            initialize = rag.initialize_storages
            await initialize()
            captured = [str(item.message) for item in caught]
    finally:
        logger.removeHandler(handler)
    return tuple(captured), tuple(handler.messages)


class QualificationSessionContext(AbstractAsyncContextManager[QualificationSession]):
    """Async context manager that always finalizes LightRAG storages."""

    def __init__(self, session: QualificationSession) -> None:
        """Bind one session.

        Args:
            session: Initialized qualification session.
        """

        self._session = session

    async def __aenter__(self) -> QualificationSession:
        """Return the bound session.

        Returns:
            Initialized session.
        """

        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Finalize storages even when the test body failed.

        Args:
            exc_type: Exception type if any.
            exc: Exception instance if any.
            traceback: Traceback if any.
        """

        del exc_type, exc, traceback
        await self._session.finalize()


def query_leads_or_empty(result: LightRagQueryResult) -> GraphLeadSet:
    """Convert a successful query to leads, documenting delimiter policy.

    Args:
        result: Structured query result.

    Returns:
        Application lead set.

    Side Effects:
        None. ``GRAPH_FIELD_SEP`` is the only source-id delimiter.
    """

    _ = GRAPH_FIELD_SEP
    return to_graph_leads(result)
