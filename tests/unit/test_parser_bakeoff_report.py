"""Unit tests for git-safe bake-off reports."""

from __future__ import annotations

from uuid import uuid4

import pytest
from smart_rag_core.evaluation.parser_bakeoff.metrics import compare_reports
from smart_rag_core.evaluation.parser_bakeoff.models import (
    LaneAgentScore,
    LaneIdentity,
    LaneRetrieveScore,
)
from smart_rag_core.evaluation.parser_bakeoff.report import (
    assert_report_is_safe,
    render_markdown,
)


def test_report_schema_and_markdown_omit_private_text() -> None:
    """Comparison JSON/Markdown must not include questions, answers, or secrets."""

    current = LaneIdentity(
        lane_id="current",
        parser_version="parser_v1",
        cleaning_version="cleaning_v1",
        locator_available=True,
        ingest_document_id=uuid4(),
        ingest_version_id=uuid4(),
    )
    anydoc = LaneIdentity(
        lane_id="anydoc_local",
        parser_version="anydoc_pdf_0_2_4_local",
        cleaning_version="anydoc_markdown_0_2_4",
        locator_available=False,
        ingest_document_id=uuid4(),
        ingest_version_id=uuid4(),
    )
    report = compare_reports(
        run_id="run-safe",
        source_sha256="ab" * 32,
        source_basename="book.pdf",
        current_identity=current,
        anydoc_identity=anydoc,
        current_chunk=None,
        anydoc_chunk=None,
        current_retrieve=(
            LaneRetrieveScore(
                case_id="case-0010",
                recall_hit_at_10=True,
                locator_ok=True,
                locator_available=True,
                refusal_ok=True,
            ),
        ),
        anydoc_retrieve=(
            LaneRetrieveScore(
                case_id="case-0010",
                recall_hit_at_10=True,
                locator_ok=False,
                locator_available=False,
                refusal_ok=True,
            ),
        ),
        current_agent=(
            LaneAgentScore(
                case_id="case-0010",
                citation_correctness=1.0,
                citation_completeness=1.0,
                fact_completeness=1.0,
                faithfulness=0.9,
                judge_status="complete",
                refusal_ok=True,
            ),
        ),
        anydoc_agent=(
            LaneAgentScore(
                case_id="case-0010",
                citation_correctness=1.0,
                citation_completeness=1.0,
                fact_completeness=1.0,
                faithfulness=0.9,
                judge_status="complete",
                refusal_ok=True,
            ),
        ),
        mapping_review_count=0,
        infra_mismatch=False,
    )
    dumped = report.model_dump_json()
    markdown = render_markdown(report)
    assert report.schema_version == "parser-bakeoff-v1"
    assert report.generalization_claim is False
    assert report.holdout_opened is False
    assert report.secrets_emitted is False
    assert report.source_text_emitted is False
    assert "What is" not in dumped
    assert "OPENAI_API_KEY" not in dumped
    assert "sk-" not in dumped
    assert "atomic_facts" not in markdown
    assert "classification" in markdown
    assert_report_is_safe(markdown)


def test_report_secret_and_source_sentinels() -> None:
    """Leak sentinels must reject credentials and source-like dumps."""

    with pytest.raises(ValueError, match="report_secret_leak"):
        assert_report_is_safe("key=sk-abcdefghijklmnopqrstuvwxyz")
    with pytest.raises(ValueError, match="report_secret_leak"):
        assert_report_is_safe("FIRECRAWL_API_KEY=secret")
    with pytest.raises(ValueError, match="report_source_text_risk"):
        assert_report_is_safe("```\naccording to chapter one\n```")
