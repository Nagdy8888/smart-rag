"""Thumbs feedback and usage summaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.untrusted import isolate_untrusted_text


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """Aggregated llm_usage without prompt text."""

    cost_usd: Decimal
    prompt_tokens: int
    completion_tokens: int
    usage_rows: int
    scope: str


class FeedbackUsageService:
    """Factory-injected feedback and usage operations."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL.
        """

        self._postgres_url = postgres_url

    def submit_thumbs(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        thumbs_up: bool,
        comment: str | None,
    ) -> UUID:
        """Store thumbs feedback for an owned run.

        Args:
            caller: Authenticated caller.
            run_id: Run id.
            thumbs_up: True for up (rating 5), False for down (rating 1).
            comment: Optional untrusted correction text.

        Returns:
            Feedback row id.
        """

        rating = 5 if thumbs_up else 1
        stored_comment = isolate_untrusted_text(comment) if comment else None
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT app.submit_run_feedback(%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        run_id,
                        rating,
                        stored_comment,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        if row is None:
            raise QueryAdmissionError("database_rejected")
        return UUID(str(row[0]))

    def caller_usage(self, caller: CallerContext) -> UsageSummary:
        """Return the caller's usage totals.

        Args:
            caller: Authenticated caller.

        Returns:
            Usage summary.
        """

        return self._summarize(caller, company=False)

    def company_usage(self, caller: CallerContext) -> UsageSummary:
        """Return company totals for owner/admin.

        Args:
            caller: Authenticated caller.

        Returns:
            Usage summary.

        Raises:
            QueryAdmissionError: Members/viewers.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        return self._summarize(caller, company=True)

    def _summarize(self, caller: CallerContext, *, company: bool) -> UsageSummary:
        """Run the usage RPC.

        Args:
            caller: Authenticated caller.
            company: True for company totals.

        Returns:
            Usage summary.
        """

        fn = "app.summarize_company_usage" if company else "app.summarize_caller_usage"
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"SELECT * FROM {fn}(%s, %s, %s)",  # noqa: S608 - allow-listed fn
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise QueryAdmissionError("database_rejected")
        return UsageSummary(
            cost_usd=Decimal(str(row["cost_usd"])),
            prompt_tokens=int(row["prompt_tokens"]),
            completion_tokens=int(row["completion_tokens"]),
            usage_rows=int(row["usage_rows"]),
            scope="company" if company else "caller",
        )
