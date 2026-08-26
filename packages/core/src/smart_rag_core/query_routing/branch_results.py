"""Normalized branch results, coverage bits, and keyword guards."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Literal

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_routing.constants import FALLBACK_EMPTY_KEYWORDS
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import BranchResult, BranchSpec


def inherited_result(
    spec: BranchSpec,
    runtime: AuthorizedRuntimeContext,
    *,
    status: Literal["ok", "degraded", "refused", "failed"],
    fallback_reason: str | None = None,
) -> BranchResult:
    """Build a branch result that copies packet 1 run and reservation ids.

    Args:
        spec: Branch spec.
        runtime: Authorized context.
        status: Branch status. Never an answer claim.
        fallback_reason: Optional limitation or degrade reason.

    Returns:
        Typed branch result.
    """

    return BranchResult(
        branch_id=spec.branch_id,
        kind=spec.kind,
        family=spec.family,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        query_text=spec.query_text,
        status=status,
        fallback_reason=fallback_reason,
    )


def limitation_codes(outcome: object) -> tuple[str, ...]:
    """Normalize graph limitation codes from a retrieve result.

    Args:
        outcome: Graph retrieve result.

    Returns:
        Limitation code strings.
    """

    raw = getattr(outcome, "limitations", ())
    codes: list[str] = []
    for item in raw or ():
        code = getattr(item, "code", item)
        value = getattr(code, "value", code)
        codes.append(str(value))
    return tuple(codes)


def ranked_ids(outcome: object) -> tuple[str, ...]:
    """Extract canonical ranked IDs from a Hybrid result.

    Args:
        outcome: Hybrid retrieve result.

    Returns:
        UUID strings.
    """

    ranked = getattr(outcome, "ranked_ids", ())
    return tuple(str(item) for item in ranked)


def coverage_bits(
    outcome: object,
    whole_document: bool,
) -> tuple[float | None, float | None, tuple[str, ...]]:
    """Read coverage_score and section ratio from Hybrid coverage.

    Args:
        outcome: Hybrid retrieve result.
        whole_document: Whether to compute section coverage.

    Returns:
        Coverage score, section ratio, and uncovered headings.
    """

    coverage = getattr(outcome, "coverage", None)
    score = getattr(coverage, "coverage_score", None) if coverage else None
    uncovered = (
        tuple(getattr(coverage, "uncovered_headings", ()) or ()) if coverage else ()
    )
    ratio: float | None = None
    if whole_document:
        inventory = getattr(coverage, "uncovered_headings", ()) if coverage else ()
        notes = getattr(coverage, "notes", ()) if coverage else ()
        signal = str(getattr(coverage, "signal", "") or "")
        if signal.endswith("full_coverage") or signal == "full_coverage":
            ratio = 1.0
        elif uncovered:
            ratio = 0.0
        elif inventory == ():
            ratio = 1.0 if not notes else 0.0
        else:
            ratio = 0.0
    typed_score = score if isinstance(score, int | float) else None
    return (
        float(typed_score) if typed_score is not None else None,
        ratio,
        tuple(str(item) for item in uncovered),
    )


def fallback_reason_text(outcome: object) -> str | None:
    """Normalize Hybrid fallback reasons without treating them as evidence.

    Args:
        outcome: Hybrid retrieve result or test double.

    Returns:
        Enum value or string, or None when absent/none.
    """

    fallback = getattr(outcome, "fallback_reason", None)
    if fallback is None:
        return None
    if isinstance(fallback, Enum):
        text = str(fallback.value)
    else:
        text = str(fallback)
    if text in {"", "none"}:
        return None
    return text


def inherit_ids(result: BranchResult, runtime: AuthorizedRuntimeContext) -> None:
    """Assert a result copied packet 1 run and reservation ids.

    Args:
        result: Branch result.
        runtime: Authorized context.

    Raises:
        QueryRoutingError: When ids do not match.
    """

    if (
        result.run_id != runtime.run_id
        or result.reservation_id != runtime.reservation_id
    ):
        raise QueryRoutingError("branch_authorization_mismatch")


def empty_keyword_guard(hl_keywords: Sequence[str], ll_keywords: Sequence[str]) -> None:
    """Fail closed instead of calling LightRAG keyword extraction.

    Args:
        hl_keywords: High-level keywords.
        ll_keywords: Low-level keywords.

    Raises:
        QueryRoutingError: ``empty_keywords``.
    """

    if not hl_keywords or not ll_keywords:
        raise QueryRoutingError(FALLBACK_EMPTY_KEYWORDS)
