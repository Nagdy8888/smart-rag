"""Counted company-answer gateway bridge."""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.assembly import fit_source_records
from smart_rag_core.query_answer.claims import parse_provider_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import filter_invented_ids
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    gateway_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response


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
            matches neither the ``answer_v4`` claims shape nor
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
    records = fit.records
    fusion = fit.fusion
    typed_tables = fit.tables
    timeout_seconds = gateway_timeout_seconds(context)
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
    filtered = bind_company_atomic_links(
        filter_invented_ids(payload, fusion, typed_tables),
        fusion=fusion,
    )
    derived = with_derived_answer_text(filtered)
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return (
        derived.model_copy(update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}),
        prompt_tokens,
        completion_tokens,
    )
