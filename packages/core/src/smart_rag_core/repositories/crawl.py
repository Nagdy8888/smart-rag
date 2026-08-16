"""Persistence for crawl runs, snapshots, and fetch provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from smart_rag_core.ingestion.crawl.adapter import (
    CrawlFetchProvenance,
    CrawlRunResult,
    WebSnapshotRecord,
)
from smart_rag_core.ingestion.crawl.policy import ApprovedCrawlScope


class CrawlRepositoryError(Exception):
    """Raised when crawl persistence fails."""


@dataclass(frozen=True, slots=True)
class CrawlRepository:
    """Worker-role repository for crawl runs and provenance tables."""

    connection: psycopg.Connection

    def load_active_approval(self, source_id: UUID) -> ApprovedCrawlScope | None:
        """Load the latest approved crawl scope for a source.

        Args:
            source_id: ``document_sources.id``.

        Returns:
            Approved scope or ``None`` when no active approval exists.
        """

        row = self.connection.execute(
            """
            SELECT
              approval_id,
              source_id,
              start_url,
              approved_domain,
              policy_version,
              max_depth,
              max_pages,
              requester_user_id,
              reviewer_user_id
            FROM app.load_active_crawl_approval(%s)
            """,
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return ApprovedCrawlScope(
            approval_id=str(row[0]),
            source_id=str(row[1]),
            start_url=str(row[2]),
            approved_domain=str(row[3]),
            policy_version=str(row[4]),
            max_depth=int(row[5]),
            max_pages=int(row[6]),
            requester_user_id=str(row[7]) if row[7] is not None else None,
            reviewer_user_id=str(row[8]) if row[8] is not None else None,
        )

    def next_crawl_version(self, source_id: UUID) -> int:
        """Return the next monotonic crawl version for a source."""

        row = self.connection.execute(
            """
            SELECT coalesce(max(crawl_version), 0) + 1
            FROM app.web_crawl_runs
            WHERE source_id = %s
            """,
            (source_id,),
        ).fetchone()
        return int(row[0]) if row is not None else 1

    def create_crawl_run(
        self,
        *,
        source_id: UUID,
        version_id: UUID | None,
        crawl_version: int,
        policy_version: str,
        start_url: str,
    ) -> UUID:
        """Insert a running crawl run row."""

        row = self.connection.execute(
            """
            INSERT INTO app.web_crawl_runs (
              source_id,
              version_id,
              crawl_version,
              policy_version,
              start_url,
              status
            )
            VALUES (%s, %s, %s, %s, %s, 'running')
            RETURNING id
            """,
            (source_id, version_id, crawl_version, policy_version, start_url),
        ).fetchone()
        if row is None:
            raise CrawlRepositoryError("crawl run insert returned no row")
        return UUID(str(row[0]))

    def persist_crawl_result(
        self,
        *,
        crawl_run_id: UUID,
        source_id: UUID,
        result: CrawlRunResult,
    ) -> None:
        """Persist snapshots, fetch events, and finalize crawl run status."""

        for event in result.fetch_events:
            self._insert_fetch_event(crawl_run_id, result.policy_version, event)
        for snapshot in result.snapshots:
            self._insert_snapshot(crawl_run_id, source_id, snapshot)
        status = "failed" if result.failure_reason else "completed"
        self.connection.execute(
            """
            UPDATE app.web_crawl_runs
            SET status = %s,
                pages_fetched = %s,
                wire_bytes_total = %s,
                decoded_bytes_total = %s,
                failure_reason = %s,
                completed_at = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (
                status,
                result.pages_fetched,
                result.wire_bytes_total,
                result.decoded_bytes_total,
                result.failure_reason,
                datetime.now(tz=UTC),
                crawl_run_id,
            ),
        )

    def _insert_fetch_event(
        self,
        crawl_run_id: UUID,
        policy_version: str,
        event: CrawlFetchProvenance,
    ) -> None:
        """Persist one fetch-event row for a crawl run.

        Args:
            crawl_run_id: Parent crawl run identifier.
            policy_version: Crawl policy version recorded on the event.
            event: Provenance for the HTTP fetch, including robots metadata.
        """

        robots_payload = None
        if event.robots is not None:
            robots_payload = json.dumps(
                {
                    "allowed": event.robots.allowed,
                    "robots_url": event.robots.robots_url,
                    "reason": event.robots.reason,
                }
            )
        self.connection.execute(
            """
            INSERT INTO app.crawl_fetch_events (
              crawl_run_id,
              requested_url,
              final_url,
              status_code,
              decision,
              reason,
              peer_ip,
              pinned_ips,
              redirect_hop,
              wire_bytes,
              decoded_bytes,
              content_type,
              robots,
              policy_version
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s
            )
            """,
            (
                crawl_run_id,
                event.requested_url,
                event.final_url,
                event.status_code,
                event.decision,
                event.reason,
                event.peer_ip,
                json.dumps(list(event.pinned_ips)),
                event.redirect_hop,
                event.wire_bytes,
                event.decoded_bytes,
                event.content_type,
                robots_payload,
                policy_version,
            ),
        )

    def _insert_snapshot(
        self,
        crawl_run_id: UUID,
        source_id: UUID,
        snapshot: WebSnapshotRecord,
    ) -> None:
        """Persist one web snapshot row for a crawl run.

        Args:
            crawl_run_id: Parent crawl run identifier.
            source_id: Document source that owns the snapshot.
            snapshot: Canonical URL, hashes, and stored object path.
        """

        self.connection.execute(
            """
            INSERT INTO app.web_snapshots (
              id,
              crawl_run_id,
              source_id,
              canonical_url,
              title,
              content_type,
              content_hash,
              storage_bucket,
              storage_path,
              wire_bytes,
              decoded_bytes,
              redirect_chain,
              peer_ip,
              pinned_ips
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb
            )
            """,
            (
                snapshot.snapshot_id,
                crawl_run_id,
                source_id,
                snapshot.canonical_url,
                snapshot.title,
                snapshot.content_type,
                snapshot.content_hash,
                snapshot.storage_bucket,
                snapshot.storage_path,
                snapshot.wire_bytes,
                snapshot.decoded_bytes,
                json.dumps(list(snapshot.redirect_chain)),
                snapshot.peer_ip,
                json.dumps(list(snapshot.pinned_ips)),
            ),
        )
