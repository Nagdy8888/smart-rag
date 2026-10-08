"""Enrich company-Ask answer rows with diagnosis and usage for LangSmith.

Loads fusion/rerank pages from LangGraph checkpoints, citation pages from
``app.citations``, and token/cost totals from ``app.llm_usage``. Used by
``publish_company_ask_langsmith.py`` so experiments carry diagnosis feedback
and Cost/Usage metadata.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.company_ask_diagnosis import (  # noqa: E402
    DiagnosisSignals,
    RunUsageTotals,
    aggregate_usage_rows,
    build_diagnosis_signals,
)
from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    CompanyAskQuestion,
    CompanyAskResult,
)
from smart_rag_core.evaluation.dual_metric import (  # noqa: E402
    RetrievalStageAttribution,
)

from scripts.eval_ask_stage_export import operator_url  # noqa: E402

_CITATION_PAGES_SQL: LiteralString = """
SELECT c.run_id::text, dc.page_number
FROM app.citations AS c
JOIN app.document_chunks AS dc ON dc.id = c.chunk_id
WHERE c.run_id = ANY(%s::uuid[])
"""

_USAGE_SQL: LiteralString = """
SELECT run_id::text,
       usage_kind,
       model_id,
       prompt_tokens,
       completion_tokens,
       total_tokens,
       cost_usd
FROM app.llm_usage
WHERE run_id = ANY(%s::uuid[])
"""


def checkpoint_diagnosis(
    answers: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Load fusion pages and citation failure codes for each conversation.

    Args:
        answers: Live rows containing ``conversation_id``.

    Returns:
        Question id to fusion pages, fused and pool pages, citation
        failures, and coverage. Empty when the operator database cannot
        be read. The loader lives on the company-ask runner; this wrapper
        is the public entry used by enrichment.
    """

    from scripts import run_company_ask

    loader = cast(
        Callable[
            [Mapping[str, Mapping[str, object]]],
            dict[str, dict[str, object]],
        ],
        vars(run_company_ask)["_checkpoint_diagnosis"],
    )
    return loader(answers)


def enrich_diagnosis_signals(
    questions: Sequence[CompanyAskQuestion],
    *,
    answer_rows: Mapping[str, Mapping[str, Any]],
    results: Sequence[CompanyAskResult],
) -> dict[str, DiagnosisSignals]:
    """Build per-question diagnosis from checkpoint + citation pages.

    Args:
        questions: Loaded private gold questions (with optional pages).
        answer_rows: Live answer rows with ``run_id`` / ``conversation_id``.
        results: Dual-metric scored results.

    Returns:
        Diagnosis mapping. When the operator DB is unavailable, returns
        signals with unknown page flags and outcome-derived buckets.
    """

    by_result = {item.question_id: item for item in results}
    checkpoints = checkpoint_diagnosis(
        cast(Mapping[str, Mapping[str, object]], answer_rows)
    )
    cited_by_run = _citation_pages_by_run(answer_rows)
    enriched: dict[str, DiagnosisSignals] = {}
    for question in questions:
        result = by_result[question.question_id]
        row = answer_rows[question.question_id]
        checkpoint = checkpoints.get(question.question_id, {})
        run_id = str(row.get("run_id") or "")
        cited_pages = cited_by_run.get(run_id, ())
        enriched[question.question_id] = build_diagnosis_signals(
            outcome=result.score.outcome.value,
            grounded=result.score.grounded_fact_pass,
            gold_page=question.page,
            cited_pages=cited_pages or row.get("cited_pages"),
            fused_pages=checkpoint.get("fused_pages") or row.get("fused_pages"),
            rerank_pool_pages=checkpoint.get("pool_pages")
            or row.get("rerank_pool_pages"),
            selected_pages=checkpoint.get("pages") or row.get("selected_pages"),
            citation_failures=_string_tuple(
                checkpoint.get("failures") or row.get("citation_failures")
            ),
            kind=question.kind,
        )
    return enriched


