"""Worker-authored detector findings and hash-bound review coverage."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from smart_rag_core.ingestion.detectors import DetectorFamilyOutcome
from smart_rag_core.security.external_processing import DetectorResult


class GovernanceReviewRepositoryError(Exception):
    """Raised when detector finding persistence or coverage lookup fails."""


@dataclass(frozen=True, slots=True)
class GovernanceReviewRepository:
    """Worker-role repository for detector findings and review coverage."""

    connection: psycopg.Connection

    def insert_positive_findings(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        content_hash: str,
        scan_evidence_id: UUID,
        attestation_policy_version: str,
        detector_policy_version: str,
        finding_scope: str,
        outcomes: tuple[DetectorFamilyOutcome, ...],
    ) -> tuple[UUID, ...]:
        """Insert fingerprint-only rows for positive detector families.

        Args:
            document_id: Canonical document id.
            version_id: Version scanned or parsed.
            content_hash: Object SHA-256 hex digest.
            scan_evidence_id: Current ``document_scan_events`` row.
            attestation_policy_version: Uploader attestation policy pin.
            detector_policy_version: ``detectors-v1`` pin.
            finding_scope: ``metadata`` or ``extraction``.
            outcomes: Family outcomes. Clean families are skipped.

        Returns:
            Inserted finding ids.

        Raises:
            GovernanceReviewRepositoryError: On invalid scope or SQL failure.
        """

        if finding_scope not in {"metadata", "extraction"}:
            raise GovernanceReviewRepositoryError("invalid_finding_scope")
        inserted: list[UUID] = []
        try:
            for outcome in outcomes:
                if outcome.result is not DetectorResult.POSITIVE:
                    continue
                row = self.connection.execute(
                    """
                    INSERT INTO app.detector_findings (
                      document_id,
                      version_id,
                      content_hash,
                      scan_evidence_id,
                      attestation_policy_version,
                      detector_policy_version,
                      detector_family,
                      finding_scope,
                      bounded_count,
                      locator_fingerprint
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        document_id,
                        version_id,
                        content_hash,
                        scan_evidence_id,
                        attestation_policy_version,
                        detector_policy_version,
                        outcome.family,
                        finding_scope,
                        outcome.bounded_count,
                        outcome.locator_fingerprint,
                    ),
                ).fetchone()
                if row is None:
                    raise GovernanceReviewRepositoryError("finding_insert_empty")
                inserted.append(UUID(str(row[0])))
        except psycopg.Error as exc:
            raise GovernanceReviewRepositoryError(str(exc)) from exc
        return tuple(inserted)

    def latest_scan_evidence_id(self, version_id: UUID) -> UUID | None:
        """Return the latest scan event id for one version.

        Args:
            version_id: Document version.

        Returns:
            Scan event id, or ``None`` when no event exists.
        """

        row = self.connection.execute(
            """
            SELECT id
            FROM app.document_scan_events
            WHERE version_id = %s
            ORDER BY scanned_at DESC
            LIMIT 1
            """,
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        return UUID(str(row[0]))

    def reviews_cover(
        self,
        *,
        version_id: UUID,
        content_hash: str,
        scan_evidence_id: UUID,
        attestation_policy_version: str,
        detector_policy_version: str,
        required_families: tuple[str, ...],
    ) -> bool:
        """Return whether every positive family has an active false-positive.

        Args:
            version_id: Document version.
            content_hash: Object hash that must still match scan evidence.
            scan_evidence_id: Scan row that must remain clean.
            attestation_policy_version: Attestation pin on the findings.
            detector_policy_version: Detector policy pin.
            required_families: Distinct positive families that need coverage.

        Returns:
            True when no families are required or every family is reviewed.
            Stale scan, hash drift, or incomplete families return False.
        """

        if not required_families:
            return True
        try:
            row = self.connection.execute(
                """
                SELECT app.detector_reviews_cover_version(
                  %s::uuid,
                  %s,
                  %s::uuid,
                  %s,
                  %s,
                  %s::text[]
                )
                """,
                (
                    version_id,
                    content_hash,
                    scan_evidence_id,
                    attestation_policy_version,
                    detector_policy_version,
                    list(required_families),
                ),
            ).fetchone()
        except psycopg.Error as exc:
            raise GovernanceReviewRepositoryError(str(exc)) from exc
        return bool(row and row[0] is True)

    def resolve_review_approved(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        content_hash: str,
        scan_evidence_id: UUID,
        attestation_policy_version: str,
        detector_policy_version: str,
        finding_scope: str,
        outcomes: tuple[DetectorFamilyOutcome, ...],
    ) -> bool:
        """Persist positive findings and return hash-bound review coverage.

        Args:
            document_id: Canonical document id.
            version_id: Version id.
            content_hash: Object hash.
            scan_evidence_id: Current scan evidence.
            attestation_policy_version: Attestation pin.
            detector_policy_version: Detector policy pin.
            finding_scope: ``metadata`` or ``extraction``.
            outcomes: Detector family outcomes.

        Returns:
            True when every positive family is covered by an active review.
        """

        self.insert_positive_findings(
            document_id=document_id,
            version_id=version_id,
            content_hash=content_hash,
            scan_evidence_id=scan_evidence_id,
            attestation_policy_version=attestation_policy_version,
            detector_policy_version=detector_policy_version,
            finding_scope=finding_scope,
            outcomes=outcomes,
        )
        families = tuple(
            outcome.family
            for outcome in outcomes
            if outcome.result is DetectorResult.POSITIVE
        )
        return self.reviews_cover(
            version_id=version_id,
            content_hash=content_hash,
            scan_evidence_id=scan_evidence_id,
            attestation_policy_version=attestation_policy_version,
            detector_policy_version=detector_policy_version,
            required_families=families,
        )
