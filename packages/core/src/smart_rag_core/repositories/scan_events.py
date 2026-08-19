"""Append-only scan event persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from smart_rag_core.ingestion.scan import ObjectScanResult


class ScanEventRepositoryError(Exception):
    """Raised when scan event persistence fails."""


@dataclass(frozen=True, slots=True)
class ScanEventRepository:
    """Worker-role repository for ``app.document_scan_events``."""

    connection: psycopg.Connection

    def insert_scan_event(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        uploader_user_id: UUID | None,
        session_id: str | None,
        declared_category: str | None,
        scan: ObjectScanResult,
    ) -> UUID:
        """Insert one append-only scan evidence row.

        Args:
            document_id: Canonical document id.
            version_id: Version id scanned.
            uploader_user_id: Uploader subject at scan time.
            session_id: Auth session id when known.
            declared_category: Uploader category attestation.
            scan: Normalized scan result.

        Returns:
            Inserted scan event id.

        Raises:
            ScanEventRepositoryError: On database failures or fake-clean rejection.
        """

        try:
            row = self.connection.execute(
                """
                INSERT INTO app.document_scan_events (
                  document_id,
                  version_id,
                  scan_engine_version,
                  signature_version,
                  result,
                  object_hash,
                  details,
                  uploader_user_id,
                  session_id,
                  declared_category,
                  functionality_level,
                  signature_db_timestamp,
                  network_provenance,
                  bytes_examined,
                  config_version,
                  signature_db_ids
                )
                VALUES (
                  %s, %s, %s, %s, %s::app.scan_result, %s,
                  %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb,
                  %s, %s, %s::jsonb
                )
                RETURNING id
                """,
                (
                    document_id,
                    version_id,
                    scan.scan_engine_version,
                    scan.signature_version,
                    scan.result.value,
                    scan.object_hash,
                    json.dumps(scan.details),
                    uploader_user_id,
                    session_id,
                    declared_category,
                    scan.functionality_level,
                    scan.signature_db_timestamp,
                    json.dumps({"phase": 3, "source": "clamav_instream"}),
                    scan.bytes_examined,
                    scan.config_version,
                    json.dumps(scan.signature_db_ids),
                ),
            ).fetchone()
        except psycopg.Error as exc:
            raise ScanEventRepositoryError(str(exc)) from exc
        if row is None:
            raise ScanEventRepositoryError("scan event insert returned no row")
        return UUID(str(row[0]))

    def latest_clean_scan_at(self, version_id: UUID) -> datetime | None:
        """Return timestamp of latest clean scan for a version."""

        row = self.connection.execute(
            """
            SELECT scanned_at
            FROM app.document_scan_events
            WHERE version_id = %s
              AND result = 'clean'::app.scan_result
            ORDER BY scanned_at DESC
            LIMIT 1
            """,
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        scanned_at = row[0]
        if isinstance(scanned_at, datetime):
            return scanned_at
        return None

    def has_current_clean_evidence(
        self,
        version_id: UUID,
        *,
        max_age_hours: int = 24,
    ) -> bool:
        """Return whether a clean scan exists within the freshness window.

        Args:
            version_id: Canonical version whose scan events are inspected.
            max_age_hours: Maximum age of a qualifying clean event.

        Returns:
            ``True`` when at least one clean scan is inside the window.
        """

        row = self.connection.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM app.document_scan_events AS e
              WHERE e.version_id = %s
                AND e.result = 'clean'::app.scan_result
                AND e.scanned_at >= timezone('utc', now()) - make_interval(hours => %s)
            )
            """,
            (version_id, max_age_hours),
        ).fetchone()
        return bool(row and row[0])

    def has_current_clean_hashes(
        self,
        version_id: UUID,
        object_hashes: tuple[str, ...],
        *,
        max_age_hours: int = 24,
    ) -> bool:
        """Return whether every object hash has a current clean scan event.

        Empty ``object_hashes`` fails closed.

        Args:
            version_id: Canonical version scanned.
            object_hashes: SHA-256 hex digests that must each have a clean
                current ``document_scan_events`` row.
            max_age_hours: Maximum age of a qualifying clean event.

        Returns:
            ``True`` only when every hash has a matching current clean event.
        """

        if not object_hashes:
            return False
        normalized = tuple(digest.lower() for digest in object_hashes)
        row = self.connection.execute(
            """
            SELECT COUNT(DISTINCT lower(e.object_hash))
            FROM app.document_scan_events AS e
            WHERE e.version_id = %s
              AND e.result = 'clean'::app.scan_result
              AND e.scanned_at >= timezone('utc', now()) - make_interval(hours => %s)
              AND lower(e.object_hash) = ANY(%s)
            """,
            (version_id, max_age_hours, list(normalized)),
        ).fetchone()
        return bool(row and int(row[0]) == len(set(normalized)))
