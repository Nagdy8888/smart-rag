"""Rerank pool, policy, schema, MMR, parent expansion, and fallback types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from smart_rag_core.evaluation.schema import ExpectedProfile, QueryType
from smart_rag_core.retrieval.profiles import (
    DOCUMENT_QUOTA,
    FINAL_EVIDENCE_MAX,
    FINAL_TOKEN_BUDGET,
    MMR_CANDIDATE_DEPTH,
    MMR_LAMBDA,
    RERANK_EXCERPT_CHARS,
    RERANK_MAX_PER_DOCUMENT,
    RERANK_POOL_SIZE,
    SECTION_QUOTA,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


class RerankFallbackReason(StrEnum):
    """Typed safe routes when the OpenAI reranker cannot be used."""

    NONE = "none"
    SKIPPED_TRIVIAL_EXACT = "skipped_trivial_exact"
    INSUFFICIENT_CANDIDATES = "insufficient_candidates"
    SCHEMA_INVALID = "rerank_schema_invalid"
    INCOMPLETE = "rerank_incomplete"
    TIMEOUT = "rerank_timeout"
    CANCELLED = "rerank_cancelled"
    BUDGET_DENIED = "rerank_budget_denied"
    VERSION_MISMATCH = "rerank_version_mismatch"
    UNKNOWN_USAGE = "rerank_unknown_usage"
    REFUSAL = "rerank_refusal"
    PROVIDER_ERROR = "rerank_provider_error"


@dataclass(frozen=True, slots=True)
class RerankPassage:
    """One authorized passage eligible for the rerank pool.

    Attributes:
        candidate: Fused authorized ID.
        raw_text: Canonical citation text, never a BM25 snippet.
        section_path: Heading path.
        page_number: Optional page.
        parent_chunk_id: Parent passage when present.
        chunk_index: Order within the version.
        token_count: Stored token count or whitespace estimate.
        channels: Independent channels that retrieved this ID.
        excerpt: Bounded excerpt sent to the reranker.
    """

    candidate: RetrievalCandidate
    raw_text: str
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    parent_chunk_id: UUID | None = None
    chunk_index: int = 0
    token_count: int = 0
    channels: frozenset[str] = frozenset()
    excerpt: str = ""


@dataclass(frozen=True, slots=True)
class RerankRanking:
    """One model ranking row after application validation.

    Attributes:
        chunk_id: Supplied candidate ID.
        rank: 1-based order.
        support: Bounded ranking feature in ``[0, 1]``.
    """

    chunk_id: UUID
    rank: int
    support: float


@dataclass(frozen=True, slots=True)
class RerankUsage:
    """Observable one-operation usage. Duplicate cost remains visible.

    Attributes:
        request_id: Provider response id or mock fixture id.
        model: Allow-listed model id.
        input_tokens: Prompt tokens, or 0 when unknown/mocked.
        output_tokens: Completion tokens, or 0 when unknown/mocked.
        model_calls: ``0`` or ``1``. Hidden retries are forbidden.
    """

    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    model_calls: int


@dataclass(frozen=True, slots=True)
class ContextSelection:
    """Final Hybrid evidence after rerank, MMR, quotas, and parents.

    Attributes:
        passages: At most 12 authorized evidence units.
        rerank_order: Post-rerank or fallback RRF order of the pool.
        fallback_reason: Skip or failure reason.
        mmr_dropped: IDs dropped by MMR/quotas.
        expanded_parent_ids: Parent IDs added after recheck.
        usage: Gateway usage for the one rerank call, if any.
        skipped_counterfactual: True when a skip trigger fired.
    """

    passages: tuple[RerankPassage, ...]
    rerank_order: tuple[UUID, ...]
    fallback_reason: RerankFallbackReason
    mmr_dropped: tuple[UUID, ...]
    expanded_parent_ids: tuple[UUID, ...]
    usage: RerankUsage | None
    skipped_counterfactual: bool


def rerank_input_hash(
    *,
    query: str,
    candidate_ids: tuple[str, ...],
    excerpts: tuple[str, ...],
    prompt_sha256: str,
) -> str:
    """Hash the canonical rerank request for echo-back verification.

    Args:
        query: Original query.
        candidate_ids: Pool IDs as strings.
        excerpts: Bounded canonical excerpts aligned with IDs.
        prompt_sha256: Pinned prompt digest.

    Returns:
        SHA-256 hex digest.
    """

    payload = {
        "query": query,
        "candidate_ids": list(candidate_ids),
        "excerpts": list(excerpts),
        "prompt_sha256": prompt_sha256,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def excerpt_text(raw_text: str, *, limit: int = RERANK_EXCERPT_CHARS) -> str:
    """Clamp canonical text for the rerank request.

    Args:
        raw_text: Canonical passage.
        limit: Maximum characters.

    Returns:
        Bounded excerpt. Empty input stays empty.
    """

    stripped = raw_text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit]


def build_rerank_pool(
    passages: tuple[RerankPassage, ...],
) -> tuple[RerankPassage, ...]:
    """Collapse duplicates and cap the pool at 20 with five per document.

    Args:
        passages: Fused-order authorized passages with canonical text.

    Returns:
        Pool in fused order after per-document and global caps.
    """

    seen: set[UUID] = set()
    per_document: dict[UUID, int] = {}
    selected: list[RerankPassage] = []
    for item in passages:
        chunk_id = item.candidate.chunk_id
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        document_id = item.candidate.document_id
        used = per_document.get(document_id, 0)
        if used >= RERANK_MAX_PER_DOCUMENT:
            continue
        per_document[document_id] = used + 1
        selected.append(
            RerankPassage(
                candidate=item.candidate,
                raw_text=item.raw_text,
                section_path=item.section_path,
                page_number=item.page_number,
                parent_chunk_id=item.parent_chunk_id,
                chunk_index=item.chunk_index,
                token_count=item.token_count or max(1, len(item.raw_text.split())),
                channels=item.channels,
                excerpt=excerpt_text(item.raw_text),
            )
        )
        if len(selected) >= RERANK_POOL_SIZE:
            break
    return tuple(selected)


def should_skip_trivial_exact(
    profile: ExpectedProfile,
    pool: tuple[RerankPassage, ...],
) -> bool:
    """Skip OpenAI rerank only for a fully supported trivial exact lookup.

    Numeric score gaps never qualify. The winner must be independently
    present in at least two applicable channels, and required codes or
    quoted phrases plus filters must be complete.

    Args:
        profile: Typed query profile.
        pool: Capped rerank pool in fused order.

    Returns:
        True only for the plan's trivial exact skip.
    """

    if len(pool) < 2:
        return False
    query_type = str(profile.query_type.value)
    if query_type != QueryType.EXACT_IDENTIFIER.value:
        return False
    codes = profile.codes.value if isinstance(profile.codes.value, list) else []
    quoted = (
        profile.quoted_phrases.value
        if isinstance(profile.quoted_phrases.value, list)
        else []
    )
    if not codes and not quoted:
        return False
    filters = profile.metadata_filters.value
    if isinstance(filters, list) and any(
        "=" in str(item) and str(item).split("=", 1)[0] not in {"tag", "language"}
        for item in filters
    ):
        return False
    winner_channels = pool[0].channels
    return len(winner_channels) >= 2


def rerank_json_schema(
    candidate_ids: tuple[str, ...],
    *,
    input_hash: str,
) -> dict[str, object]:
    """Build a request-specific strict JSON schema.

    Args:
        candidate_ids: Canonical chunk UUID strings in pool order.
        input_hash: SHA-256 of the canonical request payload.

    Returns:
        OpenAI ``json_schema`` document with an ID enum.

    Raises:
        ValueError: If the pool is empty or larger than 20.
    """

    if not candidate_ids or len(candidate_ids) > RERANK_POOL_SIZE:
        raise ValueError("rerank_pool_size_invalid")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "input_hash", "rankings"],
        "properties": {
            "status": {"type": "string", "enum": ["complete"]},
            "input_hash": {"type": "string", "minLength": 64, "maxLength": 64},
            "rankings": {
                "type": "array",
                "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["chunk_id", "rank", "support"],
                    "properties": {
                        "chunk_id": {"type": "string", "enum": list(candidate_ids)},
                        "rank": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": len(candidate_ids),
                        },
                        "support": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
            },
        },
    }


class RerankRowModel(BaseModel):
    """One ranking row after JSON Schema validation.

    Attributes:
        chunk_id: Candidate UUID string.
        rank: 1-based rank.
        support: Ranking feature in ``[0, 1]``, not a probability.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    rank: int = Field(ge=1)
    support: float

    @field_validator("rank", mode="before")
    @classmethod
    def reject_boolean_rank(cls, value: object) -> object:
        """Reject ``bool`` values that would otherwise pass as integers.

        Args:
            value: Raw rank field.

        Returns:
            Unchanged non-boolean value.

        Raises:
            ValueError: If the value is a boolean.
        """

        if isinstance(value, bool):
            raise ValueError("rerank_rank_invalid")
        return value

    @field_validator("support", mode="before")
    @classmethod
    def reject_invalid_support(cls, value: object) -> object:
        """Reject booleans and out-of-range support scores.

        Args:
            value: Raw support field.

        Returns:
            Unchanged in-range numeric value.

        Raises:
            ValueError: If support is a boolean or outside ``[0, 1]``.
        """

        if isinstance(value, bool):
            raise ValueError("rerank_support_invalid")
        if isinstance(value, int | float) and (value < 0.0 or value > 1.0):
            raise ValueError("rerank_support_out_of_bounds")
        return value


