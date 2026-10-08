"""Failure-bucket and gold-page diagnosis signals for company-Ask eval.

These helpers turn dual-metric outcomes plus optional retrieval/citation
stage signals into LangSmith-friendly feedback. They never embed answer
bodies or gold phrases.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class RunUsageTotals:
    """Aggregated ``app.llm_usage`` totals for one Ask run.

    Attributes:
        input_tokens: Sum of prompt tokens across usage kinds.
        output_tokens: Sum of completion tokens across usage kinds.
        total_tokens: Sum of total tokens across usage kinds.
        total_cost_usd: Sum of recorded ``cost_usd`` values.
        model_id: Prefer answer-model id when present, else first model.
        usage_kinds: Distinct usage kinds observed.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")
    model_id: str | None = None
    usage_kinds: tuple[str, ...] = ()

    def usage_metadata(self) -> dict[str, int | float]:
        """Return LangSmith-recognized usage/cost metadata.

        Returns:
            Token counts plus ``input_cost``, ``output_cost``, and
            ``total_cost`` for the Cost/Usage columns.
        """

        from smart_rag_core.observability.langsmith_tracing import (
            langsmith_usage_metadata,
        )

        return langsmith_usage_metadata(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_cost_usd=self.total_cost_usd,
        )

    def as_json(self) -> dict[str, Any]:
        """Return a JSON-safe usage payload for experiment outputs.

        Returns:
            Mapping with tokens, USD cost, model id, and usage kinds.
        """

        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": float(self.total_cost_usd),
            "model_id": self.model_id,
            "usage_kinds": list(self.usage_kinds),
            "usage_metadata": self.usage_metadata(),
        }


def aggregate_usage_rows(
    rows: Sequence[Mapping[str, Any]],
) -> RunUsageTotals:
    """Aggregate raw ``llm_usage`` row mappings into one total.

    Args:
        rows: Row mappings with ``prompt_tokens``, ``completion_tokens``,
            ``total_tokens``, ``cost_usd``, ``usage_kind``, and ``model_id``.

    Returns:
        Frozen totals. Empty input yields zeros.
    """

    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    total_cost = Decimal("0")
    kinds: list[str] = []
    answer_model: str | None = None
    first_model: str | None = None
    for row in rows:
        input_tokens += int(row.get("prompt_tokens") or 0)
        output_tokens += int(row.get("completion_tokens") or 0)
        total_tokens += int(row.get("total_tokens") or 0)
        cost_raw = row.get("cost_usd")
        if cost_raw is not None:
            total_cost += Decimal(str(cost_raw))
        kind = str(row.get("usage_kind") or "").strip()
        if kind:
            kinds.append(kind)
        model = str(row.get("model_id") or "").strip() or None
        if model and first_model is None:
            first_model = model
        if kind == "answer" and model:
            answer_model = model
    return RunUsageTotals(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens if total_tokens else input_tokens + output_tokens,
        total_cost_usd=total_cost,
        model_id=answer_model or first_model,
        usage_kinds=tuple(sorted(set(kinds))),
    )


@dataclass(frozen=True, slots=True)
class DiagnosisSignals:
    """Per-question retrieval/citation diagnosis for LangSmith feedback.

    Attributes:
        gold_page: Gold page from the private label, when known.
        gold_page_cited: Whether a persisted citation landed on the gold page.
        gold_page_in_fused: Whether the gold page appeared in ``fused_ids``.
        gold_page_in_rerank_pool: Whether the gold page entered the rerank pool.
        gold_page_in_selected: Whether the gold page was in selected/fused
            evidence shown to the answer stage (fusion channel pages).
        citation_failures: Deterministic citation failure codes.
        failure_bucket: Drop bucket from :func:`classify_ask_drop`.
        kind: Optional question kind (``code`` / ``table`` / ``text``).
    """

    gold_page: int | None = None
    gold_page_cited: bool | None = None
    gold_page_in_fused: bool | None = None
    gold_page_in_rerank_pool: bool | None = None
    gold_page_in_selected: bool | None = None
    citation_failures: tuple[str, ...] = ()
    failure_bucket: str = "unknown"
    kind: str | None = None


def page_in_pages(gold_page: int | None, pages: object) -> bool | None:
    """Return whether ``gold_page`` is present in a measured page collection.

    Args:
        gold_page: Page from private gold.
        pages: Sequence of page numbers, or any other value when unmeasured.

    Returns:
        ``True``/``False`` when both sides were measured, else ``None``.
    """

    if gold_page is None:
        return None
    if isinstance(pages, (list, tuple, set, frozenset)):
        values = cast(Iterable[object], pages)
        typed = {item for item in values if isinstance(item, int)}
        return gold_page in typed
    return None


