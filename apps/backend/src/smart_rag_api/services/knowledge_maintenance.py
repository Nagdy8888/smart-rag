"""Bounded, consent-aware maintenance queue RPCs."""

from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from smart_rag_core.knowledge import MaintenanceItem, MaintenanceKind, MaintenanceUpdate
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole

from smart_rag_api.services.documents_http import raise_document_error


class MaintenanceService:
    """Keep authorization in SQL as well as at the service boundary."""

    def __init__(self, postgres_url: str) -> None:
        """Store the runtime DSN without opening a socket."""
        self._postgres_url = postgres_url

    def list(
        self, caller: CallerContext, *, limit: int = 50, offset: int = 0
    ) -> list[MaintenanceItem]:
        """List a bounded page of currently visible tasks."""
        self._require_admin(caller)
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        "SELECT * FROM app.list_knowledge_maintenance(%s, %s, %s, %s, %s)",
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            max(1, min(limit, 100)),
                            max(0, min(offset, 10000)),
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg.Error as exc:
            raise_document_error(exc)
        return [MaintenanceItem.model_validate(row) for row in rows]

    def update(
        self,
        caller: CallerContext,
        kind: MaintenanceKind,
        source_id: UUID,
        body: MaintenanceUpdate,
    ) -> None:
        """Assign or close a currently authorized task with optimistic concurrency."""
        self._require_admin(caller)
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                connection.execute(
                    "SELECT app.update_knowledge_maintenance(%s, %s, %s, %s, %s, %s)",
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        kind,
                        source_id,
                        Jsonb(body.model_dump(mode="json")),
                    ),
                )
        except psycopg.Error as exc:
            raise_document_error(exc)

    @staticmethod
    def _require_admin(caller: CallerContext) -> None:
        """Reject members before any report query is attempted."""
        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
