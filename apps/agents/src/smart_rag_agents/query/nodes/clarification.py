"""One focused clarification using the existing counted preparation call."""

from uuid import UUID

import psycopg
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import QueryPreparation
from smart_rag_core.query_routing.models.plan import Phase6Extension
from smart_rag_core.query_routing.preparation import caller_from_runtime


def clarification_query(
    connection: psycopg.Connection | None, context: AuthorizedRuntimeContext, query: str
) -> tuple[str, bool, bool]:
    """Resume persisted context after ordinary admission; no new model call."""
    if connection is None or context.requested_search_scope.value in {"general", "web"}:
        return query, False, False
    row = connection.execute(
        "SELECT knowledge_reliability_enabled FROM app.company_settings"
    ).fetchone()
    if row is None or not row[0]:
        return query, False, False
    caller = caller_from_runtime(context)
    result = connection.execute(
        "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,NULL)",
        (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            context.run_id,
            query,
        ),
    ).fetchone()
    connection.commit()
    if result is None:
        raise ValueError("clarification_context_unavailable")
    return str(result[0]["query"]), bool(result[0]["resumed"]), True


def persist_clarification(
    connection: psycopg.Connection | None,
    context: AuthorizedRuntimeContext,
    preparation: QueryPreparation,
    *,
    enabled: bool,
    resumed: bool,
) -> QueryPreparation:
    """Persist one question, or suppress repeats after a clarification reply."""
    question = preparation.clarification_question
    if resumed and preparation.knowledge_scope is KnowledgeScope.AMBIGUOUS:
        return preparation.model_copy(
            update={
                "clarification_question": None,
                "knowledge_scope": KnowledgeScope.COMPANY_DOCUMENTS,
                "scope_degradation_reason": None,
                "phase6_extension": Phase6Extension.NONE,
            }
        )
    if not enabled or resumed or not question or connection is None:
        return preparation.model_copy(update={"clarification_question": None})
    if preparation.knowledge_scope not in {
        KnowledgeScope.COMPANY_DOCUMENTS,
        KnowledgeScope.AMBIGUOUS,
    }:
        return preparation.model_copy(update={"clarification_question": None})
    question = question.strip()
    if not question or question.count("?") + question.count("؟") > 1:
        return preparation.model_copy(update={"clarification_question": None})
    caller = caller_from_runtime(context)
    connection.execute(
        "SELECT app.prepare_knowledge_clarification(%s,%s,%s,%s,%s,%s)",
        (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            UUID(str(context.run_id)),
            preparation.original,
            question,
        ),
    )
    connection.commit()
    return preparation.model_copy(
        update={
            "clarification_question": question,
            "knowledge_scope": KnowledgeScope.AMBIGUOUS,
            "scope_degradation_reason": None,
            "phase6_extension": Phase6Extension.NO_RETRIEVAL,
        }
    )
