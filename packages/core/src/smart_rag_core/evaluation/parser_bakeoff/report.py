"""Git-safe JSON and Markdown comparison reports."""

from __future__ import annotations

import re

from smart_rag_core.evaluation.parser_bakeoff.models import ComparisonReport

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|FIRECRAWL_API_KEY|OPENAI_API_KEY|Bearer\s+\S+)",
    re.IGNORECASE,
)


def assert_report_is_safe(text: str) -> None:
    """Reject reports that leak credentials or look like source dumps.

    Args:
        text: Report body.

    Raises:
        ValueError: When a sentinel leak is detected.
    """

    if _SECRET_PATTERN.search(text):
        raise ValueError("report_secret_leak")
    lowered = text.lower()
    if "```" in text and "according to" in lowered:
        raise ValueError("report_source_text_risk")


def render_markdown(report: ComparisonReport) -> str:
    """Render the side-by-side Markdown report.

    Args:
        report: Frozen comparison report.

    Returns:
        Markdown without questions, answers, excerpts, or secrets.
    """

    rows = [
        "| Metric | current | anydoc_local | delta | winner |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.paired_metrics:
        rows.append(
            "| "
            + " | ".join(
                (
                    item.name,
                    _fmt(item.current),
                    _fmt(item.anydoc_local),
                    _fmt(item.delta),
                    item.winner,
                )
            )
            + " |"
        )
    current_pages = (
        report.current_chunk.pages_processed if report.current_chunk else None
    )
    anydoc_pages = report.anydoc_chunk.pages_processed if report.anydoc_chunk else None
    body = "\n".join(
        (
            "# Isolated PDF parser bake-off",
            "",
            *rows,
            "",
            "## 1. Scope",
            "",
            f"- run_id: `{report.run_id}`",
            f"- source_basename: `{report.source_basename}`",
            f"- source_sha256: `{report.source_sha256}`",
            f"- generalization_claim: `{report.generalization_claim}`",
            f"- holdout_opened: `{report.holdout_opened}`",
            "",
            "## 2. Fixed controls",
            "",
            f"- current parser: `{report.current.parser_version}`",
            f"- anydoc parser: `{report.anydoc_local.parser_version}`",
            f"- current locator_available: `{report.current.locator_available}`",
            f"- anydoc locator_available: `{report.anydoc_local.locator_available}`",
            f"- experimental_only: `{report.experimental_only}`",
            "",
            "## 3. Parse and chunk",
            "",
            f"- current chunks: `{_fmt(report.current_chunk.chunk_count if report.current_chunk else None)}`",
            f"- anydoc chunks: `{_fmt(report.anydoc_chunk.chunk_count if report.anydoc_chunk else None)}`",
            f"- current pages_processed: `{_fmt(current_pages)}`",
            f"- anydoc pages_processed: `{_fmt(anydoc_pages)}` (unavailable is expected)",
            "",
            "## 4. Retrieval",
            "",
            "- See the metric table for Recall@10 and first-evidence latency.",
            "",
            "## 5. Answer and citations",
            "",
            "- See citation_correctness and judge_faithfulness in the table.",
            f"- unscored_count: `{report.unscored_count}`",
            "",
            "## 6. Latency and cost",
            "",
            f"- current_cost_usd: `{_fmt(report.current_cost_usd)}`",
            f"- anydoc_cost_usd: `{_fmt(report.anydoc_cost_usd)}`",
            "",
            "## 7. Provenance and security",
            "",
            f"- acl_leaks: `{report.acl_leaks}`",
            f"- secrets_emitted: `{report.secrets_emitted}`",
            f"- source_text_emitted: `{report.source_text_emitted}`",
            "",
            "## 8. Failures and unscored cases",
            "",
            f"- blockers: `{','.join(report.blockers) or 'none'}`",
            f"- mapping_review_count: `{report.mapping_review_count}`",
            "",
            "## 9. Recommendation and limits",
            "",
            f"- classification: `{report.classification.value}`",
            f"- reasons: `{','.join(report.classification_reasons)}`",
            "- One PDF does not establish general parser performance.",
            "",
            "## 10. Rerun",
            "",
            f"- bootstrap_seed: `{report.bootstrap_seed}`",
            f"- schema_version: `{report.schema_version}`",
            "",
        )
    )
    assert_report_is_safe(body)
    return body


def _fmt(value: float | int | None) -> str:
    """Format an optional numeric cell.

    Args:
        value: Number or ``None``.

    Returns:
        Display token.
    """

    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
