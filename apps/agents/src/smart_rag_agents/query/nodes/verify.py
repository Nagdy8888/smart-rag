"""Deterministic citation checks, then at most one six-link verifier call."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

import psycopg
from pydantic import ValidationError
from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.service import (
    ReservationConsumeResult,
    summarize_run_usage,
)
from smart_rag_core.query_answer.citations import (
    drop_skipped_citations,
    maybe_persist_verified_citations,
    persist_web_answer_citations,
    repair_leaf_citations,
    shorten_contained_skipped_spans,
)
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    VerificationResult,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.release import (
    align_split_source_identifiers,
    bind_company_atomic_links,
    company_release_applies,
    render_verified_company_answer,
)
from smart_rag_core.query_answer.source_syntax import (
    SOURCE_CODE_SYNTAX_INVALID,
    has_source_code_syntax_issue,
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
from smart_rag_core.sse.store import sqlstate_of
from smart_rag_core.web_research.models import WebSourceRecord

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.verifier import (
    VerifierAttemptError,
    gateway_verifier,
)
from smart_rag_agents.query.nodes.knowledge import (
    annotate_knowledge_result,
    company_evidence_context,
)
from smart_rag_agents.query.nodes.release_safety import (
    refresh_refusal_usage,
    refuse_release,
)
from smart_rag_agents.query.nodes.shared import (
    route_needs_retrieval,
    runtime_after_consume,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.nodes.state_codec import (
    fusion_from_state,
    tables_from_state,
)
from smart_rag_agents.query.nodes.verify_release import company_release_payload
from smart_rag_agents.query.run_timings import with_verifier_timing
from smart_rag_agents.query.state import QueryGraphState


def verify_answer_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Verify and persist the final answer, refusing unexpected checker failures.

    Args:
        state: Generated answer and canonical evidence under admitted ceilings.
        deps: Bound gateways, authorization-scoped connection, and prompts.

    Returns:
        A checked answer or a citation-free verification-unavailable refusal.
        Cancellation and generator shutdown propagate to normal cleanup.
    """
    try:
        result = annotate_knowledge_result(_verify_answer(state, deps), deps)
    except Exception as exc:
        result = refuse_release(state, type(exc).__name__)
    if str(result.get("detail") or "").startswith("verification_unavailable:"):
        return refresh_refusal_usage(result, deps)
    return result


