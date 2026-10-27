"""Attach the durable company outcome only after final checked release."""

from __future__ import annotations

import logging
from typing import cast

from smart_rag_core.query_answer.knowledge import (
    authority_allows,
    filter_authority,
    knowledge_result,
    load_governance,
    load_run_scope,
    persist_knowledge_result,
)
from smart_rag_core.query_answer.models import AnswerPayload, TableComposition
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.preparation import caller_from_runtime

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import runtime_from_state
from smart_rag_agents.query.nodes.state_codec import (
    fusion_from_state,
    tables_from_state,
)
from smart_rag_agents.query.state import QueryGraphState

LOGGER = logging.getLogger(__name__)


def company_evidence_context(
    state: QueryGraphState, deps: QueryGraphDeps
) -> tuple[FusionResult, TableComposition]:
    """Apply current authority and immutable scope before any answer-model send."""
    fusion = fusion_from_state(state.get("fusion"))
    tables = tables_from_state(state.get("table_composition"))
    context = runtime_from_state(state)
    if deps.connection is None or context is None:
        return fusion, tables
    caller = caller_from_runtime(context)
    selected = load_run_scope(deps.connection, caller, context.run_id)
    if selected is not None:
        fusion = fusion.model_copy(
            update={
                "evidence": tuple(
                    item
                    for item in fusion.evidence
                    if (item.document_id, item.version_id) == selected
                )
            }
        )
        tables = tables.model_copy(
            update={
                "records": tuple(
                    item
                    for item in tables.records
                    if (item.document_id, item.version_id) == selected
                )
            }
        )
    records = load_governance(
        deps.connection,
        caller,
        tuple(
            dict.fromkeys(
                item.document_id for item in (*fusion.evidence, *tables.records)
            )
        ),
    )
    fusion, kept_tables = filter_authority(fusion, tables.records, records)
    return fusion, tables.model_copy(update={"records": kept_tables})


def annotate_knowledge_result(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Recheck cited authority and persist the same outcome sent to the browser."""
    if deps.connection is None or state.get("answer") is None:
        return state
    if str(state.get("detail") or "").startswith("verification_unavailable:"):
        return state
    answer = AnswerPayload.model_validate(state["answer"])
    if state.get("status") == "verified_partial" and answer.status == "complete":
        answer = answer.model_copy(update={"status": "partial"})
    if answer.answer_origin is not KnowledgeScope.COMPANY_DOCUMENTS:
        return state
    context = runtime_from_state(state)
    if context is None:
        return state
    row = deps.connection.execute(
        "SELECT knowledge_reliability_enabled FROM app.company_settings"
    ).fetchone()
    if row is None or not row[0]:
        return state
    fusion = fusion_from_state(state.get("fusion"))
    tables = tables_from_state(state.get("table_composition"))
    chunk_ids = {item.chunk_id for item in answer.citations}
    table_ids = {item.table_id for item in (*answer.citations, *answer.table_citations)}
    used = (
        *tuple(item for item in fusion.evidence if item.chunk_id in chunk_ids),
        *tuple(item for item in tables.records if item.table_id in table_ids),
    )
    caller = caller_from_runtime(context)
    records = load_governance(
        deps.connection, caller, tuple(dict.fromkeys(item.document_id for item in used))
    )
    if any(
        not authority_allows(records.get(item.document_id), item.version_id)
        for item in used
    ):
        raise ValueError("source_authority_changed")
    warnings = tuple(code for record in records.values() for code in record.warnings())
    conflict = (
        bool(state.get("knowledge_conflict"))
        and answer.status != "refused"
        and len(answer.citations) >= 2
    )
    result = knowledge_result(
        answer,
        warnings=(*warnings, "source_values_conflict") if conflict else warnings,
        conflict=conflict,
    )
    if answer.status in {"partial", "refused"}:
        headings: list[str] = []
        for branch in state.get("branch_results") or []:
            raw = branch.get("uncovered_headings")
            if isinstance(raw, list):
                headings.extend(
                    item[:200]
                    for item in cast(list[object], raw)
                    if isinstance(item, str)
                )
        result = result.model_copy(
            update={"unanswered_parts": tuple(dict.fromkeys(headings))[:3]}
        )
    persist_knowledge_result(
        deps.connection,
        caller,
        context.run_id,
        result,
        conversation_id=context.conversation_id,
        answer_text=answer.answer_text,
    )
    LOGGER.info(
        "company knowledge outcome recorded",
        extra={
            "event": "query.knowledge_outcome",
            "run_id": str(context.run_id),
            "knowledge_outcome": result.outcome,
            "source_warning_count": len(result.limitations),
            "unanswered_part_count": len(result.unanswered_parts),
        },
    )
    answer = answer.model_copy(update={"knowledge_result": result})
    verification = state.get("verification")
    return {
        **state,
        "answer": answer.model_dump(mode="json"),
        "verification": {**verification, "answer": answer.model_dump(mode="json")}
        if verification is not None
        else None,
    }
