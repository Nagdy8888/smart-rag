"""Company answer release used by the verify node.

Rendering, extractive salvage, and requested shape run here so the
verify node stays inside the physical line cap.
"""

from __future__ import annotations

from pydantic import ValidationError
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.format_shape import format_requested_answer_shape
from smart_rag_core.query_answer.generate_grounded import (
    salvage_anchor_claim_fill,
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.release import render_verified_company_answer
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.models import TableEvidenceRecord


def company_release_payload(
    checked: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    user_query: str,
) -> AnswerPayload:
    """Render, salvage, and reshape one company answer.

    Validation and answer errors keep the last successful payload.
    Any other exception propagates so the caller can release the
    generated draft instead of aborting the graph.

    Args:
        checked: Answer after deterministic checks and the verifier.
        fusion: Fitted canonical evidence for this run.
        tables: Deterministic table snapshots.
        user_query: Original user text. Untrusted.

    Returns:
        Released company payload.

    Raises:
        Exception: Unexpected render or salvage failures.
    """

    try:
        checked = render_verified_company_answer(
            checked,
            fusion=fusion,
            tables=tables,
            user_query=user_query,
        )
    except (ValidationError, ValueError, AnswerError):
        # Keep the pre-render payload; the structural salvages below may still repair.
        pass
    if fusion.evidence:
        for salvage_fn in (
            salvage_named_code_definition,
            salvage_named_table_block,
            salvage_anchor_claim_fill,
        ):
            try:
                salvaged = salvage_fn(checked, fusion, user_query=user_query)
            except (ValidationError, ValueError, AnswerError):
                continue
            if salvaged is checked:
                continue
            try:
                checked = render_verified_company_answer(
                    salvaged,
                    fusion=fusion,
                    tables=tables,
                    user_query=user_query,
                )
            except (ValidationError, ValueError, AnswerError):
                # Keep the extractive salvage rather than dropping it.
                checked = salvaged
    try:
        checked = format_requested_answer_shape(checked, user_query=user_query)
    except (ValidationError, ValueError, AnswerError):
        # Pipe-table / fence reshaping must not fail the verified path
        # after a successful extractive salvage.
        pass
    return checked
