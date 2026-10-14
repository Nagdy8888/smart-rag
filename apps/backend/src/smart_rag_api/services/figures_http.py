"""ACL-checked figure PNG reads."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.security.identity import CallerContext

from smart_rag_api.storage_admin.objects import StorageAdminError, download_object
from smart_rag_api.storage_admin.settings import load_privileged_storage_settings

FIGURE_READ_SQL = """
SELECT f.storage_bucket, f.storage_path
FROM app.document_figures AS f
JOIN app.document_versions AS v
  ON v.id = f.version_id
 AND v.is_current
WHERE f.figure_key = %s
  AND app.caller_can_read_document(%s::uuid, %s, f.document_id)
"""


class FigureReadError(RuntimeError):
    """The figure exists in metadata but the object could not be read."""


class FigureHttpService:
    """Factory-injected figure downloads."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Transaction-pooler URL. Never logged.
        """

        self._postgres_url = postgres_url

    def read_png(self, caller: CallerContext, figure_key: str) -> bytes | None:
        """Return PNG bytes for one current figure the caller may read.

        Args:
            caller: Authenticated caller.
            figure_key: Stable figure id.

        Returns:
            PNG bytes, or None when the row is missing or forbidden.

        Raises:
            FigureReadError: When metadata exists but storage download fails.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    FIGURE_READ_SQL,
                    (
                        figure_key,
                        caller.user_id,
                        caller.rpc_role(),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        try:
            settings = load_privileged_storage_settings()
            return download_object(
                settings,
                bucket=str(row["storage_bucket"]),
                object_path=str(row["storage_path"]),
            )
        except (StorageAdminError, ValueError, OSError) as exc:
            raise FigureReadError("figure_object_unavailable") from exc
