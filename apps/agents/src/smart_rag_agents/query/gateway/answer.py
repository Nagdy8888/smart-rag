"""Counted company-answer gateway bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.assembly import fit_source_records
from smart_rag_core.query_answer.claims import parse_provider_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.format_shape import format_requested_answer_shape
from smart_rag_core.query_answer.generate import filter_invented_ids
from smart_rag_core.query_answer.generate_grounded import (
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.locate import (
    LocatedQuote,
    located_query,
    located_quotes,
    quote_fallback_payload,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    LOCATE_PROMPT_SHA256,
    LOCATE_PROMPT_VERSION,
    LOCATE_TIMEOUT_SECONDS,
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


def _apply_code_table_salvages(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    query: str,
) -> AnswerPayload:
    """Run the named code-definition and table-block salvages, then re-bind.

    Both repairs apply only when the query names a ``def`` identifier or a
    numbered table caption and canonical evidence holds that block.

    Args:
        payload: Provider answer after invented-id filtering.
        fusion: Fitted canonical evidence.
        tables: Fitted table records.
        query: Original user query. Untrusted.

    Returns:
        Payload after salvage, bind, and derived answer text.
    """

    working = payload
    for salvage_fn in (salvage_named_code_definition, salvage_named_table_block):
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


@dataclass(frozen=True, slots=True)
class LocateResult:
    """Outcome of one locate-quote send.

    Attributes:
        quotes: Validated quotes; empty on failure.
        prompt_tokens: Provider prompt tokens, or None when unknown after a
            sent attempt (usage then records the conservative cap).
        completion_tokens: Provider completion tokens, or None when unknown.
        error: Machine-readable failure reason, or None.
    """

    quotes: tuple[LocatedQuote, ...]
    prompt_tokens: int | None
    completion_tokens: int | None
    error: str | None


def gateway_locate(
    deps: QueryGraphDeps,
    *,
    query: str,
    fusion: FusionResult,
    tables: tuple[object, ...],
    context: AuthorizedRuntimeContext | None,
) -> LocateResult:
    """Run one locate-quote call through the structured answer operation.

    Never raises ``AnswerError``: a counted send must return so the caller
    receives the consumed reservation version. Failures are returned in
    ``LocateResult.error``.

    Args:
        deps: Bound gateway and locate prompt.
        query: Original user query. Untrusted.
        fusion: Fitted canonical evidence.
        tables: Table records.
        context: Admitted run context for the deadline bound.

    Returns:
        Validated quotes plus provider token counts.

    Side Effects:
        At most one provider call, bounded by ``LOCATE_TIMEOUT_SECONDS``.
    """

    from smart_rag_core.gateways.model import AnswerModelRequest

    try:
        typed_tables = tuple(
            item
            if isinstance(item, TableEvidenceRecord)
            else TableEvidenceRecord.model_validate(item)
            for item in tables
        )
    except ValidationError:
        return LocateResult((), 0, 0, "locate_schema_invalid")
    fit = fit_source_records(
        user_query=query,
        fusion=fusion,
        tables=typed_tables,
        max_input_chars=deps.model_input_max_chars,
        route=fusion.effective_route,
    )
    if fit.trim_reason == "input_bound_exceeded":
        return LocateResult((), 0, 0, "input_bound_exceeded")
    gateway = deps.model_gateway
    if gateway is None:
        return LocateResult((), 0, 0, "model_gateway_unbound")
    request = AnswerModelRequest(
        query=query or "query",
        prompt_version=LOCATE_PROMPT_VERSION,
        prompt_sha256=LOCATE_PROMPT_SHA256,
        prompt_text=str(deps.locate_prompt_text or "locate"),
        source_records=fit.records or " ",
        chunk_ids=tuple(item.chunk_id for item in fit.fusion.evidence),
        table_ids=tuple(item.table_id for item in fit.tables),
        remaining_deadline_seconds=min(
            gateway_timeout_seconds(context), LOCATE_TIMEOUT_SECONDS
        ),
    )
    try:
        response = cast(
            Any,
            run_coro(
                lambda: cast(Any, gateway).generate_answer(request),
                cancel_check=deps.cancel_check,
                timeout_seconds=request.remaining_deadline_seconds,
            ),
        )
    except AnswerError as exc:
        return LocateResult((), None, None, exc.reason)
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    try:
        payload = parse_provider_answer(
            response.payload,
            chunk_ids=request.chunk_ids,
            tables=fit.tables,
        )
    except AnswerError as exc:
        return LocateResult((), prompt_tokens, completion_tokens, exc.reason)
    filtered = filter_invented_ids(payload, fit.fusion, fit.tables)
    return LocateResult(
        located_quotes(filtered, fit.fusion), prompt_tokens, completion_tokens, None
    )


def gateway_answer(
    deps: QueryGraphDeps,
    *,
    query: str,
    fusion: FusionResult,
    tables: tuple[object, ...],
    context: AuthorizedRuntimeContext | None,
    located: tuple[LocatedQuote, ...] = (),
) -> tuple[AnswerPayload, int, int]:
    """Run one async gateway answer call from the sync graph.

    Args:
        deps: Bound gateway and prompt.
        query: User query.
        fusion: Canonical evidence.
        tables: Table records.
        context: Admitted run context used for the live deadline timeout.
        located: Validated locate quotes appended to the model-facing query; the
            original query is still used for binding and shape.

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
    records = fit.records
    fusion = fit.fusion
    typed_tables = fit.tables
    timeout_seconds = gateway_timeout_seconds(context)
    model_query = located_query(query or "query", located)
    if len(model_query) + len(records) > deps.model_input_max_chars:
        model_query = query or "query"
    request = AnswerModelRequest(
        query=model_query,
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
        user_query=query,
    )
    derived = with_derived_answer_text(filtered)
    derived = _apply_code_table_salvages(
        derived,
        fusion=fusion,
        tables=typed_tables,
        query=query,
    )
    fallback = quote_fallback_payload(derived, located)
    if fallback is not None:
        derived = with_derived_answer_text(
            bind_company_atomic_links(fallback, fusion=fusion, user_query=query)
        )
    derived = format_requested_answer_shape(derived, user_query=query)
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return (
        derived.model_copy(update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}),
        prompt_tokens,
        completion_tokens,
    )
