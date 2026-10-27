"""Immutable model-usage and restricted-evidence writes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

import psycopg

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.repository.errors import raise_admission
from smart_rag_core.security.identity import CallerContext


def record_query_llm_usage(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    reservation_id: UUID,
    reservation_version: int,
    usage_kind: str,
    model_id: str,
    provider_attempt_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
    timeout_after_send: bool,
    cost_basis: str | None = None,
    estimated_cost_usd: Decimal | None = None,
    provider_prompt_tokens: int | None = None,
    provider_completion_tokens: int | None = None,
    cached_prompt_tokens: int = 0,
    cache_write_30m_tokens: int | None = None,
    cache_write_12h_tokens: int | None = None,
    service_tier: str | None = None,
) -> UUID:
    """Append one immutable ``llm_usage`` row for a provider attempt.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        run_id: Admitted query run.
        reservation_id: Run-local reservation.
        reservation_version: Version observed at consume time.
        usage_kind: Allow-listed usage kind.
        model_id: Provider model identifier.
        provider_attempt_id: Idempotent attempt id.
        prompt_tokens: Actual or estimated prompt tokens.
        completion_tokens: Actual or estimated completion tokens.
        cost_usd: Actual or estimated USD.
        timeout_after_send: True when the HTTP response was lost after send.
        cost_basis: Explicit estimate provenance, or None for legacy callers.
        estimated_cost_usd: Reporting estimate; null for safety allowances.
        provider_prompt_tokens: Observed input count, absent when unknown.
        provider_completion_tokens: Observed output count, absent when unknown.
        cached_prompt_tokens: Observed cached subset of provider input.
        cache_write_30m_tokens: Observed short-lived cache writes.
        cache_write_12h_tokens: Observed long-lived cache writes.
        service_tier: Returned provider processing tier.

    Returns:
        ``llm_usage.id``.

    Raises:
        QueryAdmissionError: When authorization or kind validation fails.

    Side Effects:
        Inserts an append-only usage row. Duplicate attempt ids are no-ops.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.record_query_llm_usage(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    reservation_id,
                    reservation_version,
                    usage_kind,
                    model_id,
                    provider_attempt_id,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    timeout_after_send,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("usage_returned_no_row")
    usage_id = UUID(str(row[0]))
    if cost_basis is not None:
        try:
            connection.execute(
                "SELECT app.record_usage_cost_basis(%s,%s,%s,%s,%s,%s)",
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    usage_id,
                    cost_basis,
                    estimated_cost_usd,
                ),
            )
        except psycopg.Error as exc:
            raise_admission(exc)
    if provider_prompt_tokens is not None and provider_completion_tokens is not None:
        try:
            connection.execute(
                "SELECT app.record_usage_token_measurement(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    usage_id,
                    provider_prompt_tokens,
                    provider_completion_tokens,
                    cached_prompt_tokens,
                    cache_write_30m_tokens,
                    cache_write_12h_tokens,
                    service_tier,
                ),
            )
        except psycopg.Error as exc:
            raise_admission(exc)
    return usage_id


def record_run_restricted_evidence(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    document_id: UUID,
    version_id: UUID,
    session_id: str,
    citation_id: UUID | None = None,
    purpose: Literal["evidence", "preview", "download"] = "evidence",
    signed_url_expires_at: datetime | None = None,
) -> UUID:
    """Append a content-minimized restricted-read event for a completed run.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived actor.
        run_id: Run that included the restricted evidence.
        document_id: Restricted document.
        version_id: Current version id.
        session_id: Bounded session identifier.
        citation_id: Optional citation row, never passage text.
        purpose: ``evidence``, ``preview``, or ``download``.
        signed_url_expires_at: Required only for ``download``.

    Returns:
        ``restricted_read_events.id``.

    Raises:
        QueryAdmissionError: When ACL, purpose, or caller checks fail.

    Side Effects:
        Calls the chained ``append_audit_event`` path and inserts one
        ``restricted_read_events`` row without passage text.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.record_run_restricted_evidence(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    document_id,
                    version_id,
                    session_id,
                    citation_id,
                    purpose,
                    signed_url_expires_at,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("restricted_evidence_returned_no_row")
    return UUID(str(row[0]))
