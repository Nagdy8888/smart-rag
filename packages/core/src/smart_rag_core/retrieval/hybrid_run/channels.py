"""Hybrid channel collect, unpack, restrict, and flatten helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeGuard, cast
from uuid import UUID

from smart_rag_core.retrieval.hybrid_run.types import (
    CandidateList,
    VariantLists,
)
from smart_rag_core.retrieval.profiles import (
    DENSE_CANDIDATE_CAP,
    DENSE_UNDERFILL_FLOOR,
    EXACT_FALLBACK_AUTHORIZED_ROW_CAP,
    EXACT_START_MIN_SLICE_SECONDS,
    TERM_CANDIDATE_CAP,
    DenseMode,
    HnswProfileId,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
)
from smart_rag_core.retrieval.term_needles import expand_term_texts
from smart_rag_core.retrieval.types import (
    Bm25RetrievalResult,
    DenseRetrievalResult,
    RetrievalCandidate,
    TermRetrievalResult,
)
from smart_rag_core.security.identity import CallerContext


def _is_candidate_tuple(value: object) -> TypeGuard[CandidateList]:
    """Return whether ``value`` is a tuple of retrieval candidates.

    Args:
        value: Channel job payload or an inner list.

    Returns:
        True when ``value`` is a tuple whose first item is a candidate, or
        empty. Matches the existing unpack ``isinstance`` checks.
    """

    if not isinstance(value, tuple):
        return False
    items = cast(tuple[object, ...], value)
    return not items or isinstance(items[0], RetrievalCandidate)


def _is_variant_tuple(value: object) -> TypeGuard[VariantLists]:
    """Return whether ``value`` is a tuple of per-variant candidate lists.

    Args:
        value: Channel job payload.

    Returns:
        True when ``value`` is a non-empty tuple whose first item is a tuple.
    """

    if not isinstance(value, tuple) or not value:
        return False
    items = cast(tuple[object, ...], value)
    return isinstance(items[0], tuple)


def _invoke_dense(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    query_embedding: list[float],
    **extra: object,
) -> object:
    """Call a dense retrieve double, dropping unknown kwargs.

    Args:
        retrieve: Live adapter or test double.
        caller: Server-derived identity.
        query_embedding: Query vector.
        extra: Optional profile/mode/escalate flags.

    Returns:
        Dense result or candidate tuple.
    """

    try:
        return retrieve(
            caller=caller,
            query_embedding=query_embedding,
            **extra,
        )
    except TypeError:
        return retrieve(caller=caller, query_embedding=query_embedding)


def exact_dense_admitted(remaining_slice_seconds: float | None) -> bool:
    """Admit an exact dense scan only when the retrieve slice can hold it.

    Args:
        remaining_slice_seconds: Channel-plus-rerank remainder, or ``None``
            when the caller did not measure a slice.

    Returns:
        True only when remaining seconds are at least
        ``EXACT_START_MIN_SLICE_SECONDS``. Unmeasured slices stay on ANN
        so production Ask cannot start exact by omission.
    """

    if remaining_slice_seconds is None:
        return False
    return remaining_slice_seconds >= EXACT_START_MIN_SLICE_SECONDS


def dense_retrieve_mode(
    *,
    version_id: UUID | None,
    profile: object | None,
    remaining_slice_seconds: float | None = None,
) -> DenseMode:
    """Select ANN or exact dense for one Hybrid channel job.

    Version-scoped exact is a long-document evaluation candidate. The
    default profile stays on ANN. Exact still honors the 10,000-row
    admission ceiling inside ``DenseRetriever``. P06-71 additionally
    requires a retrieve slice of at least the Hybrid envelope so exact
    cannot starve the 25s Ask deadline.

    Args:
        version_id: Resolved current version, or ``None`` when unscoped.
        profile: Frozen or evaluation Hybrid profile, or ``None``.
        remaining_slice_seconds: Channel-plus-rerank remainder.

    Returns:
        ``exact`` only when the profile asks for it, a version is set,
        and the remaining slice admits exact work.
    """

    if version_id is None or profile is None:
        return DenseMode.ANN
    mode = getattr(profile, "dense_mode_when_version_scoped", "ann")
    if mode == "exact" and exact_dense_admitted(remaining_slice_seconds):
        return DenseMode.EXACT
    return DenseMode.ANN


def collect_dense_lists(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    texts: tuple[str, ...],
    vectors: tuple[tuple[float, ...], ...],
    version_id: UUID | None = None,
    dense_mode: DenseMode = DenseMode.ANN,
    remaining_slice_seconds: float | None = None,
) -> VariantLists:
    """Run dense retrieve once per fused query vector.

    Escalation is at most one HIGH ANN per variant, then exact only when
    ``authorized_count * vector_count`` is at or below 10,000 and the
    remaining retrieve slice admits exact work. When ``dense_mode`` is
    already exact, ANN/HIGH retries are skipped.

    Args:
        retrieve: Bound ``DenseRetriever.retrieve`` or a test double.
        caller: Server-derived identity.
        texts: Query forms aligned with ``vectors``.
        vectors: Query embeddings.
        version_id: Optional current-version filter inside ranking.
        dense_mode: Initial dense execution mode.
        remaining_slice_seconds: Channel-plus-rerank remainder used to
            admit or refuse exact escalation.

    Returns:
        Per-variant dense candidate lists after the global unique cap.
    """

    extra: dict[str, object] = {}
    if version_id is not None:
        extra["version_id"] = version_id
    if dense_mode is DenseMode.EXACT:
        extra["mode"] = DenseMode.EXACT
    lists: list[CandidateList] = []
    authorized_count = 0
    for _text, vector in zip(texts, vectors, strict=False):
        result = _invoke_dense(
            retrieve,
            caller=caller,
            query_embedding=list(vector),
            escalate=False,
            **extra,
        )
        if isinstance(result, DenseRetrievalResult):
            lists.append(result.candidates)
            authorized_count = result.authorized_count
        elif isinstance(result, tuple):
            lists.append(cast(CandidateList, result))
    if dense_mode is DenseMode.EXACT:
        return cap_unique_across_variants(tuple(lists), DENSE_CANDIDATE_CAP)
    unique = {item.chunk_id for variant in lists for item in variant}
    if unique and len(unique) < DENSE_UNDERFILL_FLOOR:
        high: list[CandidateList] = []
        for _text, vector in zip(texts, vectors, strict=False):
            result = _invoke_dense(
                retrieve,
                caller=caller,
                query_embedding=list(vector),
                profile=HnswProfileId.HIGH,
                escalate=False,
                **extra,
            )
            if isinstance(result, DenseRetrievalResult):
                high.append(result.candidates)
                authorized_count = result.authorized_count
            elif isinstance(result, tuple):
                high.append(cast(CandidateList, result))
        if high:
            lists = high
        unique = {item.chunk_id for variant in lists for item in variant}
        work = authorized_count * max(len(vectors), 1)
        if (
            len(unique) < DENSE_UNDERFILL_FLOOR
            and work <= EXACT_FALLBACK_AUTHORIZED_ROW_CAP
            and exact_dense_admitted(remaining_slice_seconds)
        ):
            exact: list[CandidateList] = []
            for _text, vector in zip(texts, vectors, strict=False):
                result = _invoke_dense(
                    retrieve,
                    caller=caller,
                    query_embedding=list(vector),
                    mode=DenseMode.EXACT,
                    escalate=False,
                    **extra,
                )
                if isinstance(result, DenseRetrievalResult):
                    exact.append(result.candidates)
                elif isinstance(result, tuple):
                    exact.append(cast(CandidateList, result))
            if exact:
                lists = exact
    return cap_unique_across_variants(tuple(lists), DENSE_CANDIDATE_CAP)


def collect_term_lists(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    texts: tuple[str, ...],
) -> VariantLists:
    """Run term retrieve on ranking texts plus bounded extracted needles.

    Args:
        retrieve: Bound ``TermRetriever.retrieve`` or a test double.
        caller: Server-derived identity.
        texts: Query forms.

    Returns:
        Per-variant term candidate lists, unique-capped across variants.
    """

    lists: list[CandidateList] = []
    for text in expand_term_texts(texts):
        result = retrieve(caller=caller, query_text=text)
        if isinstance(result, TermRetrievalResult):
            lists.append(result.candidates)
        elif isinstance(result, tuple):
            lists.append(cast(CandidateList, result))
    return cap_unique_across_variants(tuple(lists), TERM_CANDIDATE_CAP)


def restrict_channel_candidates(
    dense_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_result: Bm25RetrievalResult,
    term_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    version_id: UUID | None,
) -> tuple[
    tuple[tuple[RetrievalCandidate, ...], ...],
    Bm25RetrievalResult,
    tuple[tuple[RetrievalCandidate, ...], ...],
]:
    """Keep only candidates whose version matches the caller filter.

    Args:
        dense_lists: Per-variant dense lists.
        bm25_result: Authorized BM25 survivors.
        term_lists: Per-variant term lists.
        version_id: Version filter, or ``None`` to keep every candidate.

    Returns:
        Filtered dense lists, BM25 result, and term lists.
    """

    if version_id is None:
        return dense_lists, bm25_result, term_lists

    def _keep(
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RetrievalCandidate, ...]:
        """Filter one candidate list to ``version_id``.

        Args:
            candidates: Authorized candidates.

        Returns:
            Candidates for the requested version only.
        """

        return tuple(item for item in candidates if item.version_id == version_id)

    filtered_dense = tuple(_keep(variant) for variant in dense_lists)
    filtered_bm25_candidates = _keep(bm25_result.candidates)
    filtered_bm25 = Bm25RetrievalResult(
        scanned_ids=tuple(item.chunk_id for item in filtered_bm25_candidates),
        candidates=filtered_bm25_candidates,
        fallback_reason=bm25_result.fallback_reason,
        variant_lists=tuple(_keep(variant) for variant in bm25_result.variant_lists),
        variant_count=bm25_result.variant_count,
        variant_ranks=tuple(
            len(_keep(variant)) for variant in bm25_result.variant_lists
        )
        if bm25_result.variant_lists
        else (len(filtered_bm25_candidates),),
        rechecked_count=bm25_result.rechecked_count,
        survivor_count=len(filtered_bm25_candidates),
        index_schema_version=bm25_result.index_schema_version,
        normalizer_version=bm25_result.normalizer_version,
    )
    filtered_term = tuple(_keep(variant) for variant in term_lists)
    return filtered_dense, filtered_bm25, filtered_term


def cap_unique_across_variants(
    lists: VariantLists,
    cap: int,
) -> VariantLists:
    """Keep at most ``cap`` unique chunk IDs with round-robin variant fairness.

    One variant cannot consume the entire cap before later variants are
    considered. Later exact duplicates of an already kept ID are dropped.

    Args:
        lists: Per-variant candidate lists.
        cap: Global unique ID ceiling.

    Returns:
        Variant lists reconstructed from the global survivor set.
    """

    if not lists or cap <= 0:
        return tuple(() for _ in lists)
    allowed: list[UUID] = []
    seen: set[UUID] = set()
    indexes = [0] * len(lists)
    progressed = True
    while len(allowed) < cap and progressed:
        progressed = False
        for ordinal, variant in enumerate(lists):
            while indexes[ordinal] < len(variant):
                item = variant[indexes[ordinal]]
                indexes[ordinal] += 1
                if item.chunk_id in seen:
                    continue
                seen.add(item.chunk_id)
                allowed.append(item.chunk_id)
                progressed = True
                break
            if len(allowed) >= cap:
                break
    allowed_set = set(allowed)
    return tuple(
        tuple(item for item in variant if item.chunk_id in allowed_set)
        for variant in lists
    )


def flatten_channel_candidates(
    dense_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_candidates: tuple[RetrievalCandidate, ...],
    term_lists: tuple[tuple[RetrievalCandidate, ...], ...],
) -> tuple[RetrievalCandidate, ...]:
    """Flatten dense, BM25, and term candidates for temporal lookup.

    Args:
        dense_lists: Per-variant dense lists.
        bm25_candidates: Authorized BM25 survivors.
        term_lists: Per-variant term lists.

    Returns:
        Deduplicated candidates in first-seen order.
    """

    seen: set[UUID] = set()
    ordered: list[RetrievalCandidate] = []
    for variant in dense_lists:
        for item in variant:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            ordered.append(item)
    for item in bm25_candidates:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        ordered.append(item)
    for variant in term_lists:
        for item in variant:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            ordered.append(item)
    return tuple(ordered)


def unique_chunk_ids(candidates: Sequence[RetrievalCandidate]) -> tuple[UUID, ...]:
    """Return first-seen authorized chunk IDs without BM25 text.

    Args:
        candidates: Authorized channel survivors.

    Returns:
        Unique IDs in first-seen order.
    """

    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for item in candidates:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        ordered.append(item.chunk_id)
    return tuple(ordered)


def unpack_dense(
    value: object,
) -> tuple[VariantLists, RetrievalFallbackReason]:
    """Normalize a dense channel job result.

    Args:
        value: Job return value or ``None`` when the job was absent.

    Returns:
        Variant lists and a named dense fallback when the channel failed.
    """

    if value is None:
        return (), RetrievalFallbackReason.NONE
    if isinstance(value, DenseRetrievalResult):
        return (value.candidates,), value.fallback_reason
    if _is_candidate_tuple(value):
        if not value:
            return (), RetrievalFallbackReason.NONE
        return (value,), RetrievalFallbackReason.NONE
    if _is_variant_tuple(value):
        return value, RetrievalFallbackReason.NONE
    return (), RetrievalFallbackReason.DENSE_UNAVAILABLE


def unpack_term(
    value: object,
) -> tuple[VariantLists, RetrievalFallbackReason]:
    """Normalize a term channel job result.

    Args:
        value: Job return value or ``None`` when the job was absent.

    Returns:
        Variant lists and a named term fallback when the channel failed.
    """

    if value is None:
        return (), RetrievalFallbackReason.NONE
    if isinstance(value, TermRetrievalResult):
        return (value.candidates,), value.fallback_reason
    if _is_candidate_tuple(value):
        if not value:
            return (), RetrievalFallbackReason.NONE
        return (value,), RetrievalFallbackReason.NONE
    if _is_variant_tuple(value):
        return value, RetrievalFallbackReason.NONE
    return (), RetrievalFallbackReason.TERM_UNAVAILABLE


def unpack_bm25(value: object) -> Bm25RetrievalResult:
    """Normalize a BM25 channel job result.

    Args:
        value: Job return value or ``None``.

    Returns:
        ID-only BM25 result. Missing jobs are empty with ``none``.
    """

    if isinstance(value, Bm25RetrievalResult):
        return value
    if _is_candidate_tuple(value) and value:
        return Bm25RetrievalResult(scanned_ids=(), candidates=value)
    if _is_variant_tuple(value) and value[0] and _is_candidate_tuple(value[0]):
        return Bm25RetrievalResult(scanned_ids=(), candidates=value[0])
    return Bm25RetrievalResult(scanned_ids=(), candidates=())


def compose_fallback(
    *,
    dense_reason: RetrievalFallbackReason,
    term_reason: RetrievalFallbackReason,
    bm25_fallback: RetrievalFallbackReason,
    deadline_exhausted: bool,
) -> RetrievalFallbackReason:
    """Choose the retrieve-level named fallback.

    Args:
        dense_reason: Dense channel outcome.
        term_reason: Term channel outcome.
        bm25_fallback: BM25 outage, version mismatch, timeout, or none.
        deadline_exhausted: True when any parallel job timed out.

    Returns:
        Highest-priority named reason. ``none`` when channels completed.
    """

    if dense_reason is RetrievalFallbackReason.DENSE_UNAVAILABLE:
        return RetrievalFallbackReason.DENSE_UNAVAILABLE
    if term_reason is RetrievalFallbackReason.TERM_UNAVAILABLE:
        return RetrievalFallbackReason.TERM_UNAVAILABLE
    if bm25_fallback is not RetrievalFallbackReason.NONE:
        return bm25_fallback
    if deadline_exhausted:
        return RetrievalFallbackReason.TIMEOUT
    return RetrievalFallbackReason.NONE


def identity_rerank(
    _query: str,
    pool: tuple[RerankPassage, ...],
    _deadline: float,
) -> tuple[tuple[RerankRanking, ...], None, RerankFallbackReason]:
    """Keep fused pool order without a model call.

    Args:
        _query: Unused original query.
        pool: Authorized rerank pool.
        _deadline: Unused remaining slice.

    Returns:
        Identity rankings, no usage, and ``none`` fallback.
    """

    rankings = tuple(
        RerankRanking(
            chunk_id=item.candidate.chunk_id,
            rank=index + 1,
            support=1.0,
        )
        for index, item in enumerate(pool)
    )
    return rankings, None, RerankFallbackReason.NONE
