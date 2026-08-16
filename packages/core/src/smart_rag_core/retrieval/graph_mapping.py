"""Canonical graph evidence identities, chunk matching, and support batching.

This module owns mapping table names and Graph Ready gates. Worker and other
retrieval modules must not repeat those strings. Hybrid retrieve is invoked at
most once per document; support rerank is invoked at most once per document.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.ingestion.chunking.normalize import (
    content_hash,
    normalize_for_dedup,
)
from smart_rag_core.jobs.limits import (
    GRAPH_PIPELINE_VERSION,
    MAPPING_COVERAGE_ARABIC_MIXED_MIN,
    MAPPING_COVERAGE_OVERALL_MIN,
    MAPPING_OVERLAP_MIN,
    MAPPING_SUPPORT_MIN,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_HYBRID_CALLS,
    MAX_MAPPING_RELATIONS,
    MAX_MAPPING_RERANK_CALLS,
    MAX_MAPPING_RERANK_POOL,
    MAX_MAPPING_VENDOR_CHUNKS,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    DEFAULT_MAX_SOURCE_IDS_PER_RELATION,
    GRAPH_FIELD_SEP,
    opaque_graph_source_basename,
    parse_source_id_list,
    strip_graph_source_envelope,
)
from smart_rag_core.retrieval.hybrid_run import HybridRetriever, HybridRunResult
from smart_rag_core.retrieval.rerank import RerankPassage, RerankRanking
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext

MappingMethod = Literal["hash", "span", "overlap", "hybrid_support"]
GraphObjectType = Literal["entity", "statement", "path_edge"]
Direction = Literal["src_to_tgt", "tgt_to_src"]

HybridRetrieveFn = Callable[[str, UUID], HybridRunResult]
SupportRerankFn = Callable[[str, tuple[RerankPassage, ...]], tuple[RerankRanking, ...]]


class MappingBudgetError(ValueError):
    """Raised when mapping exceeds bounded vendor or model-call limits."""


@dataclass(frozen=True, slots=True)
class CanonicalPassage:
    """One canonical chunk eligible for mapping.

    Attributes:
        chunk_id: Canonical chunk UUID.
        version_id: Owning document version.
        document_id: Owning document.
        chunk_index: Order within the version.
        raw_text: Citation text from ``document_chunks.raw_text``.
        content_hash: Ingest SHA-256 of ``normalize_for_dedup(raw_text)``.
        language: Version language ``en``, ``ar``, ``mixed``, or empty.
    """

    chunk_id: UUID
    version_id: UUID
    document_id: UUID
    chunk_index: int
    raw_text: str
    content_hash: str
    language: str = ""


@dataclass(frozen=True, slots=True)
class ChunkMatch:
    """One internal-chunk to canonical-passage mapping.

    Attributes:
        canonical: Matched canonical passage.
        method: hash, span, overlap, or hybrid_support.
        score: Method score in ``[0, 1]``.
        source_hash: SHA-256 of stripped normalized vendor text.
        target_hash: Canonical ``content_hash``.
        source_span: Vendor offsets after envelope strip.
        target_span: Canonical raw_text offsets when known.
    """

    canonical: CanonicalPassage
    method: MappingMethod
    score: float
    source_hash: str
    target_hash: str
    source_span: dict[str, int]
    target_span: dict[str, int]


@dataclass(frozen=True, slots=True)
class EntityRuleView:
    """Active entity rule used only for canonical keys.

    Attributes:
        entity_type: Rule type column.
        canonical_name: Optional curated display/canonical name.
        aliases: Names that map to ``canonical_name``.
        do_not_merge: Names that must stay separate.
    """

    entity_type: str
    canonical_name: str | None
    aliases: tuple[str, ...]
    do_not_merge: tuple[str, ...]


@dataclass
class MappingCallCounts:
    """Mutable Hybrid/rerank counters for Packet 4 proofs.

    Attributes:
        hybrid_retrieve: Scoped Hybrid retrieve invocations.
        support_rerank: Support rerank batch invocations.
    """

    hybrid_retrieve: int = 0
    support_rerank: int = 0


@dataclass(frozen=True, slots=True)
class CoverageSlice:
    """Numerator/denominator/exclusions for one language or object type.

    Attributes:
        language: ``en``, ``ar``, ``mixed``, or empty.
        object_type: chunk, entity, statement, or path_edge.
        method: Winning method or empty when unmapped.
        numerator: Accepted objects.
        denominator: Eligible objects including failures.
        exclusion_count: Truncated/ambiguous/unsupported/stale count.
        truncation_count: Source-id cap losses.
        failure_reason: Dominant failure reason or empty.
    """

    language: str
    object_type: str
    method: str
    numerator: int
    denominator: int
    exclusion_count: int
    truncation_count: int = 0
    failure_reason: str = ""

    @property
    def ratio(self) -> float:
        """Return coverage ratio, or ``0.0`` when the denominator is zero."""

        if self.denominator <= 0:
            return 0.0
        return self.numerator / self.denominator


class MappingIdentity(BaseModel):
    """Stable application-owned mapping identifiers.

    Attributes:
        source_identity: Version plus config generation digest.
        internal_chunk_key: Workspace-qualified vendor chunk key.
        entity_key: Canonical entity key after rules.
        statement_id: Application statement hash.
        path_edge_id: Ordered-statement path-edge hash.
    """

    model_config = ConfigDict(frozen=True)

    source_identity: str = Field(min_length=16, max_length=64)
    internal_chunk_key: str = Field(default="", max_length=1024)
    entity_key: str = Field(default="", max_length=64)
    statement_id: str = Field(default="", max_length=64)
    path_edge_id: str = Field(default="", max_length=64)


def mapping_config_generation(
    *,
    workspace_key: str,
    pointer_generation: int,
    chunker_snapshot: Mapping[str, object],
) -> str:
    """Hash workspace generation with the pinned chunker/pipeline snapshot.

    Args:
        workspace_key: Application workspace identifier.
        pointer_generation: Active pointer generation, defaulting to 1.
        chunker_snapshot: ``graph_chunker_config_snapshot`` mapping.

    Returns:
        Lowercase SHA-256 hex digest.
    """

    payload = {
        "workspace_key": workspace_key,
        "pointer_generation": pointer_generation,
        "pipeline": GRAPH_PIPELINE_VERSION,
        "chunker": dict(chunker_snapshot),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_source_identity(*, version_id: UUID, config_generation: str) -> str:
    """Return the application source identity, never a vendor hash or path.

    Args:
        version_id: Canonical document version ID.
        config_generation: Mapping config generation digest.

    Returns:
        SHA-256 of pipeline, version, and config generation.
    """

    payload = f"{GRAPH_PIPELINE_VERSION}|{version_id}|{config_generation}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def internal_chunk_key(
    *,
    workspace_key: str,
    config_generation: str,
    vendor_chunk_id: str,
) -> str:
    """Qualify a vendor chunk id. Never a cross-version application ID.

    Args:
        workspace_key: LightRAG constructor workspace.
        config_generation: Mapping config generation digest.
        vendor_chunk_id: Internal LightRAG chunk token.

    Returns:
        Workspace-qualified internal key.
    """

    return f"{workspace_key}:{config_generation}:{vendor_chunk_id}"


def _stable_digest(*parts: str) -> str:
    """Hash ordered identity parts with the pinned source delimiter.

    Args:
        parts: Stable non-prose identity components.

    Returns:
        Lowercase SHA-256 hex digest.
    """

    payload = GRAPH_FIELD_SEP.join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_relation_label(keywords: str | None) -> str:
    """Build a versioned relation-label key from structured keywords.

    Description prose is never used. Empty keywords are unsupported.

    Args:
        keywords: Structured relation ``keywords`` field, not description.

    Returns:
        Normalized label key.

    Raises:
        ValueError: If keywords are missing or blank.
    """

    if keywords is None or not str(keywords).strip():
        raise ValueError("unsupported_relation")
    normalized = normalize_for_dedup(str(keywords))
    if not normalized:
        raise ValueError("unsupported_relation")
    return normalized


def canonical_entity_key(*, entity_type: str, canonical_name: str) -> str:
    """Hash a versioned type plus canonical name.

    Args:
        entity_type: Vendor or curated type.
        canonical_name: Rule canonical or vendor name.

    Returns:
        SHA-256 entity key.
    """

    return _stable_digest(
        GRAPH_PIPELINE_VERSION,
        normalize_for_dedup(entity_type),
        normalize_for_dedup(canonical_name),
    )


def graph_statement_id(
    *,
    subject_key: str,
    object_key: str,
    relation_label_key: str,
) -> str:
    """Hash pipeline, canonical endpoints, and structured relation-label key.

    Args:
        subject_key: Canonical subject entity key.
        object_key: Canonical object entity key.
        relation_label_key: Normalized structured relation label.

    Returns:
        Stable ``graph_statement_id``.
    """

    return _stable_digest(
        GRAPH_PIPELINE_VERSION,
        subject_key,
        object_key,
        relation_label_key,
    )


def graph_path_edge_id(
    *,
    statement_ids: Sequence[str],
    direction: Direction,
    version_id: UUID,
) -> str:
    """Hash ordered statement IDs plus direction and version.

    Args:
        statement_ids: Ordered application statement IDs.
        direction: Path direction.
        version_id: Canonical version.

    Returns:
        Path-edge identifier. Native prose is not embedded.
    """

    return _stable_digest(
        GRAPH_PIPELINE_VERSION,
        ",".join(statement_ids),
        direction,
        str(version_id),
    )


def resolve_entity_name(
    vendor_name: str,
    vendor_type: str | None,
    rules: Sequence[EntityRuleView],
) -> str | None:
    """Return a canonical entity name or ``None`` when the name is ambiguous.

    Unresolved names stay separate. Ambiguous alias/do-not-merge collisions
    are unavailable rather than auto-merged. Hybrid aliases are not copied.

    Args:
        vendor_name: LightRAG entity id/name.
        vendor_type: Optional vendor type.
        rules: Active ``graph_entity_rules`` views.

    Returns:
        Canonical name, or ``None`` when ambiguous.
    """

    normalized = normalize_for_dedup(vendor_name)
    matches: list[str] = []
    blocked = False
    for rule in rules:
        aliases = {normalize_for_dedup(item) for item in rule.aliases}
        aliases.add(normalize_for_dedup(rule.canonical_name or ""))
        do_not_merge = {normalize_for_dedup(item) for item in rule.do_not_merge}
        if normalized in do_not_merge and aliases.intersection(do_not_merge):
            blocked = True
        type_ok = (
            not vendor_type or not rule.entity_type or vendor_type == rule.entity_type
        )
        if type_ok and normalized in aliases and rule.canonical_name:
            matches.append(rule.canonical_name)
    unique = tuple(dict.fromkeys(matches))
    if blocked or len(unique) > 1:
        return None
    if unique:
        return unique[0]
    return vendor_name


def _token_jaccard(left: str, right: str) -> float:
    """Return bounded token overlap after the ingest normalizer.

    Args:
        left: Vendor or canonical text.
        right: Comparison text.

    Returns:
        Jaccard ratio in ``[0, 1]``.
    """

    left_tokens = set(normalize_for_dedup(left).split())
    right_tokens = set(normalize_for_dedup(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union)


def _span_offsets(haystack: str, needle: str) -> dict[str, int] | None:
    """Return character offsets when ``needle`` is an exact substring.

    Args:
        haystack: Normalized canonical or vendor text.
        needle: Normalized substring to locate.

    Returns:
        ``start``/``end`` offsets, or ``None`` when missing.
    """

    if not needle:
        return None
    index = haystack.find(needle)
    if index < 0:
        return None
    return {"start": index, "end": index + len(needle)}


def map_vendor_chunk(
    vendor_text: str,
    canonicals: Sequence[CanonicalPassage],
    *,
    version_id: UUID,
) -> ChunkMatch | None:
    """Map one vendor chunk by hash, then exact span, then bounded overlap.

    Envelope stripping happens before hash/span/overlap. Canonical
    ``content_hash`` uses the ingest normalizer. Cross-version rows are
    ignored.

    Args:
        vendor_text: Vendor chunk content, possibly envelope-prefixed.
        canonicals: Canonical passages for this version.
        version_id: Mapping version. Other versions are rejected.

    Returns:
        Best in-version match, or ``None`` when unresolved.
    """

    stripped = strip_graph_source_envelope(vendor_text)
    source_hash = content_hash(stripped)
    source_span = {"start": 0, "end": len(stripped)}
    in_version = tuple(item for item in canonicals if item.version_id == version_id)
    for row in in_version:
        if row.content_hash == source_hash:
            return ChunkMatch(
                canonical=row,
                method="hash",
                score=1.0,
                source_hash=source_hash,
                target_hash=row.content_hash,
                source_span=source_span,
                target_span={"start": 0, "end": len(row.raw_text)},
            )
    normalized_vendor = normalize_for_dedup(stripped)
    for row in in_version:
        span = _span_offsets(normalize_for_dedup(row.raw_text), normalized_vendor)
        if span is None:
            span = _span_offsets(normalized_vendor, normalize_for_dedup(row.raw_text))
        if span is not None:
            return ChunkMatch(
                canonical=row,
                method="span",
                score=1.0,
                source_hash=source_hash,
                target_hash=row.content_hash,
                source_span=source_span,
                target_span=span,
            )
    best: ChunkMatch | None = None
    for row in in_version:
        score = _token_jaccard(stripped, row.raw_text)
        if score < MAPPING_OVERLAP_MIN:
            continue
        if best is None or score > best.score:
            best = ChunkMatch(
                canonical=row,
                method="overlap",
                score=score,
                source_hash=source_hash,
                target_hash=row.content_hash,
                source_span=source_span,
                target_span={"start": 0, "end": len(row.raw_text)},
            )
    return best


def assert_mapping_budget(
    *,
    vendor_chunks: int,
    entities: int,
    relations: int,
    hybrid_calls: int,
    rerank_calls: int,
) -> None:
    """Fail closed when mapping exceeds Packet 4 bounds.

    Args:
        vendor_chunks: Enumerated vendor chunk count.
        entities: Enumerated entity count.
        relations: Enumerated relation count.
        hybrid_calls: Hybrid retrieve calls for this document.
        rerank_calls: Support rerank calls for this document.

    Raises:
        MappingBudgetError: If any bound is exceeded.
    """

    if vendor_chunks > MAX_MAPPING_VENDOR_CHUNKS:
        raise MappingBudgetError("mapping_budget_chunks")
    if entities > MAX_MAPPING_ENTITIES:
        raise MappingBudgetError("mapping_budget_entities")
    if relations > MAX_MAPPING_RELATIONS:
        raise MappingBudgetError("mapping_budget_relations")
    if hybrid_calls > MAX_MAPPING_HYBRID_CALLS:
        raise MappingBudgetError("mapping_budget_hybrid")
    if rerank_calls > MAX_MAPPING_RERANK_CALLS:
        raise MappingBudgetError("mapping_budget_rerank")


def parse_object_source_ids(
    raw: str | None,
    *,
    kind: Literal["entity", "relation"],
) -> tuple[str, ...]:
    """Parse a vendor source-id list with Packet 1 fail-closed caps.

    Args:
        raw: Delimiter-joined source tokens or ``None``.
        kind: Entity versus relation retention cap.

    Returns:
        Ordered unique source tokens.

    Raises:
        SourceIdContractError: Empty, ambiguous, or truncated lists.
    """

    limit = (
        DEFAULT_MAX_SOURCE_IDS_PER_ENTITY
        if kind == "entity"
        else DEFAULT_MAX_SOURCE_IDS_PER_RELATION
    )
    return parse_source_id_list(raw, limit=limit)


def language_coverage_threshold(language: str) -> float:
    """Return the signed coverage floor for one language.

    Args:
        language: ``en``, ``ar``, ``mixed``, or empty.

    Returns:
        ``0.85`` for Arabic/mixed, otherwise ``0.90``.
    """

    if language in {"ar", "mixed"}:
        return MAPPING_COVERAGE_ARABIC_MIXED_MIN
    return MAPPING_COVERAGE_OVERALL_MIN


def evaluate_coverage_gates(
    slices: Sequence[CoverageSlice],
) -> tuple[bool, str]:
    """Evaluate overall and per-language mapping gates.

    English-heavy totals cannot hide an Arabic or mixed miss. Overall
    coverage must still meet 90% when English objects are present.

    Args:
        slices: Per-language coverage rows.

    Returns:
        ``(passed, reason)``. Reason is empty on success.
    """

    totals = _merge_slices(slices)
    if totals.denominator <= 0:
        return False, "coverage_empty"
    by_language: dict[str, CoverageSlice] = {}
    for item in slices:
        key = item.language or "en"
        existing = by_language.get(key)
        if existing is None:
            by_language[key] = item
            continue
        by_language[key] = CoverageSlice(
            language=key,
            object_type="all",
            method="",
            numerator=existing.numerator + item.numerator,
            denominator=existing.denominator + item.denominator,
            exclusion_count=existing.exclusion_count + item.exclusion_count,
            truncation_count=existing.truncation_count + item.truncation_count,
        )
    english_present = "en" in by_language
    if english_present and totals.ratio < MAPPING_COVERAGE_OVERALL_MIN:
        return False, "coverage_overall"
    if not english_present and totals.ratio < MAPPING_COVERAGE_ARABIC_MIXED_MIN:
        return False, "language_gate"
    for language, slice_row in by_language.items():
        if slice_row.ratio < language_coverage_threshold(language):
            return False, "language_gate"
    return True, ""


def _merge_slices(slices: Sequence[CoverageSlice]) -> CoverageSlice:
    """Sum coverage slices into one overall row.

    Args:
        slices: Per-language or per-type rows.

    Returns:
        Combined coverage slice.
    """

    return CoverageSlice(
        language="all",
        object_type="all",
        method="",
        numerator=sum(item.numerator for item in slices),
        denominator=sum(item.denominator for item in slices),
        exclusion_count=sum(item.exclusion_count for item in slices),
        truncation_count=sum(item.truncation_count for item in slices),
    )


def expected_vendor_basename(version_id: UUID) -> str:
    """Return the opaque basename required for this version.

    Args:
        version_id: Canonical document version ID.

    Returns:
        ``g-{version_id}.txt``.
    """

    return opaque_graph_source_basename(str(version_id))


def scoped_hybrid_retrieve(
    retriever: HybridRetriever,
    *,
    query: str,
    caller: CallerContext,
    version_id: UUID,
    version_candidates: Sequence[RetrievalCandidate],
    counts: MappingCallCounts,
) -> HybridRunResult:
    """Run exactly one Hybrid retrieve restricted to one document version.

    Args:
        retriever: Shared Hybrid retriever.
        query: Concatenated unresolved vendor text, already bounded.
        caller: Server-derived identity used by Hybrid RPCs.
        version_id: Version filter applied to authorized candidates.
        version_candidates: Pre-filtered authorized candidates for the version.
        counts: Mutable call counters.

    Returns:
        Hybrid run result. Callers must not invoke this more than once.

    Side Effects:
        Increments ``counts.hybrid_retrieve``. At most one retrieve.
    """

    if counts.hybrid_retrieve >= MAX_MAPPING_HYBRID_CALLS:
        raise MappingBudgetError("mapping_budget_hybrid")
    candidates = tuple(
        item for item in version_candidates if item.version_id == version_id
    )

    def _dense() -> tuple[tuple[RetrievalCandidate, ...], ...]:
        """Return the version-scoped dense list.

        Returns:
            One candidate list.
        """

        return (candidates,)

    def _bm25() -> Bm25RetrievalResult:
        """Return the version-scoped BM25 survivors.

        Returns:
            Authorized BM25 result for this version only.
        """

        return Bm25RetrievalResult(
            scanned_ids=tuple(item.chunk_id for item in candidates),
            candidates=candidates,
        )

    def _term() -> tuple[tuple[RetrievalCandidate, ...], ...]:
        """Return the version-scoped term list.

        Returns:
            One candidate list.
        """

        return (candidates,)

    counts.hybrid_retrieve += 1
    return retriever.retrieve(
        query=query,
        caller=caller,
        restrict_version_id=version_id,
        channel_jobs={"dense": _dense, "bm25": _bm25, "term": _term},
    )


def run_support_rerank(
    rerank: SupportRerankFn,
    *,
    query: str,
    passages: Sequence[RerankPassage],
    counts: MappingCallCounts,
) -> tuple[RerankRanking, ...]:
    """Run exactly one support rerank batch and require ID set equality.

    Args:
        rerank: OpenAI-only support rerank callback.
        query: Unresolved vendor/object text.
        passages: Canonical pool, already capped at 20.
        counts: Mutable call counters.

    Returns:
        Validated rankings. Empty when the pool has fewer than two passages.

    Raises:
        MappingBudgetError: If a second rerank is attempted.
        ValueError: If returned IDs are not exactly the supplied set.
    """

    if counts.support_rerank >= MAX_MAPPING_RERANK_CALLS:
        raise MappingBudgetError("mapping_budget_rerank")
    pool = tuple(passages[:MAX_MAPPING_RERANK_POOL])
    if len(pool) < 2:
        return ()
    counts.support_rerank += 1
    rankings = rerank(query, pool)
    expected = {item.candidate.chunk_id for item in pool}
    returned = {item.chunk_id for item in rankings}
    if returned != expected:
        raise ValueError("rerank_unknown_or_missing_id")
    return rankings


def assign_hybrid_support(
    rankings: Sequence[RerankRanking],
    canonicals: Sequence[CanonicalPassage],
) -> dict[UUID, ChunkMatch]:
    """Attach rerank support to canonicals at or above 0.80.

    Args:
        rankings: One-batch rerank output.
        canonicals: Canonical passages for this version.

    Returns:
        Mapping of canonical chunk id to accepted hybrid_support match.
    """

    by_id = {item.chunk_id: item for item in canonicals}
    accepted: dict[UUID, ChunkMatch] = {}
    for row in rankings:
        if row.support < MAPPING_SUPPORT_MIN:
            continue
        canonical = by_id.get(row.chunk_id)
        if canonical is None or canonical.chunk_id in accepted:
            continue
        accepted[canonical.chunk_id] = ChunkMatch(
            canonical=canonical,
            method="hybrid_support",
            score=row.support,
            source_hash=canonical.content_hash,
            target_hash=canonical.content_hash,
            source_span={"start": 0, "end": len(canonical.raw_text)},
            target_span={"start": 0, "end": len(canonical.raw_text)},
        )
    return accepted


@dataclass
class ObjectMapping:
    """One application graph object with optional accepted support.

    Attributes:
        object_type: entity, statement, or path_edge.
        object_id: Application-owned identifier.
        language: Document language.
        chunk_id: Supporting canonical chunk when accepted.
        match: Chunk match when support meets the threshold.
        available: True only when support is accepted.
        reason: Failure reason when unavailable.
        method: Mapping method or empty.
        provenance: Config/source diagnostics. Never native prose IDs.
    """

    object_type: GraphObjectType
    object_id: str
    language: str
    chunk_id: UUID | None = None
    match: ChunkMatch | None = None
    available: bool = False
    reason: str = ""
    method: str = ""
    provenance: dict[str, object] = field(default_factory=dict)
