"""Counted company-answer gateway bridge."""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.assembly import (
    assemble_source_records,
    fit_source_records,
)
from smart_rag_core.query_answer.claims import parse_provider_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.format_shape import format_requested_answer_shape
from smart_rag_core.query_answer.generate import filter_invented_ids
from smart_rag_core.query_answer.generate_grounded import (
    salvage_anchor_claim_fill,
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.ownership_shape import shape_ownership_matrix_draft
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_answer.query_coverage import salvage_question_coverage
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_answer.source_focus import prioritize_answer_sources
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    attempt_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.answer_attempts import ANSWER_ATTEMPT_CAP_SECONDS
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response


def _apply_code_table_salvages(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    query: str,
) -> AnswerPayload:
    """Run named code/table and anchor claim-fill salvages, then re-bind.

    Structural ``def`` / Table N-M repairs run first; anchor claim fill
    appends at most one omitted evidence span when the anchor gate clears.

    Args:
        payload: Provider answer after invented-id filtering.
        fusion: Fitted canonical evidence.
        tables: Fitted table records.
        query: Original user query. Untrusted.

    Returns:
        Payload after salvage, bind, and derived answer text.
    """

    working = payload
    for salvage_fn in (
        salvage_named_code_definition,
        salvage_named_table_block,
        salvage_question_coverage,
        salvage_anchor_claim_fill,
    ):
        salvaged = salvage_fn(working, fusion, user_query=query)
        if salvaged is working:
            continue
        working = bind_company_atomic_links(
            filter_invented_ids(salvaged, fusion, tables),
            fusion=fusion,
            user_query=query,
        )
        working = with_derived_answer_text(working)
    # Formatting is applied once by the caller after salvage returns.
    return working


def gateway_answer(
    deps: QueryGraphDeps,
    *,
    query: str,
    fusion: FusionResult,
    tables: tuple[object, ...],
    context: AuthorizedRuntimeContext | None,
) -> tuple[AnswerPayload, int, int]:
    """Run one async gateway answer call from the sync graph.

    Args:
        deps: Bound gateway and prompt.
        query: User query.
        fusion: Canonical evidence.
        tables: Table records.
        context: Admitted run context used for the live deadline timeout.

    Returns:
        Parsed answer payload plus provider prompt and completion tokens.
        Live company payloads bind omitted paragraphs/citations from links
        before the node returns so compacted fusion hashes cannot empty
        the paragraph contract.

    Raises:
        AnswerError: If the gateway is unbound or the provider payload
            matches neither the pinned answer claims shape nor
            ``AnswerPayload``.
    """

    from smart_rag_core.gateways.model import AnswerModelRequest

    try:
        typed_tables = tuple(
            item
            if isinstance(item, TableEvidenceRecord)
            else TableEvidenceRecord.model_validate(item)
            for item in tables
        )
    except ValidationError as exc:
        raise AnswerError("answer_schema_invalid") from exc
    fit = fit_source_records(
        user_query=query,
        fusion=fusion,
        tables=typed_tables,
        max_input_chars=deps.model_input_max_chars,
        route=fusion.effective_route,
    )
    if fit.trim_reason == "input_bound_exceeded":
        raise AnswerError("input_bound_exceeded")
    fusion = fit.fusion
    typed_tables = fit.tables
    records = assemble_source_records(
        prioritize_answer_sources(fusion, query), typed_tables
    )
    timeout_seconds = attempt_timeout_seconds(context, ANSWER_ATTEMPT_CAP_SECONDS)
    request = AnswerModelRequest(
        query=query or "query",
        prompt_version=ANSWER_PROMPT_VERSION,
        prompt_sha256=ANSWER_PROMPT_SHA256,
        prompt_text=str(deps.answer_prompt_text or "answer"),
        source_records=records or " ",
        chunk_ids=tuple(item.chunk_id for item in fusion.evidence),
        table_ids=tuple(item.table_id for item in typed_tables),
        remaining_deadline_seconds=timeout_seconds,
    )
    gateway = deps.model_gateway
    if gateway is None:
        raise AnswerError("model_gateway_unbound")
    response = cast(
        Any,
        run_coro(
            lambda: cast(Any, gateway).generate_answer(request),
            cancel_check=deps.cancel_check,
            timeout_seconds=request.remaining_deadline_seconds,
        ),
    )
    payload = parse_provider_answer(
        response.payload,
        chunk_ids=request.chunk_ids,
        tables=typed_tables,
    )
    payload = shape_ownership_matrix_draft(payload, fusion, user_query=query)
    filtered = bind_company_atomic_links(
        filter_invented_ids(payload, fusion, typed_tables),
        fusion=fusion,
        user_query=query,
    )
    derived = with_derived_answer_text(filtered)
    derived = _apply_code_table_salvages(
        derived,
        fusion=fusion,
        tables=typed_tables,
        query=query,
    )
    derived = format_requested_answer_shape(derived, user_query=query)
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return (
        derived.model_copy(update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}),
        prompt_tokens,
        completion_tokens,
    )
