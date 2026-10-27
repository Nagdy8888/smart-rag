"""Thumbs feedback and usage summaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.feedback.tags import FeedbackTagError, require_feedback_tag
from smart_rag_core.gateways.cost_reporting import CostReporting
from smart_rag_core.observability.checkpoint_usage import (
    CheckpointUsageSummary,
    combined_usage_cost,
)
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
    cost_reporting: CostReporting | None = None
    checkpoint_usage: CheckpointUsageSummary | None = None
    display_cost_usd: Decimal | None = None


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
        tag: str,
        share_with_reviewers: bool = False,
    ) -> UUID:
        """Store thumbs feedback for an owned run.

        Args:
            caller: Authenticated caller.
            run_id: Run id.
            thumbs_up: True for up (rating 5), False for down (rating 1).
            comment: Optional untrusted correction text.
            tag: Required unmerged Phase 6 feedback tag.
            share_with_reviewers: Explicit consent to share this run for knowledge review.

        Returns:
            Feedback row id.

        Raises:
            QueryAdmissionError: ``invalid_tag``, ``not_found``, or database
                rejection.
        """

        rating = 5 if thumbs_up else 1
        stored_comment = isolate_untrusted_text(comment) if comment else None
        try:
            stored_tag = require_feedback_tag(tag)
        except FeedbackTagError as exc:
            raise QueryAdmissionError("invalid_tag") from exc
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT app.submit_run_feedback(
                          %s::uuid,
                          %s::text,
                          %s::bigint,
                          %s::uuid,
                          %s::smallint,
                          %s::text,
                          %s::text
                        )
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            run_id,
                            rating,
                            stored_comment,
                            stored_tag,
                        ),
                    )
                    row = cursor.fetchone()
                    if share_with_reviewers and row is not None:
                        cursor.execute(
                            "SELECT app.share_knowledge_feedback(%s, %s, %s, %s)",
                            (
                                caller.user_id,
                                caller.rpc_role(),
                                caller.rpc_authorization_version(),
                                row[0],
                            ),
                        )
                connection.commit()
        except psycopg.Error as exc:
            message = str(exc)
            if "feedback:invalid_tag" in message:
                raise QueryAdmissionError("invalid_tag") from exc
            if "feedback:not_found" in message:
                raise QueryAdmissionError("not_found") from exc
            if "feedback:invalid_rating" in message:
                raise QueryAdmissionError("invalid_rating") from exc
            raise QueryAdmissionError("database_rejected") from exc
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
                cursor.execute(
                    "SELECT app.summarize_usage_cost_reporting(%s,%s,%s,%s) AS reporting",
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        company,
                    ),
                )
                report = cursor.fetchone()
                cursor.execute(
                    "SELECT app.summarize_checkpoint_usage(%s,%s,%s,%s) AS history",
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        company,
                    ),
                )
                history_row = cursor.fetchone()
        if row is None:
            raise QueryAdmissionError("database_rejected")
        reporting = (
            CostReporting.model_validate(report["reporting"]) if report else None
        )
        history = (
            CheckpointUsageSummary.model_validate(history_row["history"])
            if history_row
            else None
        )
        return UsageSummary(
            cost_usd=Decimal(str(row["cost_usd"])),
            prompt_tokens=((reporting.measured_prompt_tokens or 0) if reporting else 0)
            + (history.additional_prompt_tokens if history else 0),
            completion_tokens=(
                (reporting.measured_completion_tokens or 0) if reporting else 0
            )
            + (history.additional_completion_tokens if history else 0),
            usage_rows=int(row["usage_rows"]),
            scope="company" if company else "me",
            cost_reporting=reporting,
            checkpoint_usage=history,
            display_cost_usd=combined_usage_cost(
                reporting.estimated_cost_usd if reporting else None,
                history,
                ledger_operations=reporting.estimated_operations if reporting else 0,
            ),
        )
