"""Owner/admin approved website crawl enqueue service."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.policy import normalize_url

CRAWL_SERVER_CONTENT_CLASS = "real_company"
CRAWL_SERVER_GRAPH_ELIGIBLE = False


class CrawlEnqueueError(Exception):
    """Raised when approved crawl enqueue fails closed."""


@dataclass(frozen=True, slots=True)
class CrawlEnqueueOutcome:
    """Durable identifiers after crawl enqueue."""

    document_id: UUID
    version_id: UUID
    source_id: UUID
    approval_id: UUID
    job_id: UUID


def enqueue_approved_website_crawl(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    start_url: str,
    approved_domain: str,
    idempotency_key: str,
    document_title: str | None,
    max_depth: int,
    max_pages: int,
    content_class: str,
    graph_eligible: bool,
    attestation_policy_version: str | None,
) -> CrawlEnqueueOutcome:
    """Validate URL scope and insert source, approval, and crawl job.

    Client ``content_class`` and ``graph_eligible`` are ignored even for
    owner/admin. Server policy forces ``real_company`` and
    ``graph_eligible=false``. Owner/admin is still required to enqueue.
    ``source_approval_requests`` records the approval in the same RPC.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role text.
        caller_authorization_version: Live authorization snapshot.
        start_url: Approved crawl start URL.
        approved_domain: Host or registrable domain matching the start URL.
        idempotency_key: Stable client key; duplicate calls return one job.
        document_title: Optional document title; defaults to the start URL.
        max_depth: Crawl depth bound (1-5).
        max_pages: Page bound (1-200).
        content_class: Ignored client hint; not used as authority.
        graph_eligible: Ignored client hint; server forces false.
        attestation_policy_version: Optional attestation policy identifier.

    Returns:
        Created or reused document/source/job identifiers.

    Raises:
        CrawlEnqueueError: When URL policy, domain match, or the RPC rejects.

    Side Effects:
        Inserts document, version, source, approved scope, and ``website_crawl``
        job rows through ``app.enqueue_approved_website_crawl``.
    """

    _ = content_class
    _ = graph_eligible
    try:
        normalized = normalize_url(start_url)
    except CrawlPolicyError as exc:
        raise CrawlEnqueueError(str(exc)) from exc
    domain = approved_domain.lower().strip()
    if domain not in {normalized.host, normalized.registrable_domain}:
        raise CrawlEnqueueError("approved_domain does not match start_url host")
    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM app.enqueue_approved_website_crawl(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        normalized.normalized,
                        domain,
                        document_title,
                        idempotency_key,
                        max_depth,
                        max_pages,
                        CRAWL_SERVER_CONTENT_CLASS,
                        CRAWL_SERVER_GRAPH_ELIGIBLE,
                        attestation_policy_version,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        raise CrawlEnqueueError(str(exc)) from exc
    if row is None:
        raise CrawlEnqueueError("enqueue_approved_website_crawl returned no row")
    return CrawlEnqueueOutcome(
        document_id=UUID(str(row["document_id"])),
        version_id=UUID(str(row["version_id"])),
        source_id=UUID(str(row["source_id"])),
        approval_id=UUID(str(row["approval_id"])),
        job_id=UUID(str(row["job_id"])),
    )
