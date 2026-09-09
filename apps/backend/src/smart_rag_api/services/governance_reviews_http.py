"""Owner/admin detector-finding review HTTP wrapper."""

from __future__ import annotations

from uuid import UUID

import psycopg
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole


class GovernanceReviewHttpService:
    """Factory-injected detector review RPC caller."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL used with ``SET ROLE app_api``.
        """

        self._postgres_url = postgres_url

    def review_finding(
        self,
        caller: CallerContext,
        *,
        finding_id: UUID,
        decision: str,
        reason: str,
        idempotency_key: str,
    ) -> tuple[UUID, UUID, str, bool]:
        """Submit one owner/admin detector review through the ACL RPC.

        Args:
            caller: Authenticated caller. Members and viewers look missing.
            finding_id: Worker-authored finding id.
            decision: ``false_positive``, ``upheld``, or ``rejected``.
            reason: Reviewer rationale, 1-500 characters.
            idempotency_key: Replay key per finding.

        Returns:
            ``(review_id, finding_id, decision, replayed)``.

        Raises:
            QueryAdmissionError: ``not_found`` for unauthorized or missing
                findings so existence is not leaked.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("not_found")
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            row = connection.execute(
                """
                SELECT review_id, finding_id, decision, replayed
                FROM app.review_detector_finding(
                  %s::uuid, %s::text, %s::bigint, %s::uuid, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    finding_id,
                    decision,
                    reason,
                    idempotency_key,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise QueryAdmissionError("not_found")
        return UUID(str(row[0])), UUID(str(row[1])), str(row[2]), bool(row[3])