class RerankPayloadModel(BaseModel):
    """Strict rerank JSON object before application set-equality checks.

    Attributes:
        status: Must be ``complete``.
        input_hash: Echo of the request digest.
        rankings: One row per supplied candidate.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["complete"]
    input_hash: str = Field(min_length=64, max_length=64)
    rankings: list[RerankRowModel]


def validate_rerank_payload(
    payload: object,
    *,
    candidate_ids: tuple[UUID, ...],
    input_hash: str,
) -> tuple[RerankRanking, ...]:
    """Enforce set equality, uniqueness, order, and support bounds.

    A schema-valid payload can still be semantically invalid.

    Args:
        payload: Parsed JSON object.
        candidate_ids: Exact supplied ID set in pool order.
        input_hash: Canonical request digest that must be echoed.

    Returns:
        Rankings sorted by rank ascending.

    Raises:
        ValueError: If status, IDs, ranks, or support violate the contract.
    """

    try:
        body = RerankPayloadModel.model_validate(payload)
    except ValidationError as error:
        messages = " ".join(str(item.get("msg", "")) for item in error.errors())
        locations = [item.get("loc", ()) for item in error.errors()]
        if "rerank_support_out_of_bounds" in messages:
            raise ValueError("rerank_support_out_of_bounds") from error
        if "rerank_support_invalid" in messages:
            raise ValueError("rerank_support_invalid") from error
        if "rerank_rank_invalid" in messages:
            raise ValueError("rerank_rank_invalid") from error
        if any(loc and loc[-1] == "status" for loc in locations):
            raise ValueError("rerank_incomplete") from error
        raise ValueError("rerank_schema_invalid") from error
    if body.input_hash != input_hash:
        raise ValueError("rerank_input_hash_mismatch")
    if len(body.rankings) != len(candidate_ids):
        raise ValueError("rerank_ranking_length")
    expected = {str(item) for item in candidate_ids}
    seen_ids: set[str] = set()
    seen_ranks: set[int] = set()
    parsed: list[RerankRanking] = []
    for row in body.rankings:
        if row.chunk_id not in expected:
            raise ValueError("rerank_unknown_or_missing_id")
        if row.chunk_id in seen_ids:
            raise ValueError("rerank_duplicate_id")
        if row.rank > len(candidate_ids) or row.rank in seen_ranks:
            raise ValueError("rerank_rank_invalid")
        seen_ids.add(row.chunk_id)
        seen_ranks.add(row.rank)
        parsed.append(
            RerankRanking(
                chunk_id=UUID(row.chunk_id),
                rank=row.rank,
                support=float(row.support),
            )
        )
    if seen_ids != expected:
        raise ValueError("rerank_id_set_mismatch")
    parsed.sort(key=lambda item: item.rank)
    return tuple(parsed)


def _jaccard(left: str, right: str) -> float:
    """Token Jaccard on ``arabic_norm_v1`` forms.

    Args:
        left: First text.
        right: Second text.

    Returns:
        Similarity in ``[0, 1]``.
    """

    left_tokens = set(normalize_arabic_v1(left).split())
    right_tokens = set(normalize_arabic_v1(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def apply_mmr(
    ordered: tuple[RerankPassage, ...],
    *,
    query: str,
    lambda_mult: float = MMR_LAMBDA,
    document_quota: int = DOCUMENT_QUOTA,
    section_quota: int = SECTION_QUOTA,
    limit: int = FINAL_EVIDENCE_MAX,
) -> tuple[tuple[RerankPassage, ...], tuple[UUID, ...]]:
    """Select diverse evidence with per-document and per-section quotas.

    Similarity source is token Jaccard on ``arabic_norm_v1`` excerpts.
    Tie-break is canonical chunk ID ascending.

    Args:
        ordered: Post-rerank (or RRF fallback) pool.
        query: Original query.
        lambda_mult: Relevance versus diversity mix.
        document_quota: Max selected passages per document.
        section_quota: Max selected passages per first heading.
        limit: Final evidence cap.

    Returns:
        Selected passages and dropped IDs.
    """

    depth = ordered[:MMR_CANDIDATE_DEPTH]
    remaining = list(depth)
    selected: list[RerankPassage] = []
    doc_counts: dict[UUID, int] = {}
    section_counts: dict[str, int] = {}
    while remaining and len(selected) < limit:

        def score(item: RerankPassage) -> tuple[float, str]:
            """MMR objective with stable ID tie-break.

            Args:
                item: Candidate still in the pool.

            Returns:
                Sort key: higher MMR first, then canonical ID.
            """

            relevance = _jaccard(query, item.excerpt or item.raw_text)
            diversity = 0.0
            if selected:
                diversity = max(
                    _jaccard(
                        item.excerpt or item.raw_text, other.excerpt or other.raw_text
                    )
                    for other in selected
                )
            return (
                -(lambda_mult * relevance - (1.0 - lambda_mult) * diversity),
                str(item.candidate.chunk_id),
            )

        remaining.sort(key=score)
        pick = remaining.pop(0)
        document_id = pick.candidate.document_id
        section = pick.section_path[0] if pick.section_path else ""
        if doc_counts.get(document_id, 0) >= document_quota:
            continue
        if section and section_counts.get(section, 0) >= section_quota:
            continue
        selected.append(pick)
        doc_counts[document_id] = doc_counts.get(document_id, 0) + 1
        if section:
            section_counts[section] = section_counts.get(section, 0) + 1
    selected_ids = {item.candidate.chunk_id for item in selected}
    dropped = tuple(
        item.candidate.chunk_id
        for item in depth
        if item.candidate.chunk_id not in selected_ids
    )
    return tuple(selected), dropped


def trim_token_budget(
    passages: tuple[RerankPassage, ...],
    *,
    budget: int = FINAL_TOKEN_BUDGET,
    limit: int = FINAL_EVIDENCE_MAX,
) -> tuple[RerankPassage, ...]:
    """Keep at most 12 units inside the token budget.

    Args:
        passages: Ordered evidence including expanded parents.
        budget: Token ceiling.
        limit: Unit ceiling.

    Returns:
        Prefix that fits both bounds.
    """

    kept: list[RerankPassage] = []
    tokens = 0
    for item in passages:
        cost = item.token_count or max(1, len(item.raw_text.split()))
        if len(kept) >= limit or tokens + cost > budget:
            break
        kept.append(item)
        tokens += cost
    return tuple(kept)
