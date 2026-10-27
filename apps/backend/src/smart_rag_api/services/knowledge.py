"""Authorized company-knowledge metadata transport; no browser table access."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from smart_rag_core.knowledge import (
    ConversationKnowledgeScope,
    DocumentGovernance,
    KnowledgeResult,
    UpdateDocumentGovernance,
    UpdateKnowledgeScope,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole

from smart_rag_api.services.documents_http import raise_document_error


class KnowledgeService:
    """Execute the narrowly granted canonical governance RPCs."""

    def __init__(self, postgres_url: str) -> None:
        """Store the runtime DSN without opening a connection."""
        self._postgres_url = postgres_url

    def governance(
        self,
        caller: CallerContext,
        document_id: UUID,
        body: UpdateDocumentGovernance | None = None,
        *,
        version_id: UUID | None = None,
    ) -> DocumentGovernance:
        """Read visible metadata or atomically update it as owner/admin."""
        if body is not None and caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        params: tuple[object, ...] = (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            document_id,
        )
        sql = "SELECT app.get_document_governance(%s, %s, %s, %s)"
        if version_id is not None:
            sql = "SELECT app.get_document_governance(%s, %s, %s, %s, %s)"
            params = (*params, version_id)
        if body is not None:
            sql = "SELECT app.update_document_governance(%s, %s, %s, %s, %s)"
            params = (*params, Jsonb(body.model_dump(mode="json")))
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                row = connection.execute(sql, params).fetchone()
        except psycopg.Error as exc:
            raise_document_error(exc)
        if row is None or row[0] is None:
            raise QueryAdmissionError("not_found")
        return DocumentGovernance.model_validate(row[0])

    def outcome(self, caller: CallerContext, run_id: UUID) -> KnowledgeResult | None:
        """Return an owned run's persisted outcome; legacy records stay unknown."""
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                row = connection.execute(
                    "SELECT app.get_run_knowledge_result(%s, %s, %s, %s)",
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        run_id,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            raise_document_error(exc)
        if row is None or row[0] is None:
            raise QueryAdmissionError("not_found")
        return KnowledgeResult.model_validate(row[0]) if row[0] else None

    def governance_versions(
        self, caller: CallerContext, document_id: UUID
    ) -> list[DocumentGovernance]:
        """List the latest fifty version metadata records for privileged review."""
        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        self.governance(caller, document_id)
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                rows = connection.execute(
                    """SELECT app.get_document_governance(%s,%s,%s,%s,v.id)
                       FROM app.document_versions v WHERE v.document_id=%s AND v.deleted_at IS NULL
                       ORDER BY v.version_number DESC LIMIT 50""",
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        document_id,
                        document_id,
                    ),
                ).fetchall()
        except psycopg.Error as exc:
            raise_document_error(exc)
        return [
            DocumentGovernance.model_validate(row[0])
            for row in rows
            if row[0] is not None
        ]

    def scope(
        self,
        caller: CallerContext,
        conversation_id: UUID,
        body: UpdateKnowledgeScope | None = None,
    ) -> ConversationKnowledgeScope:
        """Read or change a creator-owned selection without granting evidence access."""
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                row = connection.execute(
                    "SELECT app.conversation_knowledge_scope(%s,%s,%s,%s,%s,%s)",
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        conversation_id,
                        body is not None,
                        body.document_id if body else None,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            raise_document_error(exc)
        if row is None or row[0] is None:
            raise QueryAdmissionError("not_found")
        return ConversationKnowledgeScope.model_validate(row[0])
