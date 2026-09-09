"""Server-derived Hybrid source resolution. Never a model-supplied UUID filter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_PROFILE_ID,
    long_document_runtime_enabled,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

RERANK_PER_DOCUMENT_LEGACY_CAP = 5
"""Historical five-passage per-document rerank pool cap."""

TRIVIAL_DEFAULT_QUERY_CLASSES = frozenset({"exact_code", "exact_acronym"})


class SourceResolution(StrEnum):
    """How requested source text mapped to authorized versions."""

    UNSCOPED = "unscoped"
    EXACT_ONE = "exact_one"
    AMBIGUOUS = "ambiguous"


def select_runtime_profile(
    *,
    resolution: SourceResolution,
    version_id: UUID | None,
    representative_count: int,
    query_class: str | None,
) -> tuple[str, str]:
    """Choose the frozen Hybrid profile for one resolved scope.

    Args:
        resolution: Source resolution.
        version_id: Exact-one version when present.
        representative_count: Authorized representative count.
        query_class: Optional query class. Trivial exact stays on default.

    Returns:
        ``(profile_id, eligibility_reason)``.
    """

    long_eligible = (
        resolution is SourceResolution.EXACT_ONE
        and representative_count > RERANK_PER_DOCUMENT_LEGACY_CAP
        and version_id is not None
    )
    if not long_eligible:
        return HYBRID_DEFAULT_PROFILE_ID, "default_profile_required"
    if not long_document_runtime_enabled():
        return HYBRID_DEFAULT_PROFILE_ID, "unfrozen_long_document_denied"
    if query_class in TRIVIAL_DEFAULT_QUERY_CLASSES:
        return HYBRID_DEFAULT_PROFILE_ID, "trivial_exact_default_profile"
    return LONG_DOCUMENT_PROFILE_ID, "long_document_eligible"


@dataclass(frozen=True, slots=True)
class ResolvedRetrievalScope:
    """Server-derived Hybrid scope. Unfrozen long-document stays denied.

    Attributes:
        version_id: Hard version filter only when exactly one authorized
            current version matched. None otherwise.
        whole_document: True when the request is a whole-document summary.
        representative_count: Authorized representative passages for the
            resolved version, else 0.
        query_class: Optional evaluation class id.
        candidate_profile_id: Frozen default, or long-document after freeze
            when exact-one and representative_count > 5.
        eligibility_reason: Why the long-document candidate was or was not
            eligible.
        resolution: Unscoped, exact-one, or ambiguous.
    """

    version_id: UUID | None
    whole_document: bool
    representative_count: int
    query_class: str | None
    candidate_profile_id: str
    eligibility_reason: str
    resolution: SourceResolution


def resolve_retrieval_scope(
    *,
    caller: CallerContext,
    requested_sources: tuple[str, ...],
    whole_document: bool,
    query_class: str | None = None,
    representative_count: int = 0,
    connection: psycopg.Connection | None = None,
) -> ResolvedRetrievalScope:
    """Resolve requested source text to at most one authorized version.

    Zero matches stay unscoped. Multiple matches stay unscoped with
    ``ambiguous``. Unauthorized IDs are indistinguishable from missing. The
    long-document candidate remains runtime-denied until freeze.

    Args:
        caller: Server-derived identity.
        requested_sources: Bounded textual names from preparation.
        whole_document: Phase 6 whole-document summary signal.
        query_class: Optional class for later selector freeze.
        representative_count: Passage count for the resolved version.
        connection: Optional ``app_api`` connection.

    Returns:
        Scope with a frozen profile id. Long-document stays denied until
        Packet 16 pins its digest.
    """

    resolution = SourceResolution.UNSCOPED
    version_id: UUID | None = None
    if connection is not None and requested_sources:
        matches = _search_authorized_versions(
            connection,
            caller=caller,
            sources=requested_sources,
        )
        unique = tuple(dict.fromkeys(matches))
        if len(unique) == 1:
            version_id = unique[0]
            resolution = SourceResolution.EXACT_ONE
        elif len(unique) > 1:
            resolution = SourceResolution.AMBIGUOUS
    counted = representative_count
    if (
        connection is not None
        and version_id is not None
        and counted <= 0
        and resolution is SourceResolution.EXACT_ONE
    ):
        counted = _count_representatives(connection, version_id)
    profile_id, reason = select_runtime_profile(
        resolution=resolution,
        version_id=version_id if resolution is SourceResolution.EXACT_ONE else None,
        representative_count=counted,
        query_class=query_class,
    )
    return ResolvedRetrievalScope(
        version_id=version_id if resolution is SourceResolution.EXACT_ONE else None,
        whole_document=whole_document and resolution is SourceResolution.EXACT_ONE,
        representative_count=counted,
        query_class=query_class,
        candidate_profile_id=profile_id,
        eligibility_reason=reason,
        resolution=resolution,
    )


def _count_representatives(
    connection: psycopg.Connection,
    version_id: UUID,
) -> int:
    """Count current search representatives for one version.

    Args:
        connection: Canonical Postgres.
        version_id: Resolved version.

    Returns:
        Representative count.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)::int
            FROM app.document_chunks
            WHERE version_id = %s
              AND deleted_at IS NULL
              AND is_search_representative
            """,
            (version_id,),
        )
        row = cursor.fetchone()
    return int(row[0]) if row is not None else 0


def _search_authorized_versions(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    sources: tuple[str, ...],
) -> tuple[UUID, ...]:
    """Search authorized current titles and source URIs.

    Args:
        connection: Canonical Postgres.
        caller: Server-derived identity.
        sources: Textual names. Never UUIDs used as SQL predicates from the
            model; caller-supplied UUID-shaped strings are treated as text.

    Returns:
        Matching current version ids. Unauthorized rows are omitted.
    """

    found: list[UUID] = []
    for raw in sources[:8]:
        needle = normalize_arabic_v1(raw).strip()
        if not needle:
            continue
        pattern = f"%{needle}%"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT dv.id
                FROM app.documents AS d
                INNER JOIN app.document_versions AS dv
                  ON dv.id = d.current_version_id
                LEFT JOIN app.document_sources AS ds
                  ON ds.document_id = d.id
                WHERE d.deleted_at IS NULL
                  AND dv.deleted_at IS NULL
                  AND app.caller_can_read_document(%s, %s, d.id)
                  AND (
                    search.normalize_arabic_v1(d.title) ILIKE %s
                    OR COALESCE(ds.source_uri, '') ILIKE %s
                  )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    pattern,
                    pattern,
                ),
            )
            for row in cursor.fetchall():
                found.append(UUID(str(row[0])))
    return tuple(found)
