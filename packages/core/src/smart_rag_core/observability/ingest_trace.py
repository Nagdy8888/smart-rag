"""Redacted LangSmith parent runs for laptop worker ingest jobs.

Query SSE already opens a parent metadata payload. Ingest jobs historically
invoked graphs with no ``job_id`` correlation and no parent run, so a demo
upload could succeed in Supabase and stay invisible in LangSmith. This module
binds correlation, gates export, and wraps scan/parse/index/graph invokes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from typing import Any, TypeVar, cast
from uuid import UUID

import langsmith

from smart_rag_core.observability.governance_gate import (
    assert_langsmith_export_permitted,
)
from smart_rag_core.observability.langsmith_tracing import (
    short_content_hash,
    traceable,
    tracing_is_enabled,
)
from smart_rag_core.observability.logging import (
    correlation_context,
    current_correlation_ids,
)
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.settings import SharedSettings

T = TypeVar("T")

INGEST_RUN_SCAN = "ingestion.scan"
INGEST_RUN_PARSE = "ingestion.parse"
INGEST_RUN_INDEX = "ingestion.index"
INGEST_RUN_GRAPH = "ingestion.graph"
INGEST_RUN_CRAWL = "ingestion.crawl"
INGEST_RUN_PROBE = "ingestion.probe"

_JOB_KIND_RUN_NAMES: Mapping[str, str] = {
    "scan_promote": INGEST_RUN_SCAN,
    "hybrid_index": INGEST_RUN_INDEX,
    "website_crawl": INGEST_RUN_CRAWL,
    "probe": INGEST_RUN_PROBE,
    "lightrag_index": INGEST_RUN_GRAPH,
}

_PARENT_INPUT_KEYS = frozenset(
    {"job_id", "graph_name", "document_id_sha256", "version_id_sha256"}
)


def ingest_run_name_for_job_kind(job_kind: str) -> str | None:
    """Return the LangSmith parent name for one worker job kind.

    Args:
        job_kind: Durable ingestion or LightRAG job kind.

    Returns:
        Parent run name, or ``None`` when the kind is maintenance and must
        not open an ingest tree.
    """

    return _JOB_KIND_RUN_NAMES.get(job_kind)


def hashed_optional_id(value: UUID | str | None) -> str | None:
    """Hash a document or version id for export. Never copy the raw UUID.

    Args:
        value: Canonical id, or ``None`` when the job has no row yet.

    Returns:
        16-hex SHA-256 prefix, or ``None``.
    """

    if value is None:
        return None
    return short_content_hash(str(value))


def ingest_run_trace_metadata(
    *,
    job_id: UUID | str,
    graph_name: str,
    document_id: UUID | str | None = None,
    version_id: UUID | str | None = None,
) -> dict[str, Any]:
    """Build ingest parent metadata with hashes and job id only.

    Args:
        job_id: Claimed job identifier (exported as the job id, not a secret).
        graph_name: Parent run name such as ``ingestion.index``.
        document_id: Optional document id hashed before export.
        version_id: Optional version id hashed before export.

    Returns:
        Exportable metadata. Filenames, bytes, prompts, and embeddings are
        omitted.
    """

    payload: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "job_id": str(job_id),
        "graph_name": graph_name,
    }
    document_hash = hashed_optional_id(document_id)
    version_hash = hashed_optional_id(version_id)
    if document_hash is not None:
        payload["document_id_sha256"] = document_hash
    if version_hash is not None:
        payload["version_id_sha256"] = version_hash
    return payload


def redact_ingest_parent_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Keep job id and hashes; drop any unexpected traceable arguments.

    Args:
        inputs: Traceable kwargs. Unknown keys are ignored so closures cannot
            export filenames or plot text.

    Returns:
        Exportable parent inputs plus correlation ids.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    for key in _PARENT_INPUT_KEYS:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    return payload


def redact_ingest_parent_outputs(outputs: object) -> dict[str, Any]:
    """Export a status token only. Graph ``detail`` strings are dropped.

    Args:
        outputs: Traceable return wrapper or the raw thunk result.

    Returns:
        ``status`` when it is a short token; otherwise ``completed``.
    """

    raw: object = outputs
    if isinstance(outputs, Mapping):
        mapped = dict(outputs)
        raw = mapped.get("output", mapped)
    if isinstance(raw, Mapping):
        status = raw.get("status")
        if isinstance(status, str) and 0 < len(status) <= 64 and status.isascii():
            token = status.replace("-", "_")
            if token.replace("_", "").isalnum():
                return {"status": token}
    return {"completed": True}


def ingest_content_class_for_settings(settings: SharedSettings) -> ContentClass:
    """Choose the LangSmith content class for one worker process.

    Args:
        settings: Validated worker or shared settings.

    Returns:
        ``SYNTHETIC`` for mock mode or the local unsigned waiver; otherwise
        ``REAL_COMPANY``.
    """

    if settings.mock_model_mode or settings.allows_unsigned_local_live_providers():
        return ContentClass.SYNTHETIC
    return ContentClass.REAL_COMPANY


def _ingest_tracing_scope(*, enabled: bool) -> AbstractContextManager[object]:
    """Open ``langsmith.tracing_context`` when export is on and no scope exists.

    Args:
        enabled: Whether this process should export ingest parent runs.

    Returns:
        An enabled tracing context when the SDK is not already tracing;
        otherwise a no-op so unit tests keep their recording client.
    """

    if not enabled or tracing_is_enabled():
        return nullcontext()
    factory = cast(
        Callable[..., AbstractContextManager[object]],
        langsmith.tracing_context,
    )
    return factory(enabled=True)


def assert_ingest_langsmith_gate(settings: SharedSettings) -> None:
    """Fail closed before opening an ingest parent run.

    Args:
        settings: Validated process settings.

    Raises:
        ExternalFlowBlockedError: When real-company export is unverified and
            the local waiver does not apply.

    Side Effects:
        None. Hide I/O remains forced by ``configure_langsmith``.
    """

    assert_langsmith_export_permitted(
        tracing_enabled=settings.langsmith_tracing,
        content_class=ingest_content_class_for_settings(settings),
        provider_settings_verified=settings.subprocessor_matrix_verified,
        local_unsigned_waiver=settings.allows_unsigned_local_live_providers(),
    )


def invoke_traced_ingestion(
    thunk: Callable[[], T],
    *,
    settings: SharedSettings,
    job_id: UUID | str,
    run_name: str,
    document_id: UUID | str | None = None,
    version_id: UUID | str | None = None,
) -> T:
    """Bind ``job_id`` and wrap ``thunk`` in a redacted LangSmith parent run.

    Args:
        thunk: Graph invoke, parse, or LightRAG index call. Must not log
            source text.
        settings: Process settings used for the export gate.
        job_id: Claimed job identifier.
        run_name: Parent name such as ``ingestion.index``.
        document_id: Optional document id hashed into metadata.
        version_id: Optional version id hashed into metadata.

    Returns:
        The thunk result.

    Raises:
        ExternalFlowBlockedError: When export is not permitted.

    Side Effects:
        Sets correlation context. Creates a LangSmith chain run when tracing
        is enabled. Child gateway spans nest under this parent.
    """

    assert_ingest_langsmith_gate(settings)
    extra = ingest_run_trace_metadata(
        job_id=job_id,
        graph_name=run_name,
        document_id=document_id,
        version_id=version_id,
    )
    with correlation_context(job_id=str(job_id)):
        tracing_on = bool(settings.langsmith_tracing or tracing_is_enabled())
        if not tracing_on:
            return thunk()

        @traceable(
            name=run_name,
            run_type="chain",
            process_inputs=redact_ingest_parent_inputs,
            process_outputs=redact_ingest_parent_outputs,
            metadata=extra,
        )
        def _parent(
            job_id: str,
            graph_name: str,
            document_id_sha256: str | None = None,
            version_id_sha256: str | None = None,
        ) -> T:
            """Redacted ingest parent. Arguments are hashes and ids only.

            Args:
                job_id: Claimed job id.
                graph_name: Parent run name.
                document_id_sha256: Optional hashed document id.
                version_id_sha256: Optional hashed version id.

            Returns:
                Thunk result.
            """

            del job_id, graph_name, document_id_sha256, version_id_sha256
            return thunk()

        with _ingest_tracing_scope(enabled=True):
            return _parent(
                job_id=str(job_id),
                graph_name=run_name,
                document_id_sha256=extra.get("document_id_sha256"),
                version_id_sha256=extra.get("version_id_sha256"),
            )


def nest_traced_ingestion(
    thunk: Callable[[], T],
    *,
    job_id: UUID | str,
    run_name: str,
    document_id: UUID | str | None = None,
    version_id: UUID | str | None = None,
) -> T:
    """Open a nested redacted ingest run when tracing is already enabled.

    Args:
        thunk: Parse or similar inner step.
        job_id: Claimed job identifier.
        run_name: Nested name such as ``ingestion.parse``.
        document_id: Optional document id hashed into metadata.
        version_id: Optional version id hashed into metadata.

    Returns:
        The thunk result.

    Side Effects:
        Creates a LangSmith chain run only when the SDK tracing context is
        already enabled by the worker parent. Does not re-check the matrix.
    """

    extra = ingest_run_trace_metadata(
        job_id=job_id,
        graph_name=run_name,
        document_id=document_id,
        version_id=version_id,
    )
    if not tracing_is_enabled():
        return thunk()

    @traceable(
        name=run_name,
        run_type="chain",
        process_inputs=redact_ingest_parent_inputs,
        process_outputs=redact_ingest_parent_outputs,
        metadata=extra,
    )
    def _parent(
        job_id: str,
        graph_name: str,
        document_id_sha256: str | None = None,
        version_id_sha256: str | None = None,
    ) -> T:
        """Redacted nested ingest run.

        Args:
            job_id: Claimed job id.
            graph_name: Nested run name.
            document_id_sha256: Optional hashed document id.
            version_id_sha256: Optional hashed version id.

        Returns:
            Thunk result.
        """

        del job_id, graph_name, document_id_sha256, version_id_sha256
        return thunk()

    return _parent(
        job_id=str(job_id),
        graph_name=run_name,
        document_id_sha256=extra.get("document_id_sha256"),
        version_id_sha256=extra.get("version_id_sha256"),
    )
