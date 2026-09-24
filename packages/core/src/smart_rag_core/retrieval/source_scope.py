"""Server-derived Hybrid source resolution. Never a model-supplied UUID filter."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_V3_PROFILE_ID,
    long_document_runtime_enabled,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

RERANK_PER_DOCUMENT_LEGACY_CAP = 5
"""Historical five-passage per-document rerank pool cap."""

SMALL_CORPUS_MAX_DOCUMENTS = 8
"""Authorized current-document count at or below which the five-per-document
rerank cap silences a long document instead of balancing many documents."""

TRIVIAL_DEFAULT_QUERY_CLASSES = frozenset({"exact_code", "exact_acronym"})
NAMED_SOURCE_CONFIDENCE_THRESHOLD = 0.80
"""Existing named-source confidence floor. Below this, names stay unused."""
MIN_CONTAINED_TITLE_CHARS = 8
"""Minimum normalized title length for query-contained source matching."""
_MIN_RANKING_QUERY_CHARS = 3
_WHITESPACE = re.compile(r"\s+")


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
    authorized_document_count: int = 0,
) -> tuple[str, str]:
    """Choose the frozen Hybrid profile for one resolved scope.

    Args:
        resolution: Source resolution.
        version_id: Exact-one version when present.
        representative_count: Authorized representative count.
        query_class: Optional query class. Trivial exact stays on default.
        authorized_document_count: Current documents the caller may read.
            ``0`` means unknown and never triggers the small-corpus rule.

    Returns:
        ``(profile_id, eligibility_reason)``. Reasons include
        ``small_corpus_long_document`` when an unscoped small corpus holds
        a long document.
    """

    scoped_long = (
        resolution is SourceResolution.EXACT_ONE
        and version_id is not None
        and representative_count > RERANK_PER_DOCUMENT_LEGACY_CAP
    )
    small_corpus_long = (
        resolution is not SourceResolution.EXACT_ONE
        and 0 < authorized_document_count <= SMALL_CORPUS_MAX_DOCUMENTS
        and representative_count > RERANK_PER_DOCUMENT_LEGACY_CAP
    )
    if not (scoped_long or small_corpus_long):
        return HYBRID_DEFAULT_PROFILE_ID, "default_profile_required"
    if not long_document_runtime_enabled():
        return HYBRID_DEFAULT_PROFILE_ID, "unfrozen_long_document_denied"
    if query_class in TRIVIAL_DEFAULT_QUERY_CLASSES:
        return HYBRID_DEFAULT_PROFILE_ID, "trivial_exact_default_profile"
    if scoped_long:
        return LONG_DOCUMENT_V3_PROFILE_ID, "long_document_eligible"
    return LONG_DOCUMENT_V3_PROFILE_ID, "small_corpus_long_document"


@dataclass(frozen=True, slots=True)
class ResolvedRetrievalScope:
    """Server-derived Hybrid scope. Unfrozen long-document stays denied.

    Attributes:
        version_id: Hard version filter only when exactly one authorized
            current version matched. None otherwise.
        whole_document: True when the request is a whole-document summary.
        representative_count: Authorized representative passages for the
            resolved version, or the largest authorized document's count
            when the small-corpus rule applied, else 0.
        query_class: Optional evaluation class id.
        candidate_profile_id: Frozen default, or ``hybrid_long_document_v3``
            when the exact-one or small-corpus long-document rule applies.
        eligibility_reason: Why the long-document candidate was or was not
            eligible.
        resolution: Unscoped, exact-one, or ambiguous.
        selector_texts: Authorized titles used only as scope selectors.
            Empty when unscoped. Never returned to the client as an
            existence oracle.
        authorized_document_count: Current documents the caller may read.
            ``0`` when unknown or when an exact-one scope was resolved.
    """

    version_id: UUID | None
    whole_document: bool
    representative_count: int
    query_class: str | None
    candidate_profile_id: str
    eligibility_reason: str
    resolution: SourceResolution
    selector_texts: tuple[str, ...] = ()
    authorized_document_count: int = 0


def strip_source_selectors(query: str, selectors: Sequence[str]) -> str:
    """Remove matched source-selector text from a ranking query.

    The original question is unchanged for display. Empty or tiny remainders
    fall back to ``query`` so retrieve cannot run on a blank string.

    Args:
        query: User or branch ranking text.
        selectors: Authorized titles or requested names that uniquely
            resolved. Unauthorized names must not be passed in.

    Returns:
        Query with selector phrases removed and whitespace collapsed.
    """

    remaining = query
    for raw in selectors:
        selector = raw.strip()
        if len(selector) < _MIN_RANKING_QUERY_CHARS:
            continue
        remaining = re.sub(re.escape(selector), " ", remaining, flags=re.IGNORECASE)
        stem = filename_stem(selector)
        if stem != selector.casefold() and len(stem) >= MIN_CONTAINED_TITLE_CHARS:
            remaining = re.sub(re.escape(stem), " ", remaining, flags=re.IGNORECASE)
    collapsed = _WHITESPACE.sub(" ", remaining).strip()
    if len(normalize_arabic_v1(collapsed)) < _MIN_RANKING_QUERY_CHARS:
        return query
    return collapsed


def high_confidence_source_names(
    names: Sequence[str],
    confidence: float,
) -> tuple[str, ...]:
    """Keep requested titles only when named-source confidence meets the floor.

    Args:
        names: Bounded textual titles from preparation.
        confidence: Model confidence for ``requested_sources``.

    Returns:
        At most eight stripped titles, or empty when confidence is too low.
    """

    if confidence < NAMED_SOURCE_CONFIDENCE_THRESHOLD:
        return ()
    return tuple(item.strip()[:256] for item in names if item.strip())[:8]


def filename_stem(selector: str) -> str:
    """Return a filename stem for optional stripping.

    Args:
        selector: Title or filename.

    Returns:
        Stem without a trailing extension, lowercased.
    """

    name = selector.strip()
    if "." not in name or " " in name.rsplit(".", 1)[0]:
        return name.casefold()
    return name.rsplit(".", 1)[0].casefold()


def resolve_retrieval_scope(
    *,
    caller: CallerContext,
    requested_sources: tuple[str, ...],
    whole_document: bool,
    query_class: str | None = None,
    representative_count: int = 0,
    connection: psycopg.Connection | None = None,
    query_text: str = "",
) -> ResolvedRetrievalScope:
    """Resolve requested source text to at most one authorized version.

    Zero matches stay unscoped. Multiple matches stay unscoped with
    ``ambiguous``. Unauthorized IDs are indistinguishable from missing.
    An unscoped question on a small authorized corpus whose largest
    document exceeds the legacy per-document cap uses
    ``hybrid_long_document_v3`` without applying a version filter.

    Args:
        caller: Server-derived identity.
        requested_sources: Bounded textual names from preparation.
        whole_document: Phase 6 whole-document summary signal.
        query_class: Optional class for later selector freeze.
        representative_count: Passage count for the resolved version.
        connection: Optional ``app_api`` connection.
        query_text: Original user query. Used only to match authorized
            titles contained in the question.

    Returns:
        Scope with a frozen profile id. Long-document stays denied until
        a measured digest is pinned.
    """

    resolution = SourceResolution.UNSCOPED
    version_id: UUID | None = None
    selector_texts: tuple[str, ...] = ()
    if connection is not None:
        matches = _search_authorized_versions(
            connection,
            caller=caller,
            sources=requested_sources,
            query_text=query_text,
        )
        unique_versions = tuple(dict.fromkeys(item[0] for item in matches))
        if len(unique_versions) == 1:
            version_id = unique_versions[0]
            resolution = SourceResolution.EXACT_ONE
            selector_texts = tuple(
                dict.fromkeys(item[1] for item in matches if item[1])
            )
        elif len(unique_versions) > 1:
            resolution = SourceResolution.AMBIGUOUS
    counted = representative_count
    document_count = 0
    if (
        connection is not None
        and version_id is not None
        and counted <= 0
        and resolution is SourceResolution.EXACT_ONE
    ):
        counted = _count_representatives(connection, version_id)
    if connection is not None and resolution is not SourceResolution.EXACT_ONE:
        document_count, largest = _count_authorized_corpus(connection, caller)
        counted = max(counted, largest)
    profile_id, reason = select_runtime_profile(
        resolution=resolution,
        version_id=version_id if resolution is SourceResolution.EXACT_ONE else None,
        representative_count=counted,
        query_class=query_class,
        authorized_document_count=document_count,
    )
    return ResolvedRetrievalScope(
        version_id=version_id if resolution is SourceResolution.EXACT_ONE else None,
        whole_document=whole_document and resolution is SourceResolution.EXACT_ONE,
        representative_count=counted,
        query_class=query_class,
        candidate_profile_id=profile_id,
        eligibility_reason=reason,
        resolution=resolution,
        selector_texts=selector_texts
        if resolution is SourceResolution.EXACT_ONE
        else (),
        authorized_document_count=document_count,
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


def _count_authorized_corpus(
    connection: psycopg.Connection,
    caller: CallerContext,
) -> tuple[int, int]:
    """Count authorized current documents and the largest representative set.

    The second query runs only when the corpus is small enough for the
    small-corpus rule, so large tenants pay one cheap count.

    Args:
        connection: Canonical Postgres ``app_api`` connection.
        caller: Server-derived identity.

    Returns:
        ``(document_count, largest_representative_count)``. The second
        value is ``0`` when the corpus is empty or larger than
        ``SMALL_CORPUS_MAX_DOCUMENTS``.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)::int
            FROM app.documents AS d
            INNER JOIN app.document_versions AS dv
              ON dv.id = d.current_version_id
            WHERE d.deleted_at IS NULL
              AND dv.deleted_at IS NULL
              AND app.caller_can_read_document(%s, %s, d.id)
            """,
            (caller.rpc_user_id(), caller.rpc_role()),
        )
        row = cursor.fetchone()
        documents = int(row[0]) if row is not None else 0
        if documents == 0 or documents > SMALL_CORPUS_MAX_DOCUMENTS:
            return documents, 0
        cursor.execute(
            """
            SELECT COALESCE(max(per_version.n), 0)::int
            FROM (
              SELECT count(*) AS n
              FROM app.document_chunks AS c
              INNER JOIN app.documents AS d
                ON d.current_version_id = c.version_id
              WHERE d.deleted_at IS NULL
                AND c.deleted_at IS NULL
                AND c.is_search_representative
                AND app.caller_can_read_document(%s, %s, d.id)
              GROUP BY c.version_id
            ) AS per_version
            """,
            (caller.rpc_user_id(), caller.rpc_role()),
        )
        largest = cursor.fetchone()
    return documents, int(largest[0]) if largest is not None else 0


def _search_authorized_versions(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    sources: tuple[str, ...],
    query_text: str = "",
) -> tuple[tuple[UUID, str], ...]:
    """Search authorized current titles and source URIs.

    Exact normalized title equality is preferred over ILIKE. Titles contained
    in the question are considered only when they are long enough to be
    selectors. Unauthorized rows are omitted, which is indistinguishable
    from a missing title.

    Args:
        connection: Canonical Postgres.
        caller: Server-derived identity.
        sources: Textual names. Never UUIDs used as SQL predicates from the
            model; caller-supplied UUID-shaped strings are treated as text.
        query_text: Original question used for contained-title matching.

    Returns:
        Matching ``(version_id, title)`` pairs.
    """

    found: list[tuple[UUID, str]] = []
    for raw in sources[:8]:
        needle = normalize_arabic_v1(raw).strip()
        if not needle:
            continue
        exact = _fetch_exact_title(connection, caller=caller, needle=needle)
        if exact:
            found.extend(exact)
            continue
        found.extend(_fetch_ilike_title(connection, caller=caller, needle=needle))
    haystack = normalize_arabic_v1(query_text)
    if haystack:
        found.extend(
            _fetch_contained_titles(connection, caller=caller, haystack=haystack)
        )
    return tuple(found)


def _rows_to_title_matches(
    rows: Sequence[Sequence[object]],
) -> tuple[tuple[UUID, str], ...]:
    """Convert authorized title rows to version/title pairs.

    Args:
        rows: Cursor rows of ``(version_id, title)``.

    Returns:
        Matching ``(version_id, title)`` pairs.
    """

    matches: list[tuple[UUID, str]] = []
    for row in rows:
        matches.append((UUID(str(row[0])), str(row[1] or "")))
    return tuple(matches)


def _fetch_exact_title(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    needle: str,
) -> tuple[tuple[UUID, str], ...]:
    """Match one authorized current title by exact normalized equality.

    Args:
        connection: Canonical Postgres.
        caller: Server-derived identity.
        needle: Normalized requested title.

    Returns:
        Matching ``(version_id, title)`` pairs.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.id, d.title
            FROM app.documents AS d
            INNER JOIN app.document_versions AS dv
              ON dv.id = d.current_version_id
            LEFT JOIN app.document_sources AS ds
              ON ds.document_id = d.id
            WHERE d.deleted_at IS NULL
              AND dv.deleted_at IS NULL
              AND app.caller_can_read_document(%s, %s, d.id)
              AND search.normalize_arabic_v1(d.title) = %s
            """,
            (caller.rpc_user_id(), caller.rpc_role(), needle),
        )
        rows = cursor.fetchall()
    return _rows_to_title_matches(rows)


def _fetch_ilike_title(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    needle: str,
) -> tuple[tuple[UUID, str], ...]:
    """Match authorized titles or source URIs with a bound ILIKE pattern.

    Args:
        connection: Canonical Postgres.
        caller: Server-derived identity.
        needle: Normalized requested title.

    Returns:
        Matching ``(version_id, title)`` pairs.
    """

    pattern = f"%{needle}%"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.id, d.title
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
            (caller.rpc_user_id(), caller.rpc_role(), pattern, pattern),
        )
        rows = cursor.fetchall()
    return _rows_to_title_matches(rows)


def _fetch_contained_titles(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    haystack: str,
) -> tuple[tuple[UUID, str], ...]:
    """Match authorized titles that appear inside the original question.

    Args:
        connection: Canonical Postgres.
        caller: Server-derived identity.
        haystack: Normalized original query.

    Returns:
        Matching ``(version_id, title)`` pairs. Short titles are ignored.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.id, d.title
            FROM app.documents AS d
            INNER JOIN app.document_versions AS dv
              ON dv.id = d.current_version_id
            LEFT JOIN app.document_sources AS ds
              ON ds.document_id = d.id
            WHERE d.deleted_at IS NULL
              AND dv.deleted_at IS NULL
              AND app.caller_can_read_document(%s, %s, d.id)
              AND char_length(search.normalize_arabic_v1(d.title)) >= %s
              AND strpos(%s, search.normalize_arabic_v1(d.title)) > 0
            """,
            (
                caller.rpc_user_id(),
                caller.rpc_role(),
                MIN_CONTAINED_TITLE_CHARS,
                haystack,
            ),
        )
        rows = cursor.fetchall()
    return _rows_to_title_matches(rows)
