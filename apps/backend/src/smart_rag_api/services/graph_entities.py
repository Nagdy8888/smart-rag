"""Bounded ACL-filtered graph entity search."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text


@dataclass(frozen=True, slots=True)
class GraphEntityMatch:
    """One authorized entity id. No vendor prose."""

    object_id: str
    object_type: str
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    support: float


class GraphEntityService:
    """Factory-injected entity search."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL.
        """

        self._postgres_url = postgres_url

    def search(
        self, caller: CallerContext, *, query: str, limit: int = 25
    ) -> tuple[GraphEntityMatch, ...]:
        """Search authorized entity ids.

        Args:
            caller: Authenticated caller.
            query: Bounded search string.
            limit: Max 25.

        Returns:
            Matches with escaped object ids.
        """

        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        SELECT object_id, object_type, chunk_id, document_id,
                               version_id, support
                        FROM app.search_graph_entities(%s, %s, %s, %s, %s)
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            query,
                            limit,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg.Error as exc:
            raise QueryAdmissionError("invalid_query") from exc
        return tuple(
            GraphEntityMatch(
                object_id=isolate_untrusted_text(str(row["object_id"])),
                object_type=str(row["object_type"]),
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                version_id=row["version_id"],
                support=float(row["support"]),
            )
            for row in rows
        )
