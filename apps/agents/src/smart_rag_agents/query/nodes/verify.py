"""Deterministic citation checks, then at most one six-link verifier call."""

from __future__ import annotations

from typing import cast

import psycopg
from pydantic import ValidationError
from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.service import summarize_run_usage
from smart_rag_core.query_answer.citations import (
    drop_skipped_citations,
    maybe_persist_verified_citations,
    persist_web_answer_citations,
)
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    VerificationResult,
    VerifierPayload,
)
from smart_rag_core.query_answer.release import (
    bind_company_atomic_links,
    company_release_applies,
    render_verified_company_answer,
)
from smart_rag_core.query_answer.verifier import run_verifier_batch
from smart_rag_core.query_routing.constants import (
    FALLBACK_RETRIEVERS_UNBOUND,
    LIMITATION_VERIFIER_OMITTED_LINKS,
    VERIFIER_SKIPPED_DETAIL_PREFIX,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.query_routing.serde import plan_from_state
from smart_rag_core.web_research.models import WebSourceRecord

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.verifier import gateway_verifier
from smart_rag_agents.query.nodes.shared import (
    route_needs_retrieval,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.nodes.state_codec import (
    fusion_from_state,
    tables_from_state,
)
from smart_rag_agents.query.state import QueryGraphState


def verify_answer_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Deterministic citation checks, then at most one six-link verifier call.

    State inputs:
        ``answer``, ``fusion``, ``table_composition``,
        ``remaining_model_calls``, ``verifier_call_count``.

    State outputs:
        ``verification`` (including ``verifier_skipped_reason`` when the
        verifier call failed), accumulated ``prompt_tokens`` /
        ``completion_tokens``, and possibly decremented remaining calls.

    Persistence writes:
        Counted ``verifier`` usage when a connection and gateway are bound.
        Bound citation persistence failure degrades to
        ``insufficient_evidence`` and never streams a verified uncited
        answer. Unbound Studio graphs skip persistence.

    External/model calls:
        Zero or one small verifier call covering at most six material
        links. A seventh link is omitted. Never a second verifier call.

    Budget/deadline behavior:
        Deadline/step exhaustion emits verified partial, not fake success.

    Failure/fallback route:
        Unsupported links are removed or refused. Unsupported chains drop
        the composed conclusion. Inspection/NoRetrieval stay refused.
        Missing gateway, omitted verifier links, or a schema-invalid
        verifier payload never terminate ``verified``. Omitted IDs force
        ``verified_partial`` and ``verifier_omitted_links``. Invalid
        verifier JSON degrades to ``verified_partial`` with the
        already-generated answer.         A verifier timeout or gateway failure
        degrades to ``verified_partial`` with detail
        ``verifier_skipped:<reason>`` and still persists citations.
        Leaf-unresolved citations are skipped: some remaining citations
        become ``verified_partial`` with ``citation_leaf_unresolved``;
        zero persisted citations stay ``insufficient_evidence``.
        Company answers without valid paragraph
        mappings become a citation-free refusal; fusion passages are never
        backfilled as citations.

    Args:
        state: State after answer generation.
        deps: Optional gateway and connection.

    Returns:
        Terminal verified state.
    """

    if skip_closed_nodes(state):
        return state
    raw_answer = state.get("answer")
    if raw_answer is None:
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": "missing_answer",
        }
    try:
        fusion = fusion_from_state(state.get("fusion"))
        tables = tables_from_state(state.get("table_composition"))
        payload = AnswerPayload.model_validate(raw_answer)
    except ValidationError:
        preserved = raw_answer
        return {
            **state,
            "status": "verified_partial",
            "detail": "payload_schema_invalid",
            "answer": preserved,
        }
    plan = None
    if state.get("retrieval_plan") is not None:
        try:
            plan = plan_from_state(state["retrieval_plan"])
        except ValueError:
            plan = None
    web_records: list[WebSourceRecord] = []
    web_excerpts: dict[str, str] = {}
    for raw_source in state.get("web_sources") or []:
        try:
            record = WebSourceRecord.model_validate(raw_source)
        except ValidationError:
            continue
        web_records.append(record)
        web_excerpts[record.web_source_id] = record.excerpt
    is_web = payload.answer_origin is KnowledgeScope.WEB or (
        plan is not None and plan.knowledge_scope is KnowledgeScope.WEB
    )
    if is_web and not web_excerpts:
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": "web_evidence_insufficient",
            "answer": payload.model_dump(mode="json"),
        }
    prepared = payload if is_web else bind_company_atomic_links(payload, fusion=fusion)
    checked, failures = deterministic_check_answer(
        prepared,
        fusion=fusion,
        tables=tables.records,
        evidence_required=route_needs_retrieval(plan) and not is_web,
        web_excerpts=web_excerpts if is_web else None,
        require_paragraphs=route_needs_retrieval(plan) and not is_web,
    )
    remaining = state["remaining_model_calls"]
    verifier_calls = state.get("verifier_call_count") or 0
    omitted: tuple[str, ...] = ()
    added_prompt_tokens = 0
    added_completion_tokens = 0
    verifier_skipped_reason: str | None = None
    if checked.atomic_links and not is_web:
        caller = None
        if deps.model_gateway is not None and deps.verifier_prompt_text:

            def _verifier_caller(links: tuple[AtomicLink, ...]) -> VerifierPayload:
                """Invoke one verifier batch through the bound gateway.

                Args:
                    links: At most six material links.

                Returns:
                    Structured verifier payload.
                """

                nonlocal added_prompt_tokens, added_completion_tokens
                payload, prompt_tokens, completion_tokens = gateway_verifier(
                    deps,
                    links=links,
                    fusion=fusion,
                    tables=tables.records,
                    context=runtime_from_state(state),
                )
                added_prompt_tokens += prompt_tokens
                added_completion_tokens += completion_tokens
                return payload

            caller = _verifier_caller
        try:
            if caller is not None:
                remaining = assert_call_available(remaining)
            checked, verifier_calls, omitted = run_verifier_batch(
                checked,
                caller=caller,
                already_called=verifier_calls,
            )
        except (AnswerError, QueryCeilingError) as exc:
            reason = getattr(exc, "reason", None) or str(exc) or "verifier_failed"
            verifier_skipped_reason = str(reason)[:64]
    if company_release_applies(checked, is_web=is_web):
        checked = render_verified_company_answer(
            checked, fusion=fusion, tables=tables.records
        )
    knowledge_scope = plan.knowledge_scope if plan is not None else None
    terminal = "verified_partial"
    if (
        checked.status == "refused"
        and not fusion.evidence
        and not tables.records
        and knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    ):
        terminal = "insufficient_evidence"
        detail = "insufficient authorized evidence"
    elif checked.status == "refused":
        terminal = "refused"
        detail = "answer refused after verification"
    elif checked.status == "partial" or failures or omitted:
        terminal = "verified_partial"
        detail = (
            LIMITATION_VERIFIER_OMITTED_LINKS
            if omitted
            else "verified partial after citation checks"
        )
    else:
        terminal = "verified"
        detail = "answer verified"
    if verifier_skipped_reason is not None and terminal in {
        "verified",
        "verified_partial",
    }:
        terminal = "verified_partial"
        detail = f"{VERIFIER_SKIPPED_DETAIL_PREFIX}{verifier_skipped_reason}"[:128]
    if (
        terminal == "verified"
        and deps.model_gateway is None
        and route_needs_retrieval(plan)
    ):
        terminal = "verified_partial"
        detail = "model_gateway_unbound"
    if (
        terminal == "verified"
        and route_needs_retrieval(plan)
        and deps.hybrid_retriever is None
    ):
        terminal = "insufficient_evidence"
        detail = FALLBACK_RETRIEVERS_UNBOUND
    context = runtime_from_state(state)
    billed_prompt = int(state.get("prompt_tokens") or 0) + max(0, added_prompt_tokens)
    billed_completion = int(state.get("completion_tokens") or 0) + max(
        0, added_completion_tokens
    )
    billed_cost_usd: float | None = None
    if deps.connection is not None and context is not None:
        try:
            billed = summarize_run_usage(
                deps.connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
            )
            billed_prompt = billed.prompt_tokens
            billed_completion = billed.completion_tokens
            billed_cost_usd = float(billed.cost_usd)
        except (QueryAdmissionError, psycopg.Error):
            pass
    if route_needs_retrieval(plan) and checked.answer_origin is None:
        checked = checked.model_copy(
            update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
        )
    skipped_citation_count = 0
    if is_web:
        checked = checked.model_copy(
            update={
                "citations": (),
                "table_citations": (),
                "answer_origin": KnowledgeScope.WEB,
            }
        )
        if not checked.web_citations:
            terminal = "insufficient_evidence"
            detail = "web_evidence_insufficient"
        elif deps.connection is not None and context is not None:
            try:
                persist_web_answer_citations(
                    deps.connection,
                    caller=caller_from_runtime(context),
                    run_id=context.run_id,
                    sources=tuple(web_records),
                    answer=checked,
                )
            except (QueryAdmissionError, psycopg.Error, ValueError):
                terminal = "insufficient_evidence"
                detail = "web_evidence_insufficient"
    else:
        try:
            persisted = maybe_persist_verified_citations(
                deps.connection,
                caller=caller_from_runtime(context) if context is not None else None,
                run_id=context.run_id if context is not None else None,
                fusion=fusion,
                answer=checked,
            )
        except (QueryAdmissionError, psycopg.Error):
            if deps.connection is not None and context is not None:
                terminal = "insufficient_evidence"
                detail = "citation_persist_failed"
        else:
            if persisted.skipped:
                skipped_citation_count = len(persisted.skipped)
                checked = drop_skipped_citations(checked, persisted.skipped)
                if not persisted.ids:
                    terminal = "insufficient_evidence"
                    detail = "citation_leaf_unresolved"
                elif terminal in {"verified", "verified_partial"}:
                    terminal = "verified_partial"
                    detail = "citation_leaf_unresolved"
    result = VerificationResult(
        answer=checked,
        deterministic_failures=failures,
        verifier_call_count=1 if verifier_calls else 0,
        omitted_link_ids=omitted,
        verifier_skipped_reason=verifier_skipped_reason,
        skipped_citation_count=skipped_citation_count,
        status=terminal
        if terminal
        in {"verified", "verified_partial", "refused", "insufficient_evidence"}
        else "verified_partial",
    )
    return cast(
        QueryGraphState,
        {
            **state,
            "status": terminal,
            "detail": detail,
            "answer": checked.model_dump(mode="json"),
            "verification": result.model_dump(mode="json"),
            "remaining_model_calls": remaining,
            "verifier_call_count": verifier_calls,
            "catalog_llm_call_count": int(state.get("catalog_llm_call_count") or 0),
            "keyword_extract_count": 0,
            "prompt_tokens": billed_prompt,
            "completion_tokens": billed_completion,
            "cost_usd": billed_cost_usd,
        },
    )
