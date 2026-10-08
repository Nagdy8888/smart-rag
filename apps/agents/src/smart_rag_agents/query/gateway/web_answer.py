"""Counted Web-research synthesis gateway bridge."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import ValidationError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload, AtomicLink
from smart_rag_core.query_answer.versions import (
    WEB_ANSWER_PROMPT_SHA256,
    WEB_ANSWER_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.web_research.models import WebSourceRecord
from smart_rag_core.web_research.synthesis import (
    citations_from_persisted_ids,
    isolate_web_sources,
    mock_web_answer,
)

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    gateway_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response


def _parse_web_answer_payload(
    raw: object,
    *,
    sources: tuple[WebSourceRecord, ...],
) -> AnswerPayload:
    """Parse and ground one provider Web-answer payload.

    Args:
        raw: Provider JSON object.
        sources: Persisted Web sources for this run.

    Returns:
        Web-origin answer with invented IDs and non-contained spans dropped.

    Raises:
        AnswerError: If the payload shape is invalid.
    """

    if not isinstance(raw, dict):
        raise AnswerError("web_answer_schema_invalid")
    typed = {str(key): value for key, value in cast(dict[object, object], raw).items()}
    raw_status = typed.get("status")
    status: Literal["complete", "partial", "refused"] = "refused"
    if raw_status == "complete":
        status = "complete"
    elif raw_status == "partial":
        status = "partial"
    claimed_ids: list[str] = []
    spans: list[str] = []
    raw_citations = typed.get("web_citations")
    citation_items: list[object] = (
        cast(list[object], raw_citations) if isinstance(raw_citations, list) else []
    )
    for item in citation_items:
        if not isinstance(item, dict):
            continue
        citation = cast(dict[object, object], item)
        source_id = str(citation.get("web_source_id") or "").strip()
        span = str(citation.get("span") or "").strip()
        if not source_id or not span:
            continue
        claimed_ids.append(source_id)
        spans.append(span)
    web_citations = citations_from_persisted_ids(
        sources=sources,
        claimed_ids=tuple(claimed_ids),
        spans=tuple(spans),
    )
    allowed = {item.web_source_id for item in sources}
    links: list[AtomicLink] = []
    raw_links = typed.get("atomic_links")
    link_items: list[object] = (
        cast(list[object], raw_links) if isinstance(raw_links, list) else []
    )
    for item in link_items:
        if not isinstance(item, dict):
            continue
        link_raw = cast(dict[object, object], item)
        link_id = str(link_raw.get("link_id") or "").strip()
        claim = str(link_raw.get("claim") or "").strip()
        if not link_id or not claim:
            continue
        source_ids_raw = link_raw.get("web_source_ids")
        kept_ids: list[str] = []
        id_items: list[object] = (
            cast(list[object], source_ids_raw)
            if isinstance(source_ids_raw, list)
            else []
        )
        for value in id_items:
            text = str(value).strip()
            if text in allowed:
                kept_ids.append(text)
        if not kept_ids:
            continue
        try:
            links.append(
                AtomicLink(
                    link_id=link_id[:64],
                    claim=claim[:2000],
                    web_source_ids=tuple(kept_ids),
                )
            )
        except ValidationError:
            continue
    answer_text = str(typed.get("answer_text") or "").strip()
    if not web_citations:
        status = "refused"
        if not answer_text:
            answer_text = "Insufficient public web evidence."
    return AnswerPayload(
        answer_text=answer_text[:16_384],
        citations=(),
        web_citations=web_citations,
        atomic_links=tuple(links),
        table_citations=(),
        status=status,
        answer_origin=KnowledgeScope.WEB,
    )


def gateway_web_answer(
    deps: QueryGraphDeps,
    *,
    query: str,
    sources: tuple[WebSourceRecord, ...],
    context: AuthorizedRuntimeContext | None,
) -> tuple[AnswerPayload, int, int]:
    """Run one async Web-answer gateway call from the sync graph.

    Args:
        deps: Bound gateway and ``web_answer_v1`` prompt.
        query: Sanitized user query.
        sources: Persisted Web sources for this run.
        context: Admitted run context used for the live deadline timeout.

    Returns:
        Grounded Web answer payload plus provider token counts.

    Raises:
        AnswerError: If the gateway or prompt is unbound, or the provider
            payload cannot be grounded.
    """

    from smart_rag_core.gateways.model import WebAnswerModelRequest

    if not sources:
        raise AnswerError("web_answer_sources_empty")
    prompt_text = deps.web_answer_prompt_text
    if not prompt_text:
        raise AnswerError("web_answer_prompt_unbound")
    gateway = deps.model_gateway
    if gateway is None:
        raise AnswerError("model_gateway_unbound")
    timeout_seconds = gateway_timeout_seconds(context)
    request = WebAnswerModelRequest(
        query=query or "query",
        prompt_version=WEB_ANSWER_PROMPT_VERSION,
        prompt_sha256=WEB_ANSWER_PROMPT_SHA256,
        prompt_text=str(prompt_text),
        source_records=isolate_web_sources(sources),
        web_source_ids=tuple(item.web_source_id for item in sources),
        remaining_deadline_seconds=timeout_seconds,
    )
    try:
        response = cast(
            Any,
            run_coro(
                lambda: cast(Any, gateway).generate_web_answer(request),
                cancel_check=deps.cancel_check,
                timeout_seconds=request.remaining_deadline_seconds,
            ),
        )
    except AnswerError:
        raise
    except Exception as exc:
        raise AnswerError("web_answer_provider_error") from exc
    payload = _parse_web_answer_payload(
        getattr(response, "payload", None), sources=sources
    )
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return payload, prompt_tokens, completion_tokens


def synthesize_web_answer(
    deps: QueryGraphDeps,
    *,
    query: str,
    sources: tuple[WebSourceRecord, ...],
    context: AuthorizedRuntimeContext | None,
) -> AnswerPayload:
    """Synthesize a Web draft via the gateway, falling back to extractive mock.

    Args:
        deps: Bound gateway and prompt when available.
        query: Sanitized user query.
        sources: Persisted Web sources.
        context: Admitted run context for deadline timeout.

    Returns:
        Web-origin answer. Never Hybrid and never invents source IDs.
    """

    try:
        payload, _prompt_tokens, _completion_tokens = gateway_web_answer(
            deps,
            query=query,
            sources=sources,
            context=context,
        )
    except AnswerError:
        return mock_web_answer(query=query, sources=sources)
    if payload.answer_origin is not KnowledgeScope.WEB:
        payload = payload.model_copy(update={"answer_origin": KnowledgeScope.WEB})
    return payload.model_copy(update={"citations": (), "table_citations": ()})
