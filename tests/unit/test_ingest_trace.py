"""Unit tests for redacted ingest LangSmith parent runs."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, cast
from uuid import uuid4

import langsmith
from smart_rag_core.observability.ingest_trace import (
    INGEST_RUN_GRAPH,
    INGEST_RUN_INDEX,
    ingest_content_class_for_job,
    ingest_run_name_for_job_kind,
    ingest_run_trace_metadata,
    invoke_traced_ingestion,
)
from smart_rag_core.observability.langsmith_tracing import (
    payload_contains_forbidden_text,
    short_content_hash,
)
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.settings import AgentSettings, SharedSettings

from tests.support.langsmith import RecordingLangSmithClient
from tests.unit.typed_attrs import module_attr

CANARY_PASSAGE = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"
CANARY_TOKEN = "sk-canarysecretFORBID123456"  # noqa: S105 - inert leak canary


def _tracing_context(
    *, enabled: bool, client: object
) -> AbstractContextManager[object]:
    """Return LangSmith ``tracing_context`` with a known callable type.

    Args:
        enabled: Whether tracing is enabled for the block.
        client: Recording client used by the unit tests.

    Returns:
        Context manager from ``langsmith.tracing_context``.
    """

    factory = cast(
        Callable[..., AbstractContextManager[object]],
        module_attr(langsmith, "tracing_context"),
    )
    return factory(enabled=enabled, client=client)


def test_job_kind_maps_to_ingest_parent_names() -> None:
    """Scan, index, and LightRAG jobs open the planned parent names."""

    assert ingest_run_name_for_job_kind("scan_promote") == "ingestion.scan"
    assert ingest_run_name_for_job_kind("hybrid_index") == INGEST_RUN_INDEX
    assert ingest_run_name_for_job_kind("lightrag_index") == INGEST_RUN_GRAPH
    assert ingest_run_name_for_job_kind("query_memory_reaper") is None


def test_ingest_parent_includes_job_id_and_omits_canary() -> None:
    """Enabled tracing records ``ingestion.index`` with ``job_id`` and no passage."""

    recorder = RecordingLangSmithClient()
    job_id = uuid4()
    document_id = uuid4()
    settings = AgentSettings()
    captured: dict[str, str] = {}

    def _thunk() -> dict[str, str]:
        """Return a result that would leak if process_outputs copied detail.

        Returns:
            Mapping including a canary detail string.
        """

        captured["ran"] = "1"
        return {"status": "indexed", "detail": CANARY_PASSAGE}

    with _tracing_context(enabled=True, client=recorder):
        result = invoke_traced_ingestion(
            _thunk,
            settings=settings,
            job_id=job_id,
            run_name=INGEST_RUN_INDEX,
            document_id=document_id,
            version_id=None,
        )
    assert result["status"] == "indexed"
    assert captured["ran"] == "1"
    names = [item["name"] for item in recorder.created]
    assert INGEST_RUN_INDEX in names
    parent = next(item for item in recorder.created if item["name"] == INGEST_RUN_INDEX)
    inputs = cast(dict[str, Any], parent["inputs"])
    assert inputs["job_id"] == str(job_id)
    assert inputs["graph_name"] == INGEST_RUN_INDEX
    assert inputs["document_id_sha256"] == short_content_hash(str(document_id))
    serialized = json.dumps(recorder.created + recorder.updated, default=str)
    assert CANARY_PASSAGE not in serialized
    assert CANARY_TOKEN not in serialized
    assert str(document_id) not in serialized
    assert not payload_contains_forbidden_text(
        recorder.created, CANARY_PASSAGE, CANARY_TOKEN
    )


def test_ingest_metadata_hashes_ids_only() -> None:
    """Metadata export never copies canary text or raw document UUIDs."""

    job_id = uuid4()
    document_id = uuid4()
    payload = ingest_run_trace_metadata(
        job_id=job_id,
        graph_name=INGEST_RUN_GRAPH,
        document_id=document_id,
        version_id=None,
    )
    rendered = json.dumps(payload)
    assert payload["job_id"] == str(job_id)
    assert payload["graph_name"] == INGEST_RUN_GRAPH
    assert str(document_id) not in rendered
    assert CANARY_PASSAGE not in rendered


def test_real_company_job_is_not_synthetic_under_local_settings() -> None:
    """Local env never reclassifies an authoritative real-company job."""

    settings = SharedSettings()
    assert (
        ingest_content_class_for_job(ContentClass.REAL_COMPANY, settings=settings)
        is ContentClass.REAL_COMPANY
    )