def enrich_run_usage(
    answer_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, RunUsageTotals]:
    """Load ``app.llm_usage`` totals keyed by question id.

    Args:
        answer_rows: Answer rows containing ``run_id``.

    Returns:
        Question id to usage totals. Missing when DB or run id is absent.
    """

    run_to_questions: dict[str, list[str]] = {}
    for question_id, row in answer_rows.items():
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        try:
            UUID(run_id)
        except ValueError:
            continue
        run_to_questions.setdefault(run_id, []).append(question_id)
    if not run_to_questions:
        return {}
    try:
        postgres_url = operator_url()
    except RuntimeError:
        return {}
    by_run: dict[str, list[dict[str, Any]]] = {}
    try:
        with psycopg.connect(postgres_url, connect_timeout=20) as connection:
            rows = connection.execute(_USAGE_SQL, (list(run_to_questions),)).fetchall()
    except psycopg.Error:
        return {}
    for run_id, usage_kind, model_id, prompt, completion, total, cost in rows:
        by_run.setdefault(str(run_id), []).append(
            {
                "usage_kind": usage_kind,
                "model_id": model_id,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "cost_usd": cost,
            }
        )
    totals_by_question: dict[str, RunUsageTotals] = {}
    for run_id, question_ids in run_to_questions.items():
        totals = aggregate_usage_rows(by_run.get(run_id, ()))
        for question_id in question_ids:
            totals_by_question[question_id] = totals
    return totals_by_question


def attach_diagnosis_to_answer_rows(
    answer_rows: Mapping[str, Mapping[str, Any]],
    diagnosis: Mapping[str, DiagnosisSignals],
) -> dict[str, dict[str, Any]]:
    """Copy diagnosis page lists onto answer rows for local persistence.

    Args:
        answer_rows: Original answer rows.
        diagnosis: Enriched diagnosis signals.

    Returns:
        New mapping with diagnosis fields merged into each row.
    """

    merged: dict[str, dict[str, Any]] = {}
    for question_id, row in answer_rows.items():
        payload = dict(row)
        signal = diagnosis.get(question_id)
        if signal is not None:
            payload["diagnosis"] = {
                "gold_page": signal.gold_page,
                "gold_page_cited": signal.gold_page_cited,
                "gold_page_in_fused": signal.gold_page_in_fused,
                "gold_page_in_rerank_pool": signal.gold_page_in_rerank_pool,
                "gold_page_in_selected": signal.gold_page_in_selected,
                "citation_failures": list(signal.citation_failures),
                "failure_bucket": signal.failure_bucket,
                "kind": signal.kind,
            }
        merged[question_id] = payload
    return merged


def score_results_for_enrichment(
    questions: Sequence[CompanyAskQuestion],
    answer_rows: Mapping[str, Mapping[str, Any]],
) -> tuple[CompanyAskResult, ...]:
    """Score answer rows so enrichment can read dual-metric outcomes.

    Args:
        questions: Gold questions.
        answer_rows: Answer rows.

    Returns:
        Scored results.
    """

    from smart_rag_core.evaluation.company_ask_langsmith import (
        parse_company_ask_answer_rows,
    )
    from smart_rag_core.evaluation.company_ask_regression import run_scored_questions

    answers, stages, statuses, reasons = parse_company_ask_answer_rows(
        answer_rows, questions
    )
    return run_scored_questions(
        questions,
        answers=answers,
        stages=stages or cast(dict[str, RetrievalStageAttribution], {}),
        answer_status=statuses,
        terminal_reason=reasons,
    )


def _citation_pages_by_run(
    answer_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[int, ...]]:
    """Load cited page numbers keyed by run id.

    Args:
        answer_rows: Answer rows containing ``run_id``.

    Returns:
        Run id to sorted unique page numbers. Empty when DB is unavailable.
    """

    run_ids = sorted(
        {
            str(row.get("run_id") or "").strip()
            for row in answer_rows.values()
            if str(row.get("run_id") or "").strip()
        }
    )
    if not run_ids:
        return {}
    try:
        postgres_url = operator_url()
    except RuntimeError:
        return {}
    pages: dict[str, list[int]] = {}
    try:
        with psycopg.connect(postgres_url, connect_timeout=20) as connection:
            rows = connection.execute(_CITATION_PAGES_SQL, (run_ids,)).fetchall()
    except psycopg.Error:
        return {}
    for run_id, page in rows:
        if not isinstance(page, int) or isinstance(page, bool):
            continue
        pages.setdefault(str(run_id), []).append(page)
    return {key: tuple(sorted(set(values))) for key, values in pages.items()}


def _string_tuple(value: object) -> tuple[str, ...]:
    """Coerce failure codes to a string tuple.

    Args:
        value: Potential sequence.

    Returns:
        String tuple.
    """

    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        str(item) for item in cast(Sequence[object], value) if str(item).strip()
    )
