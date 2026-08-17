"""Typed failures for Phase 9 Packet 1 candidate freeze and seed."""

from __future__ import annotations


class CandidateReleaseError(RuntimeError):
    """Base error for local release-candidate Packet 1 failures."""


class CandidateDigestMismatchError(CandidateReleaseError):
    """Raised when a recorded image digest does not match the running image."""


class CandidatePortError(CandidateReleaseError):
    """Raised when ParadeDB, Valkey, or LightRAG publish a host port."""


class UnapprovedCorpusError(CandidateReleaseError):
    """Raised when holdout, production, or otherwise unapproved data is seeded."""


class RestrictedGraphIndexError(CandidateReleaseError):
    """Raised when restricted visibility is offered to LightRAG indexing."""


class FakeReadinessError(CandidateReleaseError):
    """Raised when Hybrid Ready or Graph Ready is claimed without real jobs."""


class CandidateIdentityError(CandidateReleaseError):
    """Raised when a required freeze field is missing or drifted."""


class CandidateMigrationDriftError(CandidateReleaseError):
    """Raised when applied migrations do not match repository files."""
