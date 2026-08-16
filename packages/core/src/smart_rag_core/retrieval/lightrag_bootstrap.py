"""Protected LightRAG schema bootstrap using schema-admin credentials.

This module may import LightRAG. The ops CLI must call these functions
instead of importing vendor classes. Runtime API/worker processes must not
call ``bootstrap_lightrag_schema``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pydantic import SecretStr

from smart_rag_core.gateways.embedding import EmbeddingGateway
from smart_rag_core.gateways.model import ModelGateway
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_RELEASE_COMMIT,
    LIGHTRAG_SEARCH_PATH,
    QUALIFICATION_POSTGRES_MAX_CONNECTIONS,
)
from smart_rag_core.retrieval.lightrag_adapter import (
    LIGHTRAG_SCHEMA_NAME,
    LightRagAdapterError,
    ReviewedSchemaManifest,
    apply_lightrag_postgres_env,
    assert_private_schema_postconditions,
    bootstrap_server_settings,
    construct_lightrag_engine,
    parse_lightrag_db_url,
    reviewed_schema_manifest,
)
from smart_rag_core.retrieval.lightrag_qualification import (
    QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD,
    LightRagPostgresParams,
    QualificationWarnings,
    SchemaFingerprint,
    capture_schema_fingerprint,
    fingerprint_drift,
    initialize_storages_capturing_warnings,
    is_fatal_initialize_warning,
    reset_process_client_manager,
)


class LightRagBootstrapError(LightRagAdapterError):
    """Raised when protected schema bootstrap fails closed."""


@dataclass(frozen=True, slots=True)
class LightRagBootstrapReport:
    """Outcome of one protected ``initialize_storages`` run.

    Attributes:
        fingerprint: Private-schema fingerprint after initialize.
        warnings: Captured Python and log warnings.
        workspace: Constructor workspace used for this run.
        search_path: Controlled search_path applied to vendor env.
        fingerprint_sha256: Canonical SHA-256 of table names.
        repeated: True when this report is from a repeat initialize.
    """

    fingerprint: SchemaFingerprint
    warnings: QualificationWarnings
    workspace: str
    search_path: str
    fingerprint_sha256: str
    repeated: bool = False


def fingerprint_table_digest(fingerprint: SchemaFingerprint) -> str:
    """Return a stable digest of reviewed private-schema table names.

    Args:
        fingerprint: Captured fingerprint.

    Returns:
        Lowercase hex SHA-256 of the ordered table tuple.
    """

    payload = json.dumps(list(fingerprint.tables), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _raise_on_fatal_warnings(warnings: QualificationWarnings) -> None:
    """Fail closed when initialize warnings show incomplete migration.

    Args:
        warnings: Captured Python and log warnings.

    Raises:
        LightRagBootstrapError: If any warning is fatal.
    """

    fatal = tuple(
        item
        for item in (*warnings.python_warnings, *warnings.log_warnings)
        if is_fatal_initialize_warning(item)
    )
    if fatal:
        raise LightRagBootstrapError(f"initialize_warning:{fatal[0]}")


async def bootstrap_lightrag_schema(
    *,
    schema_admin_dsn: SecretStr,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    working_dir: Path,
    connection: psycopg.Connection,
    workspace: str = DEFAULT_GRAPH_WORKSPACE,
    max_connections: int = QUALIFICATION_POSTGRES_MAX_CONNECTIONS,
    reviewed: ReviewedSchemaManifest | None = None,
) -> LightRagBootstrapReport:
    """Run protected ``initialize_storages`` and capture fingerprint/warnings.

    Args:
        schema_admin_dsn: Isolated schema-admin DSN. Never a runtime setting.
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        working_dir: Vendor working directory.
        connection: psycopg connection for fingerprinting (same database).
        workspace: Constructor workspace.
        max_connections: Pool cap during bootstrap. Must stay 2-4.
        reviewed: Expected table manifest. Defaults to the pin manifest.

    Returns:
        Bootstrap report. Connections are finalized before return.

    Raises:
        LightRagBootstrapError: On fatal warnings, AGE, public objects, or
            fingerprint table drift.

    Side Effects:
        Applies ``POSTGRES_*`` env, runs vendor ``initialize_storages`` with
        schema-admin privileges, then ``finalize_storages``.
    """

    params = parse_lightrag_db_url(schema_admin_dsn)
    return await _run_bootstrap(
        params=params,
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
        working_dir=working_dir,
        connection=connection,
        workspace=workspace,
        max_connections=max_connections,
        reviewed=reviewed or reviewed_schema_manifest(),
        repeated=False,
    )


async def repeat_bootstrap_lightrag_schema(
    *,
    schema_admin_dsn: SecretStr,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    working_dir: Path,
    connection: psycopg.Connection,
    first: LightRagBootstrapReport,
    workspace: str = DEFAULT_GRAPH_WORKSPACE,
    max_connections: int = QUALIFICATION_POSTGRES_MAX_CONNECTIONS,
) -> LightRagBootstrapReport:
    """Re-run initialize and require a stable fingerprint.

    Args:
        schema_admin_dsn: Isolated schema-admin DSN.
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        working_dir: Vendor working directory.
        connection: Fingerprint connection.
        first: Report from the first bootstrap.
        workspace: Constructor workspace.
        max_connections: Pool cap.

    Returns:
        Second bootstrap report.

    Raises:
        LightRagBootstrapError: If fingerprints drift or warnings are fatal.
    """

    params = parse_lightrag_db_url(schema_admin_dsn)
    second = await _run_bootstrap(
        params=params,
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
        working_dir=working_dir,
        connection=connection,
        workspace=workspace,
        max_connections=max_connections,
        reviewed=reviewed_schema_manifest(),
        repeated=True,
    )
    drift = fingerprint_drift(first.fingerprint, second.fingerprint)
    if drift:
        raise LightRagBootstrapError(f"repeat_bootstrap_fingerprint_drift:{drift[0]}")
    return second


async def _run_bootstrap(
    *,
    params: LightRagPostgresParams,
    embedding_gateway: EmbeddingGateway,
    model_gateway: ModelGateway,
    working_dir: Path,
    connection: psycopg.Connection,
    workspace: str,
    max_connections: int,
    reviewed: ReviewedSchemaManifest,
    repeated: bool,
) -> LightRagBootstrapReport:
    """Execute one initialize/finalize cycle with postconditions.

    Args:
        params: Parsed schema-admin connection fields.
        embedding_gateway: Shared embedding gateway.
        model_gateway: Shared model gateway.
        working_dir: Vendor working directory.
        connection: Fingerprint connection.
        workspace: Constructor workspace.
        max_connections: Pool cap.
        reviewed: Expected table manifest.
        repeated: Whether this is a second initialize.

    Returns:
        Bootstrap report after finalize.

    Raises:
        LightRagBootstrapError: On fatal warnings or postcondition failure.
    """

    apply_lightrag_postgres_env(
        params,
        max_connections=max_connections,
        server_settings=bootstrap_server_settings(),
    )
    await reset_process_client_manager()
    rag, _callbacks = await construct_lightrag_engine(
        embedding_gateway=embedding_gateway,
        model_gateway=model_gateway,
        working_dir=working_dir,
        workspace=workspace,
        cosine_better_than_threshold=QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD,
    )
    try:
        python_warnings, log_warnings = await initialize_storages_capturing_warnings(
            rag
        )
        warnings = QualificationWarnings(
            python_warnings=python_warnings,
            log_warnings=log_warnings,
        )
        _raise_on_fatal_warnings(warnings)
        fingerprint = capture_schema_fingerprint(connection, LIGHTRAG_SCHEMA_NAME)
        assert_private_schema_postconditions(
            fingerprint, connection=connection, manifest=reviewed
        )
    except LightRagAdapterError as exc:
        await rag.finalize_storages()
        await reset_process_client_manager()
        raise LightRagBootstrapError(str(exc)) from exc
    except Exception:
        await rag.finalize_storages()
        await reset_process_client_manager()
        raise
    await rag.finalize_storages()
    await reset_process_client_manager()
    return LightRagBootstrapReport(
        fingerprint=fingerprint,
        warnings=warnings,
        workspace=workspace,
        search_path=LIGHTRAG_SEARCH_PATH,
        fingerprint_sha256=fingerprint_table_digest(fingerprint),
        repeated=repeated,
    )


def persist_capture_status(
    connection: psycopg.Connection,
    report: LightRagBootstrapReport,
) -> None:
    """Record pin version and capture digest on ``schema_capture_status``.

    Args:
        connection: Schema-admin psycopg connection.
        report: Successful bootstrap report.

    Side Effects:
        Updates ``lightrag.schema_capture_status``. Does not log secrets.
    """

    warning_payload = json.dumps(
        {
            "python_warnings": list(report.warnings.python_warnings),
            "log_warnings": list(report.warnings.log_warnings),
        }
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE lightrag.schema_capture_status
            SET
              lightrag_version = %s,
              capture_status = 'captured',
              pin_commit = %s,
              embedding_model = %s,
              embedding_dimensions = %s,
              fingerprint_sha256 = %s,
              search_path = %s,
              warning_report = %s::jsonb,
              notes = 'Phase 5 Packet 2 protected initialize_storages capture.',
              captured_at = timezone('utc', now())
            WHERE capture_status IN ('deferred', 'captured')
               OR lightrag_version IN ('deferred', '1.5.6')
            """,
            (
                LIGHTRAG_PINNED_VERSION,
                LIGHTRAG_RELEASE_COMMIT,
                EMBEDDING_MODEL,
                EMBEDDING_DIMENSIONS,
                report.fingerprint_sha256,
                LIGHTRAG_SEARCH_PATH,
                warning_payload,
            ),
        )
    connection.commit()
