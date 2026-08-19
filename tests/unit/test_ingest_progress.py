"""Unit tests for ingest TTY progress prefixes."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from smart_rag_core.observability.ingest_progress import (
    ingest_progress_message_is_safe,
    log_ingest_progress,
)
from smart_rag_core.schema.enums import JobErrorCategory

CANARY_PASSAGE = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"


def test_hybrid_and_graph_prefixes_are_present(caplog: pytest.LogCaptureFixture) -> None:
    """Fixture job kinds emit ``[hybrid]`` and ``[graph]`` without canary text."""

    job_id = uuid4()
    with caplog.at_level(logging.INFO, logger="smart_rag.ingest_progress"):
        log_ingest_progress(
            "hybrid",
            "embed_batch",
            job_id,
            batch_index=1,
            batch_count=13,
            chunks=64,
            filename=CANARY_PASSAGE,
        )
        log_ingest_progress("graph", "extract_batch", job_id, extract_calls=3)
        log_ingest_progress(
            "hybrid",
            "hybrid_index_failed",
            job_id,
            error_category=JobErrorCategory.VALIDATION,
            reason_code="job_failed",
        )
    messages = [record.getMessage() for record in caplog.records]
    assert any(item.startswith("[hybrid]") for item in messages)
    assert any(item.startswith("[graph]") for item in messages)
    rendered = "\n".join(messages)
    assert str(job_id) in rendered
    assert "embed_batch" in rendered
    assert "extract_batch" in rendered
    assert CANARY_PASSAGE not in rendered
    assert ingest_progress_message_is_safe(rendered, needles=(CANARY_PASSAGE,))


def test_invalid_pipeline_and_stage_are_rejected() -> None:
    """Unknown pipelines or unsafe stage tokens fail closed."""

    job_id = uuid4()
    with pytest.raises(ValueError, match="pipeline"):
        log_ingest_progress("worker", "scan", job_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stage"):
        log_ingest_progress("hybrid", CANARY_PASSAGE, job_id)
