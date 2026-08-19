"""Runtime LightRAG factory that attaches existing private PostgreSQL storage.

This module may import LightRAG. Application, agent, backend, and worker
source trees must not. Runtime never calls vendor DDL: ``initdb`` CREATE,
``check_tables`` CREATE/ALTER, ``setup_table``, or ``execute(_DDL)``.

``POSTGRES_*`` process variables are applied from typed ``LIGHTRAG_DB_URL``
because pinned LightRAG 1.5.6 reads ``os.environ``. Passwords are never
logged. ``POSTGRES_WORKSPACE`` is never set; constructor workspace only.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TypeVar, cast
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ConfigDict, SecretStr

from smart_rag_core.gateways.embedding import EmbeddingGateway, create_embedding_gateway
from smart_rag_core.gateways.model import ModelGateway, create_model_gateway
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.query_admission.ceilings import (
    QueryRetrieveBudget,
    assert_retrieve_kind_available,
    debit_retrieve_budget,
    usage_kind_caps,
)
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.service import (
    consume_query_reservation,
    record_query_llm_usage,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE,
    LIGHTRAG_CHUNK_TOKEN_SIZE,
    LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_RUNTIME_ROLE,
    LIGHTRAG_SEARCH_PATH,
    LIGHTRAG_TIKTOKEN_MODEL,
    QUALIFICATION_POSTGRES_CONNECTION_RETRIES,
    RUNTIME_COSINE_BETTER_THAN_THRESHOLD,
    RUNTIME_POSTGRES_MAX_CONNECTIONS,
    SELECTED_DOC_STATUS_STORAGE,
    SELECTED_GRAPH_STORAGE,
    SELECTED_KV_STORAGE,
    SELECTED_VECTOR_STORAGE,
    GraphIndexDeleteResult,
    GraphIndexEnqueueResult,
    GraphLeadSet,
    GraphQueryBounds,
    bind_graph_source_text,
    clamp_global_steering,
)
from smart_rag_core.retrieval.lightrag_callbacks import CountedLightRagCallbacks
from smart_rag_core.retrieval.lightrag_qualification import (
    QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD,
    DocumentStatusView,
    LightRagDeletionResult,
    LightRagPostgresParams,
    LightRagQualificationError,
    LightRagRuntime,
    SchemaFingerprint,
    VendorPostgresOverrides,
    age_extension_present,
    capture_schema_fingerprint,
    coerce_deletion_status,
    fingerprint_drift,
    install_pgvector_codec_schema_fallback,
    parse_postgres_url,
    reset_process_client_manager,
    status_record_mapping,
    vendor_env_pairs,
)
from smart_rag_core.retrieval.lightrag_structured import (
    as_string_mapping,
    parse_aquery_data_payload,
    to_graph_leads,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings.base import (
    SharedSettings,
    pop_process_environ,
    set_process_environ,
    snapshot_process_environ,
)

LIGHTRAG_SCHEMA_NAME = "lightrag"
VECTOR_TABLE_SUFFIX = "text_embedding_3_large_1024d"
REVIEWED_VENDOR_TABLES: tuple[str, ...] = (
    "lightrag_doc_chunks",
    "lightrag_doc_full",
    "lightrag_doc_status",
    "lightrag_entity_chunks",
    "lightrag_full_entities",
    "lightrag_full_relations",
    "lightrag_graph_edges",
    "lightrag_graph_nodes",
    "lightrag_llm_cache",
    "lightrag_relation_chunks",
    "lightrag_vdb_chunks_text_embedding_3_large_1024d",
    "lightrag_vdb_entity_text_embedding_3_large_1024d",
    "lightrag_vdb_relation_text_embedding_3_large_1024d",
    "schema_capture_status",
)
REVIEWED_VECTOR_TABLES: tuple[str, ...] = (
    "lightrag_vdb_chunks_text_embedding_3_large_1024d",
    "lightrag_vdb_entity_text_embedding_3_large_1024d",
    "lightrag_vdb_relation_text_embedding_3_large_1024d",
)
_VENDOR_KV_TABLES: tuple[str, ...] = (
    "LIGHTRAG_DOC_FULL",
    "LIGHTRAG_DOC_CHUNKS",
    "LIGHTRAG_LLM_CACHE",
    "LIGHTRAG_DOC_STATUS",
    "LIGHTRAG_FULL_ENTITIES",
    "LIGHTRAG_FULL_RELATIONS",
    "LIGHTRAG_ENTITY_CHUNKS",
    "LIGHTRAG_RELATION_CHUNKS",
)


class LightRagAdapterError(LightRagQualificationError):
    """Raised when runtime attach, fingerprint, or pool policy fails closed."""


class ReviewedSchemaManifest(BaseModel):
    """Reviewed private-schema fingerprint used by runtime attach.

    Attributes:
        pin_version: Immutable LightRAG pin.
        schema_name: Private schema that owns vendor tables.
        search_path: Required ``POSTGRES_SERVER_SETTINGS`` search_path.
        embedding_model: Pinned embedding model.
        embedding_dimensions: Pinned output dimension.
        tables: Ordered vendor table names including capture status.
    """

    model_config = ConfigDict(frozen=True)

    pin_version: str = LIGHTRAG_PINNED_VERSION
    schema_name: str = LIGHTRAG_SCHEMA_NAME
    search_path: str = LIGHTRAG_SEARCH_PATH
    embedding_model: str = EMBEDDING_MODEL
    embedding_dimensions: int = EMBEDDING_DIMENSIONS
    tables: tuple[str, ...] = REVIEWED_VENDOR_TABLES


def reviewed_schema_manifest() -> ReviewedSchemaManifest:
    """Return the Packet 2 reviewed private-schema table list.

    Returns:
        Frozen manifest derived from pin 1.5.6 ``_DDL`` / ``TABLES`` /
        ``setup_table`` plus ``schema_capture_status``.
    """

    return ReviewedSchemaManifest()


def load_reviewed_fingerprint_fixture(path: Path) -> ReviewedSchemaManifest:
    """Load the committed reviewed fingerprint fixture.

    Args:
        path: JSON fixture under ``tests/fixtures/lightrag/``.

    Returns:
        Parsed manifest.

    Raises:
        LightRagAdapterError: If the fixture is missing or malformed.
    """

    if not path.is_file():
        raise LightRagAdapterError("reviewed_fingerprint_fixture_missing")
    return ReviewedSchemaManifest.model_validate_json(path.read_text(encoding="utf-8"))


def assert_postgres_workspace_unset() -> None:
    """Fail closed when ``POSTGRES_WORKSPACE`` is present in process env.

    Raises:
        LightRagAdapterError: If the vendor env override is set.

    Side Effects:
        Reads a snapshot of process environment. Does not log values.
    """

    env = snapshot_process_environ()
    if env.get("POSTGRES_WORKSPACE"):
        raise LightRagAdapterError("postgres_workspace_env_override")


def assert_search_path(search_path: str) -> None:
    """Require the controlled private search_path.

    Args:
        search_path: Candidate search_path value.

    Raises:
        LightRagAdapterError: If the path is not ``lightrag,extensions,public``.
    """

    if search_path != LIGHTRAG_SEARCH_PATH:
        raise LightRagAdapterError("wrong_search_path")


def assert_embedding_pin(*, model_name: str, dimensions: int) -> None:
    """Require the process-wide first vector model/dimension pin.

    Args:
        model_name: Embedding model name supplied to ``EmbeddingFunc``.
        dimensions: Embedding output dimension.

    Raises:
        LightRagAdapterError: If the pair is not ``text-embedding-3-large`` at
            1024 dimensions.
    """

    if model_name != EMBEDDING_MODEL or dimensions != EMBEDDING_DIMENSIONS:
        raise LightRagAdapterError("incompatible_vector_config")


def search_path_from_server_settings(server_settings: str) -> str:
    """Extract ``search_path`` from vendor ``POSTGRES_SERVER_SETTINGS``.

    Args:
        server_settings: Ampersand-delimited GUC assignments.

    Returns:
        The ``search_path`` value, or an empty string when absent.
    """

    for part in server_settings.split("&"):
        if part.startswith("search_path="):
            return part.removeprefix("search_path=")
    return ""


def bootstrap_server_settings() -> str:
    """Return vendor ``POSTGRES_SERVER_SETTINGS`` for schema-admin bootstrap.

    Returns:
        Controlled private search_path without runtime ``session_authorization``.
    """

    return f"search_path={LIGHTRAG_SEARCH_PATH}"


def runtime_server_settings() -> str:
    """Return vendor ``POSTGRES_SERVER_SETTINGS`` for runtime attach.

    Returns:
        Controlled private ``search_path``. Runtime role is applied with
        ``SET ROLE app_lightrag`` on pool init/reset rather than as a startup
        GUC, because vendor ``RESET ALL`` would drop ``session_authorization``.
    """

    return bootstrap_server_settings()


def apply_lightrag_postgres_env(
    params: LightRagPostgresParams,
    *,
    max_connections: int,
    server_settings: str,
    workspace_env: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """Apply LightRAG ``POSTGRES_*`` variables from a typed DSN.

    Args:
        params: Parsed connection fields. Password is never logged.
        max_connections: Process-wide pool cap. Must be 2-4.
        server_settings: ``POSTGRES_SERVER_SETTINGS`` value.
        workspace_env: Must stay ``None`` on runtime/bootstrap happy paths.

    Returns:
        Applied non-secret pairs (password omitted).

    Raises:
        LightRagAdapterError: If pool/retry/search_path/workspace policy fails.

    Side Effects:
        Writes ``POSTGRES_*`` keys consumed by pinned LightRAG. Does not log
        the password.
    """

    assert_postgres_workspace_unset()
    if workspace_env is not None:
        raise LightRagAdapterError("postgres_workspace_env_override")
    assert_search_path(search_path_from_server_settings(server_settings))
    if max_connections < 2 or max_connections > RUNTIME_POSTGRES_MAX_CONNECTIONS:
        raise LightRagAdapterError("postgres_max_connections_out_of_range")
    overrides = VendorPostgresOverrides(
        max_connections=max_connections,
        connection_retries=QUALIFICATION_POSTGRES_CONNECTION_RETRIES,
        search_path=LIGHTRAG_SEARCH_PATH,
        workspace_env=None,
    )
    pairs = vendor_env_pairs(
        params, schema_name=LIGHTRAG_SCHEMA_NAME, overrides=overrides
    )
    applied: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == "POSTGRES_SERVER_SETTINGS":
            set_process_environ(key, server_settings)
            applied.append((key, server_settings))
            continue
        set_process_environ(key, value)
        if key != "POSTGRES_PASSWORD":
            applied.append((key, value))
    pop_process_environ("POSTGRES_WORKSPACE")
    pop_process_environ("WORKSPACE")
    return tuple(applied)


def parse_lightrag_db_url(secret: SecretStr) -> LightRagPostgresParams:
    """Parse a typed LightRAG DSN without logging the secret.

    Args:
        secret: ``LIGHTRAG_DB_URL`` or schema-admin DSN.

    Returns:
        Connection fields.

    Raises:
        LightRagAdapterError: If the URL scheme is unsupported.
    """

    return parse_postgres_url(secret.get_secret_value())


def public_vendor_tables(connection: psycopg.Connection) -> tuple[str, ...]:
    """Return vendor-named tables incorrectly created in ``public``.

    Args:
        connection: Open psycopg connection.

    Returns:
        Ordered public table names that start with ``lightrag_``.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name LIKE 'lightrag\\_%' ESCAPE '\\'
            ORDER BY table_name
            """
        )
        return tuple(str(row[0]) for row in cursor.fetchall())


def assert_private_schema_postconditions(
    fingerprint: SchemaFingerprint,
    *,
    connection: psycopg.Connection,
    manifest: ReviewedSchemaManifest | None = None,
) -> None:
    """Fail closed on AGE, public objects, or reviewed table drift.

    Args:
        fingerprint: Capture of schema ``lightrag``.
        connection: Connection used to inspect ``public``.
        manifest: Expected reviewed tables. Defaults to the pin manifest.

    Raises:
        LightRagAdapterError: If a postcondition fails.
    """

    expected = manifest or reviewed_schema_manifest()
    if age_extension_present(fingerprint):
        raise LightRagAdapterError("age_extension_present")
    leaked = public_vendor_tables(connection)
    if leaked:
        raise LightRagAdapterError(f"public_vendor_tables:{leaked[0]}")
    actual = tuple(name for name in fingerprint.tables)
    if actual != expected.tables:
        raise LightRagAdapterError("schema_fingerprint_tables_drift")
    if not any(
        type_schema in {"extensions", "public"}
        for type_schema in fingerprint.vector_type_schemas
    ):
        raise LightRagAdapterError("vector_type_missing")


def assert_fingerprint_matches(
    live: SchemaFingerprint, reviewed: SchemaFingerprint
) -> None:
    """Require live private-schema fingerprint equality.

    Args:
        live: Fingerprint after initialize or attach.
        reviewed: Reviewed fixture fingerprint.

    Raises:
        LightRagAdapterError: If any inventoried field drifts.
    """

    drift = fingerprint_drift(live, reviewed)
    if drift:
        raise LightRagAdapterError(f"schema_fingerprint_drift:{drift[0]}")


def pooler_safe_asyncpg_kwargs(
    kwargs: dict[str, object],
    *,
    host: str | None = None,
) -> dict[str, object]:
    """Disable prepared statements on pooled Postgres connections.

    Hosted Supabase session poolers close asyncpg connections that use a
    statement cache, which aborts LightRAG extract with
    ``connection was closed in the middle of operation``. TLS is left to
    the vendor ``POSTGRES_SSL_MODE`` so Windows trust-store failures do
    not block attach.

    Args:
        kwargs: Keyword arguments destined for ``asyncpg.create_pool``.
        host: Unused; kept so callers can pass the DSN host later.

    Returns:
        A new mapping with ``statement_cache_size=0``.
    """

    del host
    updated = dict(kwargs)
    updated.setdefault("statement_cache_size", 0)
    return updated


async def _set_runtime_role(connection: object) -> None:
    """Apply ``SET ROLE app_lightrag`` on one pooled connection.

    Args:
        connection: asyncpg connection from the vendor pool.

    Raises:
        LightRagAdapterError: If the connection cannot execute SQL.
    """

    execute = getattr(connection, "execute", None)
    if not callable(execute):
        raise LightRagAdapterError("runtime_role_set_unavailable")
    await cast(Callable[[str], Awaitable[object]], execute)(
        f"SET ROLE {LIGHTRAG_RUNTIME_ROLE}"
    )


class _LightRagSharedStorage(Protocol):
    """Typed view of LightRAG shared-storage locking used during attach.

    Attributes:
        get_data_init_lock: Vendor lock factory around storage initialize.
    """

    get_data_init_lock: Callable[..., AbstractAsyncContextManager[object]]


class _AsyncpgPoolModule(Protocol):
    """Typed view of ``asyncpg`` used to wrap ``create_pool``.

    Attributes:
        create_pool: Vendor pool factory. Signature is intentionally wide
            because pinned asyncpg stubs expose Unknown parameters.
    """

    create_pool: Callable[..., Awaitable[object]]


_QUERY_RETRIEVE_BUDGET: ContextVar[QueryRetrieveBudget | None] = ContextVar(
    "lightrag_query_retrieve_budget",
    default=None,
)
_TCallback = TypeVar("_TCallback")


def install_query_budget_consume(callbacks: CountedLightRagCallbacks) -> None:
    """Wrap LightRAG callbacks so query-time gateway calls debit remaining.

    Index paths stay uncounted unless a retrieve budget ContextVar is bound.
    ``aquery_data_structured`` sets that ContextVar for one consume window.

    Args:
        callbacks: Counted gateway callbacks constructed for this engine.

    Side Effects:
        Replaces embedding and LLM methods on ``callbacks`` with wrappers
        that consume the run-local reservation or fail closed.
    """

    original_embed = callbacks.embedding_texts
    original_extract = callbacks.extract_llm
    original_keyword = callbacks.keyword_llm
    original_query = callbacks.query_llm

    async def embedding_texts(texts: list[str]) -> object:
        """Counted query-time embedding callback.

        Args:
            texts: Vendor embedding inputs.

        Returns:
            Embedding matrix from the shared gateway.
        """

        return await _counted_query_callback(
            usage_kind="embedding",
            model_id=EMBEDDING_MODEL,
            send=lambda: original_embed(texts),
        )

    async def extract_llm(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **kwargs: object,
    ) -> str:
        """Counted extract-role LightRAG callback.

        Args:
            prompt: Vendor user prompt.
            system_prompt: Optional vendor system prompt.
            history_messages: Unused vendor history.
            **kwargs: Ignored vendor extras.

        Returns:
            Gateway content.
        """

        return await _counted_query_callback(
            usage_kind="lightrag",
            model_id=f"lightrag-{LIGHTRAG_PINNED_VERSION}",
            send=lambda: original_extract(
                prompt, system_prompt, history_messages, **kwargs
            ),
        )

    async def keyword_llm(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **kwargs: object,
    ) -> str:
        """Counted keyword-role LightRAG callback.

        Args:
            prompt: Vendor user prompt.
            system_prompt: Optional vendor system prompt.
            history_messages: Unused vendor history.
            **kwargs: Ignored vendor extras.

        Returns:
            Gateway content.
        """

        return await _counted_query_callback(
            usage_kind="lightrag",
            model_id=f"lightrag-{LIGHTRAG_PINNED_VERSION}",
            send=lambda: original_keyword(
                prompt, system_prompt, history_messages, **kwargs
            ),
        )

    async def query_llm(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **kwargs: object,
    ) -> str:
        """Counted query-role LightRAG callback.

        Args:
            prompt: Vendor user prompt.
            system_prompt: Optional vendor system prompt.
            history_messages: Unused vendor history.
            **kwargs: Ignored vendor extras.

        Returns:
            Gateway content.
        """

        return await _counted_query_callback(
            usage_kind="lightrag",
            model_id=f"lightrag-{LIGHTRAG_PINNED_VERSION}",
            send=lambda: original_query(
                prompt, system_prompt, history_messages, **kwargs
            ),
        )

    callbacks.embedding_texts = embedding_texts  # type: ignore[method-assign]
    callbacks.extract_llm = extract_llm  # type: ignore[method-assign]
    callbacks.keyword_llm = keyword_llm  # type: ignore[method-assign]
    callbacks.query_llm = query_llm  # type: ignore[method-assign]


async def _counted_query_callback(
    *,
    usage_kind: str,
    model_id: str,
    send: Callable[[], Awaitable[_TCallback]],
) -> _TCallback:
    """Consume remaining for one LightRAG callback or invoke it uncounted.

    Same-loop form of ``execute_counted_model_call``: durable consume uses
    the reservation RPCs, then the callback awaits on this event loop.

    Args:
        usage_kind: ``embedding`` or ``lightrag``.
        model_id: Provider model identifier.
        send: Async callback invocation.

    Returns:
        Callback result.

    Raises:
        QueryCeilingError: When remaining model calls cannot cover the kind.
        QueryBudgetError: When remaining USD cannot cover the kind cap.

    Side Effects:
        Debits the ContextVar budget when bound. Unbound query/index
        callbacks are not reservation-counted.
    """

    budget = _QUERY_RETRIEVE_BUDGET.get()
    if budget is None:
        return await send()
    assert_retrieve_kind_available(
        remaining_model_calls=budget.remaining_model_calls,
        remaining_usd=budget.remaining_usd,
        usage_kind=usage_kind,
    )
    connection = budget.connection
    caller = budget.caller
    run_id = budget.run_id
    reservation_id = budget.reservation_id
    if (
        isinstance(connection, psycopg.Connection)
        and isinstance(caller, CallerContext)
        and isinstance(run_id, UUID)
        and isinstance(reservation_id, UUID)
    ):
        usd_cap, prompt_cap, completion_cap = usage_kind_caps(usage_kind)
        consumed = consume_query_reservation(
            connection,
            caller=caller,
            reservation_id=reservation_id,
            expected_version=budget.expected_version,
            amount_usd=usd_cap,
            prompt_tokens=prompt_cap,
            completion_tokens=completion_cap,
        )
        budget.expected_version = consumed.optimistic_version
        debit_retrieve_budget(budget, usage_kind, remaining_usd=consumed.remaining_usd)
        try:
            result = await send()
        except TimeoutAfterSendError:
            record_query_llm_usage(
                connection,
                caller=caller,
                run_id=run_id,
                reservation_id=reservation_id,
                reservation_version=consumed.optimistic_version,
                usage_kind=usage_kind,
                model_id=model_id,
                provider_attempt_id=str(uuid4()),
                prompt_tokens=prompt_cap,
                completion_tokens=completion_cap,
                cost_usd=usd_cap,
                timeout_after_send=True,
            )
            raise
        record_query_llm_usage(
            connection,
            caller=caller,
            run_id=run_id,
            reservation_id=reservation_id,
            reservation_version=consumed.optimistic_version,
            usage_kind=usage_kind,
            model_id=model_id,
            provider_attempt_id=str(uuid4()),
            prompt_tokens=prompt_cap,
            completion_tokens=completion_cap,
            cost_usd=usd_cap,
            timeout_after_send=False,
        )
        return result
    debit_retrieve_budget(budget, usage_kind)
    return await send()


async def construct_lightrag_engine(
    *,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    working_dir: Path,
    workspace: str,
    enable_llm_cache: bool = False,
    cosine_better_than_threshold: float = RUNTIME_COSINE_BETTER_THAN_THRESHOLD,
) -> tuple[LightRagRuntime, CountedLightRagCallbacks]:
    """Construct one ``LightRAG`` instance without initializing storages.

    Args:
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        working_dir: Vendor working directory for local files.
        workspace: Constructor workspace. Must not come from env.
        enable_llm_cache: Vendor LLM cache flag.
        cosine_better_than_threshold: Vendor vector floor. Use ``-1.0`` in
            mock mode so hash embeddings remain retrievable.

    Returns:
        Constructed runtime and counted callbacks.

    Raises:
        LightRagAdapterError: If workspace env is set or the embedding pin
            does not match.

    Side Effects:
        Creates ``working_dir`` and installs the pgvector codec fallback.
    """

    from lightrag import LightRAG
    from lightrag.llm_roles import RoleLLMConfig
    from lightrag.utils import EmbeddingFunc

    assert_postgres_workspace_unset()
    assert_embedding_pin(model_name=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)
    install_pgvector_codec_schema_fallback()
    callbacks = CountedLightRagCallbacks(
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
    )
    install_query_budget_consume(callbacks)
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
        cosine_better_than_threshold=cosine_better_than_threshold,
    )
    return cast(LightRagRuntime, rag), callbacks


@asynccontextmanager
async def runtime_attach_without_ddl() -> AsyncGenerator[None]:
    """Patch vendor initialize so runtime never issues CREATE/ALTER.

    Yields:
        Control while ``ClientManager.get_client`` opens a pool, attaches
        storages, and skips DDL / ``initdb`` CREATE / ``setup_table`` /
        ``execute(_DDL)``.

    Side Effects:
        Temporarily replaces vendor methods. Restores them on exit.
    """

    from lightrag.kg import postgres_impl as postgres_impl_mod
    from lightrag.kg import shared_storage as shared_storage_mod
    from lightrag.kg.pgtable_impl import PGTableGraphStorage
    from lightrag.kg.postgres_impl import PGVectorStorage, PostgreSQLDB

    get_data_init_lock = cast(
        _LightRagSharedStorage, shared_storage_mod
    ).get_data_init_lock
    original_check_tables = PostgreSQLDB.check_tables
    original_configure_vector = PostgreSQLDB.configure_vector_extension
    original_setup_table = PGVectorStorage.setup_table
    original_graph_initialize = PGTableGraphStorage.initialize
    original_create_pool = cast(
        _AsyncpgPoolModule, postgres_impl_mod.asyncpg
    ).create_pool

    async def configure_vector_extension_verify(
        self: PostgreSQLDB, connection: object
    ) -> None:
        """Require an existing ``vector`` type and never CREATE EXTENSION.

        Args:
            self: Vendor database handle.
            connection: asyncpg connection from pool bootstrap.

        Raises:
            LightRagAdapterError: If the ``vector`` type is missing.
        """

        del self
        fetchrow = getattr(connection, "fetchrow", None)
        if not callable(fetchrow):
            raise LightRagAdapterError("vector_type_codec_missing")
        row = await cast(Callable[[str], Awaitable[object]], fetchrow)(
            """
            SELECT n.nspname
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = 'vector'
            ORDER BY n.nspname
            LIMIT 1
            """
        )
        if row is None:
            raise LightRagAdapterError("vector_type_missing")

    async def check_tables_verify_only(self: PostgreSQLDB) -> None:
        """Require reviewed tables to exist; never CREATE or ALTER.

        Args:
            self: Vendor database handle.

        Raises:
            LightRagAdapterError: If a required table is missing.
        """

        for table_name in _VENDOR_KV_TABLES:
            try:
                await self.query(f"SELECT 1 FROM {table_name} LIMIT 1")  # noqa: S608
            except Exception as exc:
                raise LightRagAdapterError(
                    f"schema_drift_missing_table:{table_name.lower()}"
                ) from exc
        for table_name in REVIEWED_VECTOR_TABLES:
            try:
                await self.query(f"SELECT 1 FROM {table_name} LIMIT 1")  # noqa: S608
            except Exception as exc:
                raise LightRagAdapterError(
                    f"schema_drift_missing_vector_table:{table_name}"
                ) from exc
        try:
            await self.query("SELECT 1 FROM lightrag_graph_nodes LIMIT 1")
            await self.query("SELECT 1 FROM lightrag_graph_edges LIMIT 1")
        except Exception as exc:
            raise LightRagAdapterError("schema_drift_missing_graph_table") from exc

    async def setup_table_verify_only(
        db: PostgreSQLDB,
        table_name: str,
        workspace: str,
        embedding_dim: int,
        legacy_table_name: str,
        base_table: str,
    ) -> None:
        """Require the suffixed vector table; never CREATE or migrate.

        Args:
            db: Shared PostgreSQL client.
            table_name: Expected suffixed vector table.
            workspace: Constructor workspace. Unused for DDL skip.
            embedding_dim: Must match the 1024 pin.
            legacy_table_name: Unused on the attach path.
            base_table: Unused on the attach path.

        Raises:
            LightRagAdapterError: If dimension/table verification fails.
        """

        del workspace, legacy_table_name, base_table
        if embedding_dim != EMBEDDING_DIMENSIONS:
            raise LightRagAdapterError("incompatible_vector_config")
        exists = await db.check_table_exists(table_name)
        if not exists:
            raise LightRagAdapterError(
                f"schema_drift_missing_vector_table:{table_name}"
            )

    async def graph_initialize_without_ddl(self: PGTableGraphStorage) -> None:
        """Attach ``ClientManager`` without executing vendor ``_DDL``.

        Args:
            self: Graph storage instance.

        Raises:
            LightRagAdapterError: If ``POSTGRES_WORKSPACE`` overrode the
                constructor workspace.
        """

        from lightrag.kg.postgres_impl import ClientManager

        async with get_data_init_lock():
            if self.db is None:
                self.db = await ClientManager.get_client(
                    vector_storage=self.global_config.get("vector_storage")
                )
                if self.db.workspace:
                    raise LightRagAdapterError("postgres_workspace_env_override")
                if not getattr(self, "workspace", None):
                    self.workspace = DEFAULT_GRAPH_WORKSPACE

    async def create_pool_with_runtime_role(*args: object, **kwargs: object) -> object:
        """Create the vendor pool and bind ``SET ROLE`` on init/reset.

        Args:
            args: Positional ``asyncpg.create_pool`` arguments.
            kwargs: Keyword ``asyncpg.create_pool`` arguments.

        Returns:
            Vendor connection pool.
        """

        kwargs = pooler_safe_asyncpg_kwargs(dict(kwargs))
        original_init = kwargs.get("init")
        original_reset = kwargs.get("reset")

        async def init_with_role(connection: object) -> None:
            """Register codecs, then drop to the runtime role.

            Args:
                connection: New pooled asyncpg connection.
            """

            if callable(original_init):
                await cast(Callable[[object], Awaitable[object]], original_init)(
                    connection
                )
            await _set_runtime_role(connection)

        async def reset_with_role(connection: object) -> None:
            """Re-apply the runtime role after vendor ``RESET ALL``.

            Args:
                connection: Pooled connection being returned to the pool.
            """

            if callable(original_reset):
                await cast(Callable[[object], Awaitable[object]], original_reset)(
                    connection
                )
            await _set_runtime_role(connection)

        kwargs["init"] = init_with_role
        kwargs["reset"] = reset_with_role
        return await original_create_pool(*args, **kwargs)

    PostgreSQLDB.configure_vector_extension = configure_vector_extension_verify
    PostgreSQLDB.check_tables = check_tables_verify_only
    PGVectorStorage.setup_table = setup_table_verify_only
    PGTableGraphStorage.initialize = graph_initialize_without_ddl
    postgres_impl_mod.asyncpg.create_pool = create_pool_with_runtime_role
    try:
        yield
    finally:
        PostgreSQLDB.configure_vector_extension = original_configure_vector
        PostgreSQLDB.check_tables = original_check_tables
        PGVectorStorage.setup_table = original_setup_table
        PGTableGraphStorage.initialize = original_graph_initialize
        postgres_impl_mod.asyncpg.create_pool = original_create_pool


@dataclass
class LightRagRuntimeAdapter:
    """Attached LightRAG runtime that skips vendor DDL.

    Attributes:
        rag: Initialized ``LightRAG`` instance.
        callbacks: Counted gateway callbacks.
        workspace: Constructor workspace.
        working_dir: Vendor working directory.
        fingerprint: Private-schema fingerprint after attach.
        max_connections: Process-wide pool cap used for this attach.
        query_budget: Optional retrieve ledger. Bound per query run so
            ``aquery_data`` callbacks consume remaining.
    """

    rag: LightRagRuntime
    callbacks: CountedLightRagCallbacks
    workspace: str
    working_dir: Path
    fingerprint: SchemaFingerprint
    max_connections: int
    query_budget: QueryRetrieveBudget | None = field(default=None, repr=False)
    _finalized: bool = field(default=False, init=False, repr=False)

    async def enqueue_insert(
        self,
        *,
        document_id: str,
        text: str,
        source_token: str,
        track_id: str,
    ) -> GraphIndexEnqueueResult:
        """Insert envelope-bound version text through qualified ``ainsert``.

        Args:
            document_id: Canonical document version ID used as vendor ``ids``.
            text: Normalized version text, not yet envelope-bound.
            source_token: Unique opaque basename token.
            track_id: Fresh monitoring token. Never an idempotency key.

        Returns:
            Monitoring metadata including the vendor track id and status
            label from enqueue. Terminal polling is the caller's job.

        Side Effects:
            Calls vendor ``ainsert``. ``track_id`` is monitoring only.
        """

        enveloped = bind_graph_source_text(
            document_version_id=document_id,
            normalized_text=text,
        )
        returned = await self.rag.ainsert(
            enveloped,
            ids=[document_id],
            file_paths=[source_token],
            track_id=track_id,
        )
        status_view = await self.vendor_document_status(document_id)
        status_label = status_view.status if status_view is not None else "pending"
        return GraphIndexEnqueueResult(
            document_id=document_id,
            track_id=str(returned or track_id),
            status=status_label,
        )

    async def vendor_document_status(
        self,
        document_id: str,
    ) -> DocumentStatusView | None:
        """Return vendor document status for one canonical version ID.

        Args:
            document_id: Canonical document version ID.

        Returns:
            Narrow status view, or ``None`` when the vendor has no row.
        """

        payload = await self.rag.aget_docs_by_ids(document_id)
        if not payload:
            return None
        record = payload.get(document_id)
        if record is None and len(payload) == 1:
            record = next(iter(payload.values()))
        if record is None:
            return None
        mapping = status_record_mapping(record)
        raw_status = mapping.get("status")
        status = str(raw_status) if raw_status is not None else "pending"
        raw_track = mapping.get("track_id")
        raw_path = mapping.get("file_path")
        return DocumentStatusView(
            document_id=document_id,
            status=status,
            track_id=str(raw_track) if raw_track is not None else None,
            file_path=str(raw_path) if raw_path is not None else None,
            is_duplicate=bool(mapping.get("is_duplicate", False)),
            duplicate_kind=(
                str(mapping["duplicate_kind"])
                if mapping.get("duplicate_kind") is not None
                else None
            ),
        )

    async def delete_document(
        self,
        *,
        document_id: str,
        delete_llm_cache: bool = True,
    ) -> GraphIndexDeleteResult:
        """Delete one vendor document and optionally its LLM cache.

        Args:
            document_id: Canonical document version ID.
            delete_llm_cache: When true, request privacy cache deletion.

        Returns:
            Vendor deletion status. Unsupported statuses fail closed.

        Raises:
            LightRagQualificationError: If the vendor status is undocumented.
        """

        result = cast(
            LightRagDeletionResult,
            await self.rag.adelete_by_doc_id(
                document_id,
                delete_llm_cache=delete_llm_cache,
            ),
        )
        status = coerce_deletion_status(str(result.status))
        return GraphIndexDeleteResult(
            document_id=str(result.doc_id or document_id),
            status=status,
            message=str(result.message or ""),
        )

    async def finalize(self) -> None:
        """Release vendor storage pools. Safe to call twice.

        Side Effects:
            Calls ``finalize_storages`` once, then resets ClientManager.
        """

        if self._finalized:
            return
        try:
            await self.rag.finalize_storages()
        finally:
            await reset_process_client_manager()
            self._finalized = True

    def client_pool_max_size(self) -> int | None:
        """Return the process-wide asyncpg pool max size when present.

        Returns:
            Pool max size, or ``None`` after finalize.
        """

        from lightrag.kg.postgres_impl import ClientManager

        instances_raw = getattr(ClientManager, "_instances", None)
        if not isinstance(instances_raw, dict):
            return None
        instances = cast(dict[str, object], instances_raw)
        db = instances.get("db")
        if db is None:
            return None
        pool = getattr(db, "pool", None)
        if pool is None:
            return None
        getter = getattr(pool, "get_max_size", None)
        if callable(getter):
            value = getter()
            return int(value) if isinstance(value, int) else None
        max_size = getattr(pool, "_maxsize", None)
        return int(max_size) if isinstance(max_size, int) else None

    async def current_database_user(self) -> str:
        """Return ``current_user`` on a pooled runtime connection.

        Returns:
            Role name visible to pooled DML.

        Raises:
            LightRagAdapterError: If ClientManager is missing or the query
                does not return a role name.
        """

        from lightrag.kg.postgres_impl import ClientManager

        instances_raw = getattr(ClientManager, "_instances", None)
        if not isinstance(instances_raw, dict):
            raise LightRagAdapterError("client_manager_uninitialized")
        instances = cast(dict[str, object], instances_raw)
        db = instances.get("db")
        if db is None:
            raise LightRagAdapterError("client_manager_uninitialized")
        query = getattr(db, "query", None)
        if not callable(query):
            raise LightRagAdapterError("client_manager_query_unavailable")
        row = await cast(Callable[..., Awaitable[object]], query)(
            "SELECT current_user AS role_name"
        )
        if not isinstance(row, dict) or "role_name" not in row:
            raise LightRagAdapterError("runtime_role_query_failed")
        typed_row = cast(dict[str, object], row)
        return str(typed_row["role_name"])

    async def _vendor_query(
        self,
        sql: str,
        params: list[object],
    ) -> list[dict[str, object]]:
        """Run one unqualified vendor catalog query on the runtime pool.

        Args:
            sql: Parameterized SQL using ``$1`` placeholders. Table names are
                unqualified on search_path ``lightrag,extensions,public``.
            params: Query parameters.

        Returns:
            Row mappings. Empty when the catalog has no matches.

        Raises:
            LightRagAdapterError: If ClientManager is missing or query fails.
        """

        from lightrag.kg.postgres_impl import ClientManager

        instances_raw = getattr(ClientManager, "_instances", None)
        if not isinstance(instances_raw, dict):
            raise LightRagAdapterError("client_manager_uninitialized")
        instances = cast(dict[str, object], instances_raw)
        db = instances.get("db")
        if db is None:
            raise LightRagAdapterError("client_manager_uninitialized")
        query = getattr(db, "query", None)
        if not callable(query):
            raise LightRagAdapterError("client_manager_query_unavailable")
        rows = await cast(Callable[..., Awaitable[object]], query)(sql, params, True)
        if rows is None:
            return []
        if isinstance(rows, dict):
            return [cast(dict[str, object], rows)]
        if isinstance(rows, list):
            return cast(list[dict[str, object]], rows)
        raise LightRagAdapterError("vendor_query_shape")

    async def list_vendor_doc_chunks(
        self,
        *,
        workspace: str,
        document_id: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return vendor document chunks for one source id.

        Args:
            workspace: Constructor workspace.
            document_id: Canonical version UUID string (``full_doc_id``).
            limit: Inclusive cap plus one so callers can detect overflow.

        Returns:
            Chunk rows with ``id``, ``content``, ``full_doc_id``, ``file_path``.
        """

        return await self._vendor_query(
            """
            SELECT id, workspace, full_doc_id, content, file_path, chunk_order_index
            FROM lightrag_doc_chunks
            WHERE workspace = $1 AND full_doc_id = $2
            ORDER BY chunk_order_index
            LIMIT $3
            """,
            [workspace, document_id, limit],
        )

    async def list_vendor_entity_joins(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return entity-to-chunk joins for one workspace.

        Args:
            workspace: Constructor workspace.
            limit: Inclusive cap plus one so callers can detect overflow.

        Returns:
            Rows with ``id`` (entity name) and ``chunk_ids`` jsonb.
        """

        return await self._vendor_query(
            """
            SELECT id, workspace, chunk_ids, count
            FROM lightrag_entity_chunks
            WHERE workspace = $1
            LIMIT $2
            """,
            [workspace, limit],
        )

    async def list_vendor_relation_joins(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return relation-to-chunk joins for one workspace.

        Args:
            workspace: Constructor workspace.
            limit: Inclusive cap plus one so callers can detect overflow.

        Returns:
            Rows with sorted endpoint keys and ``chunk_ids`` jsonb.
        """

        return await self._vendor_query(
            """
            SELECT id, workspace, chunk_ids, count
            FROM lightrag_relation_chunks
            WHERE workspace = $1
            LIMIT $2
            """,
            [workspace, limit],
        )

    async def list_vendor_graph_nodes(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return graph nodes including source_id properties.

        Args:
            workspace: Constructor workspace.
            limit: Inclusive cap plus one so callers can detect overflow.

        Returns:
            Node rows. Callers read ``properties`` jsonb, never rendered prose.
        """

        return await self._vendor_query(
            """
            SELECT id, workspace, properties
            FROM lightrag_graph_nodes
            WHERE workspace = $1
            LIMIT $2
            """,
            [workspace, limit],
        )

    async def list_vendor_graph_edges(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return graph edges including structured relation fields.

        Args:
            workspace: Constructor workspace.
            limit: Inclusive cap plus one so callers can detect overflow.

        Returns:
            Edge rows. Relation labels come from ``properties.keywords``.
        """

        return await self._vendor_query(
            """
            SELECT src_id, tgt_id, workspace, properties
            FROM lightrag_graph_edges
            WHERE workspace = $1
            LIMIT $2
            """,
            [workspace, limit],
        )

    async def aquery_data_structured(
        self,
        *,
        query: str,
        mode: Literal["local", "hybrid", "global"],
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Run ``aquery_data`` with both keyword lists and adapter bounds.

        Args:
            query: Original user query.
            mode: ``local``, graph ``hybrid``, or ``global``. Never ``naive``
                or ``mix``.
            hl_keywords: Non-empty high-level keywords.
            ll_keywords: Non-empty low-level keywords.
            bounds: Adapter-owned candidate and token limits.

        Returns:
            Structured leads. Descriptions and file paths are not identifiers.

        Raises:
            LightRagAdapterError: Empty keywords or unsupported mode.
            LightRagQueryFailure: Vendor payload is not a success envelope.

        Side Effects:
            One vendor ``aquery_data`` call. Native rerank stays disabled.
        """

        from lightrag import QueryParam

        if mode not in {"local", "hybrid", "global"}:
            raise LightRagAdapterError("unsupported_graph_mode")
        high = tuple(item.strip() for item in hl_keywords if item.strip())
        low = tuple(item.strip() for item in ll_keywords if item.strip())
        if not high or not low:
            raise LightRagAdapterError("both_keyword_lists_required")
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
            hl_keywords=list(high),
            ll_keywords=list(low),
            enable_rerank=False,
            include_references=False,
        )
        token = _QUERY_RETRIEVE_BUDGET.set(self.query_budget)
        try:
            raw = await self.rag.aquery_data(query, param)
        finally:
            _QUERY_RETRIEVE_BUDGET.reset(token)
        leads = to_graph_leads(parse_aquery_data_payload(as_string_mapping(raw)))
        if mode == "global":
            return clamp_global_steering(leads)
        return leads

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Return local-mode entity-centered leads.

        Args:
            query: Original user query text.
            hl_keywords: Non-empty high-level keywords.
            ll_keywords: Non-empty low-level keywords.
            bounds: Adapter-owned limits.

        Returns:
            Structured local leads.
        """

        return await self.aquery_data_structured(
            query=query,
            mode="local",
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Return graph-hybrid leads. This is not application Hybrid RAG.

        Args:
            query: Original user query text.
            hl_keywords: Non-empty high-level keywords.
            ll_keywords: Non-empty low-level keywords.
            bounds: Adapter-owned limits.

        Returns:
            Structured graph-hybrid leads.
        """

        return await self.aquery_data_structured(
            query=query,
            mode="hybrid",
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Return at most three topic/entity steering expansions.

        Args:
            query: Original user query text.
            hl_keywords: Non-empty high-level keywords.
            ll_keywords: Non-empty low-level keywords.
            bounds: Adapter-owned limits.

        Returns:
            Steering leads only. Never evidence.
        """

        return await self.aquery_data_structured(
            query=query,
            mode="global",
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )


class LightRagRuntimeAdapterContext(
    AbstractAsyncContextManager[LightRagRuntimeAdapter]
):
    """Async context manager that always finalizes runtime storages."""

    def __init__(self, adapter: LightRagRuntimeAdapter) -> None:
        """Bind one runtime adapter.

        Args:
            adapter: Attached runtime adapter.
        """

        self._adapter = adapter

    async def __aenter__(self) -> LightRagRuntimeAdapter:
        """Return the bound adapter.

        Returns:
            Attached adapter.
        """

        return self._adapter

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Finalize storages even when the caller failed.

        Args:
            exc_type: Exception type if any.
            exc: Exception instance if any.
            traceback: Traceback if any.
        """

        del exc_type, exc, traceback
        await self._adapter.finalize()


async def open_runtime_lightrag_adapter(
    *,
    dsn: SecretStr,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    working_dir: Path | None = None,
    workspace: str = DEFAULT_GRAPH_WORKSPACE,
    connection: psycopg.Connection,
    max_connections: int = RUNTIME_POSTGRES_MAX_CONNECTIONS,
    reviewed: SchemaFingerprint | None = None,
    mock_model_mode: bool = True,
) -> LightRagRuntimeAdapter:
    """Attach LightRAG to the migrated private schema without DDL.

    Args:
        dsn: Runtime ``LIGHTRAG_DB_URL``. Must not be the schema-admin secret.
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        working_dir: Optional vendor working directory.
        workspace: Constructor workspace. Env override is rejected.
        connection: psycopg connection used for fingerprinting.
        max_connections: Pool cap. Must stay at most 4.
        reviewed: Optional reviewed fingerprint. Table list is always checked.
        mock_model_mode: When true, use the mock cosine floor ``-1.0``.

    Returns:
        Attached adapter. Caller must ``finalize``.

    Raises:
        LightRagAdapterError: On env override, search_path, fingerprint,
            AGE, public-object, or pool-cap failure.

    Side Effects:
        Sets ``POSTGRES_*`` env, opens the process-wide ClientManager pool,
        and calls vendor ``initialize_storages`` under DDL-skip patches.
        Does not call schema-admin bootstrap.
    """

    params = parse_lightrag_db_url(dsn)
    apply_lightrag_postgres_env(
        params,
        max_connections=max_connections,
        server_settings=runtime_server_settings(),
    )
    resolved_dir = working_dir or Path(tempfile.mkdtemp(prefix="smart-rag-lightrag-"))
    rag, callbacks = await construct_lightrag_engine(
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
        working_dir=resolved_dir,
        workspace=workspace,
        cosine_better_than_threshold=cosine_threshold_for_mode(
            mock_model_mode=mock_model_mode
        ),
    )
    async with runtime_attach_without_ddl():
        await rag.initialize_storages()
    fingerprint = capture_schema_fingerprint(connection, LIGHTRAG_SCHEMA_NAME)
    try:
        assert_private_schema_postconditions(fingerprint, connection=connection)
        if reviewed is not None:
            assert_fingerprint_matches(fingerprint, reviewed)
    except Exception:
        await rag.finalize_storages()
        await reset_process_client_manager()
        raise
    adapter = LightRagRuntimeAdapter(
        rag=rag,
        callbacks=callbacks,
        workspace=workspace,
        working_dir=resolved_dir,
        fingerprint=fingerprint,
        max_connections=max_connections,
    )
    try:
        role_name = await adapter.current_database_user()
        if role_name != LIGHTRAG_RUNTIME_ROLE:
            raise LightRagAdapterError(f"runtime_role_mismatch:{role_name}")
    except Exception:
        await adapter.finalize()
        raise
    return adapter


async def open_runtime_adapter_from_optional_url(
    *,
    dsn: SecretStr | None,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    connection: psycopg.Connection,
    working_dir: Path | None = None,
    workspace: str = DEFAULT_GRAPH_WORKSPACE,
    mock_model_mode: bool = True,
) -> LightRagRuntimeAdapter | None:
    """Open the runtime adapter when ``LIGHTRAG_DB_URL`` is configured.

    Args:
        dsn: Optional runtime DSN from Backend/Worker settings.
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        connection: Fingerprint connection.
        working_dir: Optional vendor working directory.
        workspace: Constructor workspace.
        mock_model_mode: When true, use the mock cosine floor ``-1.0``.

    Returns:
        Attached adapter, or ``None`` when the DSN is unset (honest idle).
    """

    if dsn is None:
        return None
    return await open_runtime_lightrag_adapter(
        dsn=dsn,
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
        working_dir=working_dir,
        workspace=workspace,
        connection=connection,
        mock_model_mode=mock_model_mode,
    )


def cosine_threshold_for_mode(*, mock_model_mode: bool) -> float:
    """Return the vector floor for this process model mode.

    Mock hash vectors have no semantic neighborhood, so qualification and
    local mock attach use ``-1.0``. Real embeddings keep the production
    ``0.2`` pin. Packet 3 must not copy ``-1.0`` into a live Graph setting.

    Args:
        mock_model_mode: ``SharedSettings.mock_model_mode``.

    Returns:
        Cosine floor passed to vendor ``EmbeddingFunc`` / LightRAG construct.
    """

    if mock_model_mode:
        return QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD
    return RUNTIME_COSINE_BETTER_THAN_THRESHOLD


def adapter_mode_label(dsn: SecretStr | None) -> Literal["attached", "unconfigured"]:
    """Return the honest runtime adapter mode.

    Args:
        dsn: Optional ``LIGHTRAG_DB_URL``.

    Returns:
        ``attached`` when a DSN is present, otherwise ``unconfigured``.
    """

    return "unconfigured" if dsn is None else "attached"


async def bind_process_runtime_adapter(
    *,
    dsn: SecretStr | None,
    settings: SharedSettings,
    workspace: str = DEFAULT_GRAPH_WORKSPACE,
    working_dir: Path | None = None,
) -> LightRagRuntimeAdapter | None:
    """Open the runtime adapter for API/worker lifespan when a DSN is set.

    Args:
        dsn: Optional ``LIGHTRAG_DB_URL`` from Backend or Worker settings.
        settings: Shared deployable settings used to build mock/real gateways.
        workspace: Constructor workspace.
        working_dir: Optional vendor working directory.

    Returns:
        Attached adapter, or ``None`` when the DSN is unset.

    Raises:
        LightRagAdapterError: If the DSN is set and attach fails.

    Side Effects:
        Opens a short-lived psycopg fingerprint connection. Does not call
        schema-admin ``initialize_storages``.
    """

    if dsn is None:
        return None
    embedding_gateway = create_embedding_gateway(settings)
    model_gateway = create_model_gateway(settings)
    connection = psycopg.connect(dsn.get_secret_value())
    try:
        return await open_runtime_lightrag_adapter(
            dsn=dsn,
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=working_dir,
            workspace=workspace,
            connection=connection,
            mock_model_mode=settings.mock_model_mode,
        )
    finally:
        connection.close()
