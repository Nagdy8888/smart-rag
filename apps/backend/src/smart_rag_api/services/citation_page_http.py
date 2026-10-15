"""ACL-checked render of one citation PDF page. No Storage URL."""

from __future__ import annotations

from uuid import UUID

import fitz
import psycopg
from psycopg.rows import dict_row
from smart_rag_core.ingestion.parser.page_image import (
    CitationPageImageError,
    render_pdf_page_png,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext

from smart_rag_api.storage_admin.objects import StorageAdminError, download_object
from smart_rag_api.storage_admin.settings import load_privileged_storage_settings

CITATION_PAGE_OBJECT_SQL = """
SELECT storage_bucket, storage_path, pdf_page_number
FROM app.get_citation_page_object_v1(%s, %s, %s, %s, %s)
"""


class CitationPageReadError(RuntimeError):
    """The citation is authorized but the page image could not be produced."""


class CitationPageService:
    """Render one current PDF page for an owned citation."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Transaction-pooler URL. Never logged.
        """

        self._postgres_url = postgres_url

    def read_png(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        citation_id: UUID,
    ) -> bytes:
        """Return a PNG of the cited file page.

        Args:
            caller: Authenticated caller.
            run_id: Owning run.
            citation_id: Citation on that run.

        Returns:
            PNG bytes for that one page.

        Raises:
            QueryAdmissionError: ``not_found`` when the citation is foreign,
                unavailable, or not a company PDF page.
            CitationPageReadError: When storage or rendering fails. The
                message does not include the object path or image bytes.
        """

        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        CITATION_PAGE_OBJECT_SQL,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            run_id,
                            citation_id,
                        ),
                    )
                    row = cursor.fetchone()
        except psycopg.Error as exc:
            if "query_admission:not_found" in str(exc):
                raise QueryAdmissionError("not_found") from exc
            raise CitationPageReadError("citation_page_unavailable") from exc
        if row is None:
            raise QueryAdmissionError("not_found")
        page_number = row.get("pdf_page_number")
        bucket = row.get("storage_bucket")
        object_path = row.get("storage_path")
        if (
            not isinstance(page_number, int)
            or not isinstance(bucket, str)
            or not isinstance(object_path, str)
        ):
            raise QueryAdmissionError("not_found")
        try:
            settings = load_privileged_storage_settings()
            pdf_bytes = download_object(
                settings,
                bucket=bucket,
                object_path=object_path,
                timeout_seconds=20.0,
            )
            return render_pdf_page_png(pdf_bytes, page_number)
        except (
            CitationPageImageError,
            StorageAdminError,
            ValueError,
            OSError,
            RuntimeError,
            fitz.FileDataError,
        ) as exc:
            raise CitationPageReadError("citation_page_unavailable") from exc
