"""Private-safe category metrics; missing judgments never become passes."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import cast

from smart_rag_core.evaluation.company_ask_regression import (
    CompanyAskQuestion,
    CompanyAskResult,
)


def summarize_knowledge_metrics(
    questions: Sequence[CompanyAskQuestion],
    results: Sequence[CompanyAskResult],
    answers: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate quality, outcome, timing, and measured cost without raw content."""
    scored = {result.question_id: result for result in results}
    groups: dict[str, list[CompanyAskQuestion]] = {}
    for question in questions:
        arabic = bool(re.search(r"[\u0600-\u06ff]", question.prompt))
        latin = bool(re.search(r"[A-Za-z]", question.prompt))
        language = "mixed" if arabic and latin else "ar" if arabic else "en"
        groups.setdefault(f"{question.kind or 'unclassified'}:{language}", []).append(
            question
        )
    categories: dict[str, object] = {}
    for category, cases in groups.items():
        rows = [answers.get(case.question_id, {}) for case in cases]
        outcomes: dict[str, int] = {}
        times: list[float] = []
        costs: list[float] = []
        for row in rows:
            knowledge = _mapping(row.get("knowledge_result"))
            outcome = str(knowledge.get("outcome") or "unknown")
            if outcome not in {
                "supported",
                "partial",
                "insufficient_evidence",
                "conflicting_evidence",
            }:
                outcome = "unknown"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            timing = _number(_mapping(row.get("timing")).get("wall_seconds"))
            cost = _number(_mapping(row.get("usage")).get("cost_usd"))
            if timing is not None:
                times.append(timing)
            if cost is not None:
                costs.append(cost)
        judgments: dict[str, object] = {}
        for name in (
            "citation_supported",
            "current_source_correct",
            "permission_correct",
        ):
            values = [row[name] for row in rows if isinstance(row.get(name), bool)]
            judgments[name] = {
                "scored": len(values),
                "pass_rate": sum(value is True for value in values) / len(values)
                if values
                else None,
            }
        categories[category] = {
            "questions": len(cases),
            "scored_answers": sum(case.question_id in scored for case in cases),
            "strict_pass": sum(
                bool(scored[case.question_id].score.strict_pass)
                for case in cases
                if case.question_id in scored
            ),
            "grounded_fact_pass": sum(
                bool(scored[case.question_id].score.grounded_fact_pass)
                for case in cases
                if case.question_id in scored
            ),
            "knowledge_outcomes": outcomes,
            "outcome_measured": len(cases) - outcomes.get("unknown", 0),
            "answered": sum(
                outcomes.get(key, 0)
                for key in ("supported", "partial", "conflicting_evidence")
            ),
            "refused": outcomes.get("insufficient_evidence", 0),
            "latency_measured": len(times),
            "latency_p50_seconds": _percentile(times, 0.5),
            "latency_p95_seconds": _percentile(times, 0.95),
            "cost_measured": len(costs),
            "measured_cost_usd": sum(costs) if costs else None,
            "judgments": judgments,
        }
    return {
        "schema": "company-knowledge-metrics-v1",
        "categories": categories,
        "questions": len(questions),
        "scored_answers": len(results),
        "quality_gate": "not_evaluated",
        "holdout_opened": False,
    }


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow additive JSON objects without inventing absent measurements."""
    return cast(Mapping[str, object], value) if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    """Accept finite nonnegative measurements, never booleans or unknowns."""
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _percentile(values: list[float], quantile: float) -> float | None:
    """Use the conservative nearest-rank percentile on measured rows only."""
    return (
        sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]
        if values
        else None
    )