def classify_ask_drop(
    *,
    outcome: str,
    grounded: bool,
    gold_page_in_fusion: bool | None,
    citation_failures: Sequence[str],
    gold_page_in_fused: bool | None = None,
    gold_page_in_rerank_pool: bool | None = None,
) -> str:
    """Name the first stage that explains a missed known answer.

    Args:
        outcome: Dual-metric outcome value.
        grounded: Whether every required fact matched.
        gold_page_in_fusion: Whether the gold page was in selected evidence.
        citation_failures: Deterministic citation failure codes.
        gold_page_in_fused: Whether the gold page was in ``fused_ids``.
        gold_page_in_rerank_pool: Whether the gold page entered the rerank pool.

    Returns:
        A short drop bucket: ``pass``, ``retrieval_miss``,
        ``rerank_pool_drop``, ``selection_drop``, ``citation``,
        ``verifier_refusal``, ``phrasing``, ``deadline``, ``error``, or the
        raw outcome when none of those rules apply.
    """

    if outcome in {"strict_phrase", "fact_covered"} and grounded:
        return "pass"
    if outcome == "error":
        return "error"
    if outcome == "deadline":
        return "deadline"
    if outcome == "empty_retrieval" or gold_page_in_fused is False:
        return "retrieval_miss"
    if gold_page_in_fused and gold_page_in_rerank_pool is False:
        return "rerank_pool_drop"
    if gold_page_in_rerank_pool and gold_page_in_fusion is False:
        return "selection_drop"
    if gold_page_in_fused is None and gold_page_in_fusion is False:
        return "retrieval_miss"
    if citation_failures or outcome == "verifier_refusal_after_fusion":
        return "citation" if citation_failures else "verifier_refusal"
    if outcome == "wrong_phrasing":
        return "phrasing"
    if outcome == "partial":
        return "partial"
    return outcome


def build_diagnosis_signals(
    *,
    outcome: str,
    grounded: bool,
    gold_page: int | None = None,
    cited_pages: object = None,
    fused_pages: object = None,
    rerank_pool_pages: object = None,
    selected_pages: object = None,
    citation_failures: Sequence[str] = (),
    kind: str | None = None,
) -> DiagnosisSignals:
    """Build one diagnosis payload for LangSmith target outputs / feedback.

    Args:
        outcome: Dual-metric outcome value.
        grounded: Whether every required fact matched.
        gold_page: Gold page number.
        cited_pages: Pages from persisted citations.
        fused_pages: Pages for ``fused_ids``.
        rerank_pool_pages: Pages for ``rerank_pool_ids``.
        selected_pages: Pages for selected/fusion evidence.
        citation_failures: Deterministic citation failure codes.
        kind: Optional question kind label.

    Returns:
        Frozen diagnosis signals including ``failure_bucket``.
    """

    cited = page_in_pages(gold_page, cited_pages)
    in_fused = page_in_pages(gold_page, fused_pages)
    in_pool = page_in_pages(gold_page, rerank_pool_pages)
    in_selected = page_in_pages(gold_page, selected_pages)
    failures = tuple(str(item) for item in citation_failures if str(item).strip())
    bucket = classify_ask_drop(
        outcome=outcome,
        grounded=grounded,
        gold_page_in_fusion=in_selected if in_selected is not None else cited,
        citation_failures=failures,
        gold_page_in_fused=in_fused,
        gold_page_in_rerank_pool=in_pool,
    )
    return DiagnosisSignals(
        gold_page=gold_page,
        gold_page_cited=cited,
        gold_page_in_fused=in_fused,
        gold_page_in_rerank_pool=in_pool,
        gold_page_in_selected=in_selected,
        citation_failures=failures,
        failure_bucket=bucket,
        kind=kind,
    )


def bool_feedback_score(value: bool | None) -> float | None:
    """Map an optional boolean diagnosis flag to a LangSmith score.

    Args:
        value: Measured flag, or ``None`` when unknown.

    Returns:
        ``1.0`` / ``0.0`` when measured, else ``None``.
    """

    if value is None:
        return None
    return 1.0 if value else 0.0


def failure_bucket_score(bucket: str) -> float:
    """Map a failure bucket to a pass/fail LangSmith score.

    Args:
        bucket: Drop bucket from :func:`classify_ask_drop`.

    Returns:
        ``1.0`` for ``pass``, otherwise ``0.0``.
    """

    return 1.0 if bucket == "pass" else 0.0
