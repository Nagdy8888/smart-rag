"""Assemble ordered canonical chunk text for graph insertion.

There is no ``document_versions.normalized_text`` column. Packet 3 concatenates
``app.document_chunks.raw_text`` in ``chunk_index`` order.
"""

from __future__ import annotations

from uuid import UUID

import psycopg


class GraphSourceTextError(ValueError):
    """Raised when version text cannot be assembled for graph insert."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable reason.

        Args:
            reason: Short reason such as ``version_text_empty``.
        """

        super().__init__(reason)
        self.reason = reason


def load_version_graph_text(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> str:
    """Return ordered canonical chunk text for one document version.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version whose chunks are concatenated.

    Returns:
        Version text joined with blank lines.

    Raises:
        GraphSourceTextError: If no undeleted chunks exist.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT raw_text
            FROM app.document_chunks
            WHERE version_id = %s
              AND deleted_at IS NULL
            ORDER BY chunk_index ASC
            """,
            (version_id,),
        )
        rows = cursor.fetchall()
    parts = [str(row[0]) for row in rows if row[0] is not None and str(row[0])]
    if not parts:
        raise GraphSourceTextError("version_text_empty")
    return "\n\n".join(parts)
