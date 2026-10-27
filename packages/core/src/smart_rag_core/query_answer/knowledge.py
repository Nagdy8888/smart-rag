"""Authority recheck at final company release, including graph/table sources."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from smart_rag_core.knowledge import DocumentGovernance, KnowledgeResult
from smart_rag_core.query_admission.messages import append_query_message
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.security.identity import CallerContext


def load_run_scope(
    connection: psycopg.Connection, caller: CallerContext, run_id: UUID
) -> tuple[str, str] | None:
    """Recheck the immutable run selection against current ACL/version state."""
    row = connection.execute(
        "SELECT app.get_run_knowledge_scope(%s,%s,%s,%s)",
        (caller.user_id, caller.rpc_role(), caller.rpc_authorization_version(), run_id),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0]["document_id"]), str(row[0]["version_id"])


def load_governance(
    connection: psycopg.Connection,
    caller: CallerContext,
    document_ids: tuple[str, ...],
) -> dict[str, DocumentGovernance]:
    """Batch-read at most fifteen documents through the ACL-checking RPC."""
    if len(document_ids) > 15:
        raise ValueError("governance_batch_exceeded")
    if not document_ids:
        return {}
    rows = connection.execute(
        """SELECT id, app.get_document_governance(%s, %s, %s, id)
           FROM unnest(%s::uuid[]) AS ids(id)""",
        (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            [UUID(value) for value in document_ids],
        ),
    ).fetchall()
    return {
        str(row[0]): DocumentGovernance.model_validate(row[1])
        for row in rows
        if row[1] is not None
    }


def authority_allows(record: DocumentGovernance | None, version_id: str) -> bool:
    """Reject stale, unauthorized, draft, replaced, or future-effective evidence."""
    if record is None or str(record.version_id) != version_id:
        return False
    if not record.reliability_enabled:
        return True
    return record.authority_status in {"approved", "unreviewed"} and (
        record.effective_at is None or record.effective_at <= datetime.now(UTC)
    )


def filter_authority(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    records: dict[str, DocumentGovernance],
) -> tuple[FusionResult, tuple[TableEvidenceRecord, ...]]:
    """Recheck all company branches at one common final-release boundary."""
    return fusion.model_copy(
        update={
            "evidence": tuple(
                item
                for item in fusion.evidence
                if authority_allows(records.get(item.document_id), item.version_id)
            )
        }
    ), tuple(
        item
        for item in tables
        if authority_allows(records.get(item.document_id), item.version_id)
    )


def knowledge_result(
    answer: AnswerPayload,
    *,
    warnings: tuple[str, ...] = (),
    conflict: bool = False,
) -> KnowledgeResult:
    """Label only checked answers; never convert an operational error to support."""
    if conflict:
        outcome = "conflicting_evidence"
    elif answer.status == "refused":
        outcome = "insufficient_evidence"
    elif answer.status == "partial":
        outcome = "partial"
    else:
        outcome = "supported"
    return KnowledgeResult(
        outcome=outcome, limitations=tuple(dict.fromkeys(warnings))[:12]
    )


def persist_knowledge_result(
    connection: psycopg.Connection,
    caller: CallerContext,
    run_id: UUID,
    result: KnowledgeResult,
    *,
    conversation_id: UUID,
    answer_text: str,
) -> None:
    """Persist the same checked outcome before emitting its terminal events."""
    append_query_message(
        connection,
        caller=caller,
        conversation_id=conversation_id,
        run_id=run_id,
        role="assistant",
        content=answer_text,
    )
    connection.execute(
        "SELECT app.record_run_knowledge_result(%s, %s, %s, %s, %s)",
        (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            run_id,
            Jsonb(result.model_dump(mode="json")),
        ),
    )
    connection.commit()