def _verify_answer(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Run deterministic checks, one bounded verifier, and citation persistence.

    Args:
        state: Generated answer with canonical passages/table results.
        deps: Optional gateway and scoped connection.

    Returns:
        Final release state. No checker exception restores the model draft.
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
        return refuse_release(state, "payload_schema_invalid")
    plan = None
    if state.get("retrieval_plan") is not None:
        try:
            plan = plan_from_state(state["retrieval_plan"])
        except ValueError:
            return refuse_release(state, "retrieval_plan_invalid")
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
        return refuse_release(state, "web_evidence_insufficient")
    if not is_web and route_needs_retrieval(plan):
        fusion, tables = company_evidence_context(state, deps)
        state = {
            **state,
            "fusion": fusion.model_dump(mode="json"),
            "table_composition": tables.model_dump(mode="json"),
        }
    try:
        prepared = (
            payload
            if is_web
            else bind_company_atomic_links(
                payload,
                fusion=fusion,
                user_query=state.get("resolved_query") or state["user_query"] or None,
            )
        )
    except (ValidationError, ValueError, AnswerError):
        return refuse_release(state, "claim_binding_failed")
    try:
        checked, failures = deterministic_check_answer(
            prepared,
            fusion=fusion,
            tables=tables.records,
            evidence_required=route_needs_retrieval(plan) and not is_web,
            web_excerpts=web_excerpts if is_web else None,
            require_paragraphs=route_needs_retrieval(plan) and not is_web,
        )
    except (ValidationError, ValueError, AnswerError):
        return refuse_release(state, "deterministic_check_failed")
    remaining = state["remaining_model_calls"]
    verifier_calls = state.get("verifier_call_count") or 0
    verifier_link_verdicts: tuple[VerifierLinkVerdict, ...] = ()
    omitted: tuple[str, ...] = ()
    added_prompt_tokens = 0
    added_completion_tokens = 0
    verifier_skipped_reason: str | None = None
    release_failure: str | None = None
    pre_verifier = checked
    verifier_started = time.perf_counter()
    verifier_timed = bool(checked.atomic_links) and not is_web
    if verifier_timed:
        caller = None
        if deps.model_gateway is not None and deps.verifier_prompt_text:

            def _verifier_caller(links: tuple[AtomicLink, ...]) -> VerifierPayload:
                """Invoke one verifier batch through the bound gateway.

                Args:
                    links: At most six material links.

                Returns:
                    Structured verifier payload.
                """

                nonlocal added_prompt_tokens, added_completion_tokens, verifier_calls
                nonlocal verifier_link_verdicts
                context = runtime_from_state(state)

                def on_consumed(consumed: ReservationConsumeResult) -> None:
                    """Keep later settlement on the consumed reservation version."""
                    nonlocal state
                    if context is not None:
                        state = {
                            **state,
                            "authorized_runtime": runtime_after_consume(
                                context, consumed
                            ).model_dump(mode="json"),
                        }

                verifier_calls = 1
                payload, prompt_tokens, completion_tokens = gateway_verifier(
                    deps,
                    links=links,
                    fusion=fusion,
                    tables=tables.records,
                    context=context,
                    on_consumed=on_consumed,
                )
                added_prompt_tokens += prompt_tokens
                added_completion_tokens += completion_tokens
                reason_codes = {
                    "supported",
                    "unsupported",
                    "literal_mismatch",
                    "invalid_inference",
                    "insufficient_evidence",
                }
                verifier_link_verdicts = tuple(
                    verdict.model_copy(
                        update={
                            "reason": verdict.reason
                            if verdict.reason in reason_codes
                            else "unspecified"
                        }
                    )
                    for verdict in payload.link_verdicts
                )
                return payload

            caller = _verifier_caller
        try:
            if caller is not None:
                remaining = assert_call_available(remaining)
            checked, verifier_calls, omitted = run_verifier_batch(
                checked,
                caller=caller,
                already_called=verifier_calls,
                fusion=fusion,
            )
            try:
                checked = align_split_source_identifiers(
                    pre_verifier,
                    checked,
                    fusion=fusion,
                )
            except (ValidationError, ValueError, AnswerError):
                # Identifier realignment must not abort verify as run_failed.
                pass
        except (AnswerError, QueryCeilingError, QueryBudgetError) as exc:
            reason = getattr(exc, "reason", None) or str(exc) or "verifier_failed"
            verifier_skipped_reason = str(reason)[:64]
            release_failure = verifier_skipped_reason
        except VerifierAttemptError as exc:
            verifier_skipped_reason = exc.reason
            release_failure = exc.reason
        except Exception as exc:
            verifier_skipped_reason = type(exc).__name__[:64]
            release_failure = verifier_skipped_reason
    verifier_timing = (
        with_verifier_timing(
            state,
            duration_ms=max(0, int((time.perf_counter() - verifier_started) * 1000)),
            skipped_reason=verifier_skipped_reason,
        )
        if verifier_timed
        else {}
    )
    if release_failure is not None:
        return refuse_release(
            cast(QueryGraphState, {**state, **verifier_timing}),
            release_failure,
            remaining_model_calls=remaining,
            verifier_call_count=verifier_calls,
            prompt_tokens=added_prompt_tokens,
            completion_tokens=added_completion_tokens,
        )
    if company_release_applies(checked, is_web=is_web):
        user_query = state.get("resolved_query") or state["user_query"] or ""
        try:
            checked = company_release_payload(
                checked,
                fusion=fusion,
                tables=tables.records,
                user_query=user_query,
            )
        except Exception:
            return refuse_release(
                cast(QueryGraphState, {**state, **verifier_timing}),
                "answer_release_failed",
                remaining_model_calls=remaining,
                verifier_call_count=verifier_calls,
                prompt_tokens=added_prompt_tokens,
                completion_tokens=added_completion_tokens,
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
    usage_reporting: dict[str, object] | None = None
    if deps.connection is not None and context is not None:
        try:
            billed = summarize_run_usage(
                deps.connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
            )
            if billed.cost_reporting is not None:
                usage_reporting = billed.cost_reporting.model_dump(mode="json")
            billed_prompt = billed.prompt_tokens
            billed_completion = billed.completion_tokens
            if (
                billed.cost_reporting is not None
                and billed.cost_reporting.estimated_cost_usd is not None
            ):
                billed_cost_usd = float(billed.cost_reporting.estimated_cost_usd)
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
                return refuse_release(state, "web_citation_persist_failed")
    else:
        try:
            persisted = maybe_persist_verified_citations(
                deps.connection,
                caller=caller_from_runtime(context) if context is not None else None,
                run_id=context.run_id if context is not None else None,
                fusion=fusion,
                answer=checked,
            )
        except Exception as exc:
            logging.getLogger(__name__).info(
                "citation persistence failed",
                extra={
                    "event": "query.verify.citation_persist_failed",
                    "error_type": type(exc).__name__,
                    "reason": getattr(exc, "reason", "unexpected_failure"),
                    "sqlstate": sqlstate_of(exc),
                    "run_id": str(context.run_id) if context is not None else None,
                },
            )
            return refuse_release(
                cast(QueryGraphState, {**state, **verifier_timing}),
                "citation_persist_failed",
                remaining_model_calls=remaining,
                verifier_call_count=verifier_calls,
                prompt_tokens=added_prompt_tokens,
                completion_tokens=added_completion_tokens,
            )
        else:
            if persisted.skipped:
                shortened = shorten_contained_skipped_spans(
                    checked, fusion, persisted.skipped
                )
                if shortened is not checked:
                    try:
                        shortened_persisted = maybe_persist_verified_citations(
                            deps.connection,
                            caller=(
                                caller_from_runtime(context)
                                if context is not None
                                else None
                            ),
                            run_id=(context.run_id if context is not None else None),
                            fusion=fusion,
                            answer=shortened,
                        )
                    except (QueryAdmissionError, psycopg.Error):
                        shortened_persisted = None
                    if shortened_persisted is not None:
                        checked = shortened
                        persisted = shortened_persisted
            if persisted.skipped:
                skipped_citation_count = len(persisted.skipped)
                if fusion.evidence:
                    repaired = repair_leaf_citations(checked, fusion, persisted.skipped)
                    if repaired is not checked:
                        try:
                            repaired = render_verified_company_answer(
                                repaired,
                                fusion=fusion,
                                tables=tables.records,
                                user_query=state.get("resolved_query")
                                or state["user_query"]
                                or "",
                            )
                        except (ValidationError, ValueError, AnswerError):
                            pass
                        try:
                            retried = maybe_persist_verified_citations(
                                deps.connection,
                                caller=(
                                    caller_from_runtime(context)
                                    if context is not None
                                    else None
                                ),
                                run_id=(
                                    context.run_id if context is not None else None
                                ),
                                fusion=fusion,
                                answer=repaired,
                            )
                        except (QueryAdmissionError, psycopg.Error):
                            retried = None
                        if retried is not None and retried.ids:
                            checked = repaired
                            if retried.skipped:
                                skipped_citation_count = len(retried.skipped)
                                checked = drop_skipped_citations(
                                    checked, retried.skipped
                                )
                            else:
                                skipped_citation_count = 0
                            terminal = "verified_partial"
                            detail = "citation_leaf_unresolved"
                            persisted = retried
                        else:
                            checked = drop_skipped_citations(checked, persisted.skipped)
                            terminal = (
                                "verified_partial"
                                if persisted.ids
                                else "insufficient_evidence"
                            )
                            detail = "citation_leaf_unresolved"
                    else:
                        checked = drop_skipped_citations(checked, persisted.skipped)
                        terminal = (
                            "verified_partial"
                            if persisted.ids
                            else "insufficient_evidence"
                        )
                        detail = "citation_leaf_unresolved"
                elif not persisted.ids:
                    checked = drop_skipped_citations(checked, persisted.skipped)
                    terminal = "insufficient_evidence"
                    detail = "citation_leaf_unresolved"
                else:
                    checked = drop_skipped_citations(checked, persisted.skipped)
                    if terminal in {"verified", "verified_partial"}:
                        terminal = "verified_partial"
                        detail = "citation_leaf_unresolved"
    if (
        not is_web
        and terminal in {"verified", "verified_partial"}
        and has_source_code_syntax_issue(
            checked, user_query=state.get("resolved_query") or state["user_query"] or ""
        )
    ):
        checked = checked.model_copy(update={"status": "partial"})
        terminal = "verified_partial"
        detail = SOURCE_CODE_SYNTAX_INVALID
    verification_dump: dict[str, Any]
    answer_dump: dict[str, Any]
    try:
        result = VerificationResult(
            answer=checked,
            deterministic_failures=failures,
            verifier_call_count=1 if verifier_calls else 0,
            verifier_link_verdicts=verifier_link_verdicts,
            omitted_link_ids=omitted,
            verifier_skipped_reason=verifier_skipped_reason,
            skipped_citation_count=skipped_citation_count,
            status=terminal
            if terminal
            in {"verified", "verified_partial", "refused", "insufficient_evidence"}
            else "verified_partial",
        )
        verification_dump = result.model_dump(mode="json")
        answer_dump = checked.model_dump(mode="json")
    except (ValidationError, ValueError):
        return refuse_release(
            cast(QueryGraphState, {**state, **verifier_timing}),
            "payload_schema_invalid",
            remaining_model_calls=remaining,
            verifier_call_count=verifier_calls,
            prompt_tokens=added_prompt_tokens,
            completion_tokens=added_completion_tokens,
        )
    return cast(
        QueryGraphState,
        {
            **state,
            "status": terminal,
            "detail": detail,
            "answer": answer_dump,
            "verification": verification_dump,
            "remaining_model_calls": remaining,
            "verifier_call_count": verifier_calls,
            "catalog_llm_call_count": int(state.get("catalog_llm_call_count") or 0),
            "keyword_extract_count": 0,
            "prompt_tokens": billed_prompt,
            "completion_tokens": billed_completion,
            "cost_usd": billed_cost_usd,
            "cost_reporting": usage_reporting,
            **verifier_timing,
        },
    )
