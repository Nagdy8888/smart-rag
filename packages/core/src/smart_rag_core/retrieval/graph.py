"""Application-owned graph retrieval and indexing protocols.

LightRAG remains a replaceable lead generator behind these protocols.
Vendor descriptions, keywords, file paths, reference ordinals, source
hashes, track IDs, normalized entity names, and relation endpoint pairs are
never application integrity, idempotency, or citation identifiers.
Production insert/query wiring is intentionally absent from this module.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.models.env_pins import (
    ALLOWED_LIGHTRAG_LLM_MODEL_IDS,
    LIGHTRAG_LLM_MODEL_ID,
    OPENAI_CHAT_MODEL_ID,
)

if LIGHTRAG_LLM_MODEL_ID not in ALLOWED_LIGHTRAG_LLM_MODEL_IDS:
    raise RuntimeError("pinned LightRAG LLM model is not allow-listed")

LIGHTRAG_PACKAGE_NAME = "lightrag-hku"
LIGHTRAG_PINNED_VERSION = "1.5.6"
LIGHTRAG_WHEEL_SHA256 = (
    "81b8aa8b09c11e446f94b53dbbef8d6becd900a7a44685fca95ff59cf5c8e457"
)
LIGHTRAG_SDIST_SHA256 = (
    "1c5afb96db5cd9f0b13b7d8d93ce1daf5a51bf7e2f74fe5ce4fe3eb9be03e77f"
)
LIGHTRAG_RELEASE_COMMIT = "b33c6b0812cddf39206e48a9810112e51f025274"
LIGHTRAG_LICENSE = "MIT"
GRAPH_FIELD_SEP = "<SEP>"
DEFAULT_MAX_SOURCE_IDS_PER_ENTITY = 200
DEFAULT_MAX_SOURCE_IDS_PER_RELATION = 200
SELECTED_KV_STORAGE = "PGKVStorage"
SELECTED_VECTOR_STORAGE = "PGVectorStorage"
SELECTED_GRAPH_STORAGE = "PGTableGraphStorage"
SELECTED_DOC_STATUS_STORAGE = "PGDocStatusStorage"
FORBIDDEN_AGE_GRAPH_STORAGE = "PGGraphStorage"
LIGHTRAG_CHUNK_TOKEN_SIZE = 1200
LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE = 100
LIGHTRAG_TIKTOKEN_MODEL = OPENAI_CHAT_MODEL_ID
LIGHTRAG_LLM_MAX_OUTPUT_TOKENS = 4000
LIGHTRAG_LLM_MAX_INPUT_CHARS = 65_536
LIGHTRAG_LLM_MAX_OUTPUT_CHARS = 32_768
LIGHTRAG_LLM_TIMEOUT_SECONDS = 90.0
LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS = 120
# LightRAG 1.5.6 watchdog: func=timeout, worker=timeout*2, health=timeout*2+15.
# Keep this at the vendor default. Do not raise it to hide blocked embedding calls.
LIGHTRAG_EMBEDDING_VENDOR_TIMEOUT_SECONDS = 30
# OpenAI HTTP timeout for LightRAG embeddings. Must stay below the watchdog
# func timeout so the SDK fails closed before LightRAG force-kills the batch.
# The OpenAI Python SDK default is 600 seconds when timeout is omitted.
LIGHTRAG_EMBEDDING_PROVIDER_TIMEOUT_SECONDS = 20.0
# Hybrid ingestion embedding HTTP timeout. Independent of the LightRAG watchdog.
OPENAI_EMBEDDING_TIMEOUT_SECONDS = 120.0
# Standard API list prices from https://openai.com/api/pricing/, verified
# 2026-08-19. These produce an estimate; the provider invoice remains canonical.
LIGHTRAG_LLM_INPUT_USD_PER_MILLION = "0.20"
LIGHTRAG_LLM_CACHED_INPUT_USD_PER_MILLION = "0.02"
LIGHTRAG_LLM_OUTPUT_USD_PER_MILLION = "1.20"
LIGHTRAG_LLM_PRICING_VERSION = "openai-api-pricing-2026-08-19"
QUALIFICATION_POSTGRES_MAX_CONNECTIONS = 2
QUALIFICATION_POSTGRES_CONNECTION_RETRIES = 0
RUNTIME_POSTGRES_MAX_CONNECTIONS = 4
LIGHTRAG_SEARCH_PATH = "lightrag,extensions,public"
LIGHTRAG_RUNTIME_ROLE = "app_lightrag"
DEFAULT_GRAPH_WORKSPACE = "company_default"
RUNTIME_COSINE_BETTER_THAN_THRESHOLD = 0.2
ADAPTER_MAX_GRAPH_CANDIDATES = 12
ADAPTER_MAX_HOPS = 3
ADAPTER_MAX_PATHS = 6
ADAPTER_DEFAULT_DEADLINE_SECONDS = 45.0
GLOBAL_STEERING_MAX = 3
INSPECTION_MAX_DEPTH = 3
INSPECTION_MAX_ROWS = 200
INSPECTION_STATEMENT_TIMEOUT = "3s"
INSPECTION_DEADLINE_SECONDS = 10.0
GRAPH_SURVIVAL_FALLBACK_THRESHOLD = 0.50
GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD = 0.80
GRAPH_SURVIVAL_ROLLING_WINDOW = 20
GRAPH_SOURCE_ENVELOPE_VERSION = "graph_source_envelope_v1"
_GRAPH_SOURCE_ENVELOPE_PREFIX = "<<smart-rag-graph-source:"


class GraphLeadEntity(BaseModel):
    """One vendor entity lead. Never a citation.

    Attributes:
        entity_name: Vendor-normalized name used only for candidate discovery.
        entity_type: Optional vendor type string.
        source_ids: Delimiter-split internal chunk tokens. Ambiguous or
            truncated sets are unavailable rather than silently complete.
    """

    model_config = ConfigDict(frozen=True)

    entity_name: str = Field(min_length=1, max_length=512)
    entity_type: str | None = Field(default=None, max_length=128)
    source_ids: tuple[str, ...] = ()


class GraphLeadRelation(BaseModel):
    """One vendor relation lead. Never a citation.

    Attributes:
        src_id: Vendor source entity name. Not an application predicate ID.
        tgt_id: Vendor target entity name. Not an application predicate ID.
        source_ids: Delimiter-split internal chunk tokens.
    """

    model_config = ConfigDict(frozen=True)

    src_id: str = Field(min_length=1, max_length=512)
    tgt_id: str = Field(min_length=1, max_length=512)
    source_ids: tuple[str, ...] = ()


class GraphLeadChunk(BaseModel):
    """One vendor chunk lead. Never canonical evidence.

    Attributes:
        chunk_id: Vendor internal chunk token. Not a canonical chunk UUID.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(min_length=1, max_length=256)


class GraphLeadSet(BaseModel):
    """Bounded structured leads returned by ``GraphRetriever``.

    Descriptions, relationship keywords, file paths, and query-local
    reference ordinals are intentionally omitted so they cannot be treated
    as evidence identifiers.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["local", "hybrid", "global"]
    entities: tuple[GraphLeadEntity, ...] = ()
    relations: tuple[GraphLeadRelation, ...] = ()
    chunks: tuple[GraphLeadChunk, ...] = ()
    high_level_keywords: tuple[str, ...] = ()
    low_level_keywords: tuple[str, ...] = ()


class GraphQueryBounds(BaseModel):
    """Adapter-owned limits that wrap vendor ``QueryParam`` values.

    Native engine settings do not replace these controls.
    """

    model_config = ConfigDict(frozen=True)

    top_k: int = Field(ge=1, le=ADAPTER_MAX_GRAPH_CANDIDATES)
    chunk_top_k: int = Field(ge=1, le=ADAPTER_MAX_GRAPH_CANDIDATES)
    max_entity_tokens: int = Field(ge=1, le=12_000)
    max_relation_tokens: int = Field(ge=1, le=16_000)
    max_total_tokens: int = Field(ge=1, le=60_000)
    deadline_seconds: float = Field(gt=0, le=ADAPTER_DEFAULT_DEADLINE_SECONDS)
    max_hops: int = Field(default=ADAPTER_MAX_HOPS, ge=1, le=ADAPTER_MAX_HOPS)
    max_paths: int = Field(default=ADAPTER_MAX_PATHS, ge=1, le=ADAPTER_MAX_PATHS)


class GraphIndexEnqueueResult(BaseModel):
    """Monitoring metadata from a vendor insert enqueue.

    Attributes:
        document_id: Caller-supplied canonical document version ID.
        track_id: Vendor monitoring token. Never an idempotency key.
        status: Terminal or in-flight vendor status label.
    """

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1, max_length=255)
    track_id: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=64)


class GraphIndexDeleteResult(BaseModel):
    """Vendor document deletion outcome.

    Attributes:
        document_id: Document ID submitted for deletion.
        status: ``success``, ``not_found``, ``not_allowed``, or ``fail``.
        message: Vendor status text. Not parsed for evidence.
    """

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1, max_length=255)
    status: Literal["success", "not_found", "not_allowed", "fail"]
    message: str = Field(default="", max_length=2_048)


class GraphLimitationCode(StrEnum):
    """Typed query-time graph limitation signals. Payloads never leak ACL."""

    GRAPH_SURVIVAL_BELOW_THRESHOLD = "graph_survival_below_threshold"
    GRAPH_PARTIAL_READINESS = "graph_partial_readiness"
    GRAPH_ACL_BLINDNESS = "graph_acl_blindness"
    TEMPORAL_GRAPH_LIMITATION = "temporal_graph_limitation"
    GRAPH_OUTAGE = "graph_outage"
    GRAPH_UPDATING = "graph_updating"
    GRAPH_FILTERED_DIRTY = "graph_filtered_dirty"
    GLOBAL_STEERING_ONLY = "global_steering_only"
    GRAPH_EMPTY = "graph_empty"
    GRAPH_DEADLINE = "graph_deadline"
    GRAPH_CANCELLED = "graph_cancelled"


class GraphRetriever(Protocol):
    """Project protocol for structured graph lead retrieval.

    The runtime adapter implements these methods. Callers resolve leads
    through the authoritative resolver before treating anything as evidence.
    """

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Return local-mode entity-centered leads.

        Args:
            query: Original user query text.
            hl_keywords: Non-empty high-level keywords from the query profile.
            ll_keywords: Non-empty low-level keywords from the query profile.
            bounds: Adapter-owned candidate and token limits.

        Returns:
            Structured leads. Callers must resolve them to canonical passages.

        Raises:
            ValueError: If either keyword list is empty.
        """

        ...

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Return graph-hybrid leads from both local and global signals.

        Args:
            query: Original user query text.
            hl_keywords: Non-empty high-level keywords.
            ll_keywords: Non-empty low-level keywords.
            bounds: Adapter-owned limits.

        Returns:
            Structured leads, never rendered context prose.
        """

        ...

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: GraphQueryBounds,
    ) -> GraphLeadSet:
        """Return at most three topic/entity steering expansions.

        Global output is never evidence.

        Args:
            query: Original user query text.
            hl_keywords: Non-empty high-level keywords.
            ll_keywords: Non-empty low-level keywords.
            bounds: Adapter-owned limits.

        Returns:
            Steering leads only.
        """

        ...


class GraphIndexer(Protocol):
    """Project protocol for graph insert and delete. Unimplemented in Packet 1."""

    async def enqueue_insert(
        self,
        *,
        document_id: str,
        text: str,
        source_token: str,
    ) -> GraphIndexEnqueueResult:
        """Enqueue normalized document-version text for graph indexing.

        Args:
            document_id: Canonical document version ID used as the vendor ID.
            text: Normalized version text. Not a canonical chunk set.
            source_token: Unique opaque non-secret basename token.

        Returns:
            Monitoring metadata. ``track_id`` is never idempotency.
        """

        ...

    async def enqueue_insert_sources(
        self,
        *,
        texts: tuple[str, ...],
        document_ids: tuple[str, ...],
        source_tokens: tuple[str, ...],
        track_id: str | None = None,
    ) -> GraphIndexEnqueueResult:
        """Enqueue one bounded list of canonical-passage sources.

        Args:
            texts: Envelope-bound passage texts, already 1:1 with IDs.
            document_ids: Deterministic ``{version_id}:{chunk_id}`` source IDs.
            source_tokens: Unique opaque basenames, 1:1 with ``document_ids``.
            track_id: Optional monitoring token. Never idempotency.

        Returns:
            Monitoring metadata for the version job. ``document_id`` is the
            canonical version ID, not a passage source ID.
        """

        ...

    async def delete_document(
        self,
        *,
        document_id: str,
        delete_llm_cache: bool = True,
    ) -> GraphIndexDeleteResult:
        """Delete one vendor document and optionally its LLM cache.

        Args:
            document_id: Canonical document version ID.
            delete_llm_cache: When true, request privacy cache deletion.

        Returns:
            Vendor deletion status. Unsupported statuses fail closed.
        """

        ...


def apply_query_bounds(
    *,
    top_k: int,
    chunk_top_k: int,
    max_entity_tokens: int,
    max_relation_tokens: int,
    max_total_tokens: int,
    deadline_seconds: float,
) -> GraphQueryBounds:
    """Clamp caller values to adapter-owned limits.

    Args:
        top_k: Requested entity/relation candidate count.
        chunk_top_k: Requested chunk candidate count.
        max_entity_tokens: Requested entity token budget.
        max_relation_tokens: Requested relation token budget.
        max_total_tokens: Requested total token budget.
        deadline_seconds: Remaining operation deadline.

    Returns:
        Frozen bounds that never exceed adapter maxima.

    Raises:
        ValueError: If any input is not strictly positive.
    """

    if (
        min(
            top_k,
            chunk_top_k,
            max_entity_tokens,
            max_relation_tokens,
            max_total_tokens,
        )
        < 1
    ):
        raise ValueError("graph_query_bounds_must_be_positive")
    if deadline_seconds <= 0:
        raise ValueError("graph_query_deadline_must_be_positive")
    return GraphQueryBounds(
        top_k=min(top_k, ADAPTER_MAX_GRAPH_CANDIDATES),
        chunk_top_k=min(chunk_top_k, ADAPTER_MAX_GRAPH_CANDIDATES),
        max_entity_tokens=min(max_entity_tokens, 12_000),
        max_relation_tokens=min(max_relation_tokens, 16_000),
        max_total_tokens=min(max_total_tokens, 60_000),
        deadline_seconds=min(deadline_seconds, ADAPTER_DEFAULT_DEADLINE_SECONDS),
    )


def inspection_query_bounds() -> GraphQueryBounds:
    """Return adapter bounds clamped to the inspection 10-second deadline.

    Returns:
        Frozen bounds with inspection deadline and candidate maxima.
    """

    return apply_query_bounds(
        top_k=ADAPTER_MAX_GRAPH_CANDIDATES,
        chunk_top_k=ADAPTER_MAX_GRAPH_CANDIDATES,
        max_entity_tokens=12_000,
        max_relation_tokens=16_000,
        max_total_tokens=60_000,
        deadline_seconds=INSPECTION_DEADLINE_SECONDS,
    )


def clamp_graph_leads(leads: GraphLeadSet, bounds: GraphQueryBounds) -> GraphLeadSet:
    """Apply application candidate caps and stable lexicographic tie-breaks.

    Native engine ``top_k`` does not replace this clamp. Relation leads are
    the graph candidates when present; otherwise entity leads are. Endpoint
    entities of kept relations are retained for resolution and do not count
    as extra candidates.

    Args:
        leads: Structured vendor leads after parse.
        bounds: Adapter-owned candidate limits.

    Returns:
        Frozen lead set within application maxima.
    """

    relations = tuple(
        sorted(leads.relations, key=lambda item: (item.src_id, item.tgt_id))
    )[: bounds.top_k]
    if relations:
        needed = {item.src_id for item in relations} | {
            item.tgt_id for item in relations
        }
        entities = tuple(
            item
            for item in sorted(leads.entities, key=lambda item: item.entity_name)
            if item.entity_name in needed
        )
        source_tokens = {token for rel in relations for token in rel.source_ids}
    else:
        entities = tuple(sorted(leads.entities, key=lambda item: item.entity_name))[
            : bounds.top_k
        ]
        source_tokens = {token for ent in entities for token in ent.source_ids}
    referenced = tuple(
        item
        for item in sorted(leads.chunks, key=lambda item: item.chunk_id)
        if item.chunk_id in source_tokens
    )[: bounds.chunk_top_k]
    chunks = (
        referenced
        or tuple(sorted(leads.chunks, key=lambda item: item.chunk_id))[
            : bounds.chunk_top_k
        ]
    )
    return GraphLeadSet(
        mode=leads.mode,
        entities=entities,
        relations=relations,
        chunks=chunks,
        high_level_keywords=leads.high_level_keywords,
        low_level_keywords=leads.low_level_keywords,
    )


def returned_graph_candidate_count(leads: GraphLeadSet) -> int:
    """Count application graph candidates after the lead clamp.

    Args:
        leads: Clamped lead set.

    Returns:
        Relation count, or entity count when there are no relations.
    """

    if leads.relations:
        return len(leads.relations)
    return len(leads.entities)


def graph_survival_ratio(*, supported: int, returned: int) -> float | None:
    """Return supported/returned, or ``None`` when no candidates were returned.

    Args:
        supported: Leads that survived every resolver check.
        returned: Clamped vendor candidates before resolver drops.

    Returns:
        Closed unit interval, or ``None`` when ``returned`` is zero.
    """

    if returned <= 0:
        return None
    return supported / returned


def workspace_limitation_code(
    state: str | None, *, pointer_attached: bool
) -> GraphLimitationCode | None:
    """Map workspace pointer/state to a fail-closed limitation, if any.

    Combined fallback is Phase 6. Packet 5 returns the typed signal only.

    Args:
        state: Durable workspace state, or ``None`` when the row is missing.
        pointer_attached: Whether the singleton pointer names a workspace.

    Returns:
        Limitation code, or ``None`` when the workspace is queryable.
    """

    if not pointer_attached or state is None:
        return GraphLimitationCode.GRAPH_OUTAGE
    if state == "active":
        return None
    if state == "updating":
        return GraphLimitationCode.GRAPH_UPDATING
    if state == "filtered_dirty":
        return GraphLimitationCode.GRAPH_FILTERED_DIRTY
    return GraphLimitationCode.GRAPH_OUTAGE


def clamp_global_steering(leads: GraphLeadSet) -> GraphLeadSet:
    """Keep at most three topic/entity expansions and drop evidence fields.

    Args:
        leads: Parsed global-mode leads.

    Returns:
        Steering-only lead set. Relations and chunks are cleared.
    """

    entities = tuple(sorted(leads.entities, key=lambda item: item.entity_name))[
        :GLOBAL_STEERING_MAX
    ]
    return GraphLeadSet(
        mode="global",
        entities=entities,
        relations=(),
        chunks=(),
        high_level_keywords=leads.high_level_keywords,
        low_level_keywords=leads.low_level_keywords,
    )


class ProseContextRejectedError(ValueError):
    """Raised when a caller attempts to parse rendered context as evidence."""


def reject_rendered_context_parser(rendered_context: str) -> None:
    """Fail closed if human-rendered vendor context is offered as data.

    Args:
        rendered_context: ``only_need_context`` prose or any similar string.

    Raises:
        ProseContextRejectedError: Always. Packet 1 forbids prose parsers.
    """

    raise ProseContextRejectedError(
        f"rendered_graph_context_is_not_evidence:{len(rendered_context)}"
    )


class SourceIdContractError(ValueError):
    """Raised when vendor source-id lists are empty, ambiguous, or capped."""


def parse_source_id_list(raw: str | None, *, limit: int) -> tuple[str, ...]:
    """Split a vendor source-id scalar with the pinned delimiter.

    Args:
        raw: Delimiter-joined source token list, or ``None``.
        limit: Pinned per-object source retention cap.

    Returns:
        Ordered unique source tokens.

    Raises:
        SourceIdContractError: If the list is empty, contains blank tokens,
            or reaches the retention cap (possible truncation).
    """

    if raw is None or not raw.strip():
        raise SourceIdContractError("source_id_list_empty")
    parts = tuple(token.strip() for token in raw.split(GRAPH_FIELD_SEP))
    if any(not token for token in parts):
        raise SourceIdContractError("source_id_list_ambiguous")
    unique = tuple(dict.fromkeys(parts))
    if len(unique) != len(parts):
        raise SourceIdContractError("source_id_list_ambiguous")
    if len(unique) >= limit:
        raise SourceIdContractError("source_id_list_truncated")
    return unique


_DOCUMENT_VERSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ENVELOPE_RE = re.compile(
    r"^<<smart-rag-graph-source:"
    + re.escape(GRAPH_SOURCE_ENVELOPE_VERSION)
    + r":([A-Za-z0-9._:-]{1,128})>>\n",
)


class GraphSourceEnvelopeError(ValueError):
    """Raised when identity-bound graph source text cannot be formed."""


def bind_graph_source_text(*, document_version_id: str, normalized_text: str) -> str:
    """Bind vendor content identity to the canonical document version ID.

    LightRAG 1.5.6 deduplicates on content hash, not caller-supplied IDs.
    Distinct canonical versions with identical normalized text must remain
    independent vendor documents so deletion and attribution stay separate.
    This envelope is a non-secret, reversible, versioned header. It is not
    a random salt and does not alter canonical Hybrid chunks.

    Args:
        document_version_id: Canonical version ID or passage source ID
            (``{version_id}:{chunk_id}``) used as vendor ``ids`` and as the
            envelope token.
        normalized_text: Version text that would otherwise be inserted raw.

    Returns:
        Envelope header plus the original normalized text.

    Raises:
        GraphSourceEnvelopeError: If the ID is empty or not a safe token.
    """

    if not _DOCUMENT_VERSION_ID_RE.fullmatch(document_version_id):
        raise GraphSourceEnvelopeError("graph_source_envelope_invalid_document_id")
    return (
        f"{_GRAPH_SOURCE_ENVELOPE_PREFIX}{GRAPH_SOURCE_ENVELOPE_VERSION}:"
        f"{document_version_id}>>\n{normalized_text}"
    )


def strip_graph_source_envelope(text: str) -> str:
    """Remove the identity envelope when present.

    Mapping and canonical hash matching use the remainder. Missing envelopes
    are returned unchanged so unmapped vendor chunks stay diagnosable.

    Args:
        text: Vendor chunk or full-document text.

    Returns:
        Text without a leading identity envelope, or the original string.
    """

    match = _ENVELOPE_RE.match(text)
    if match is None:
        return text
    return text[match.end() :]


def opaque_graph_source_basename(document_version_id: str) -> str:
    """Return a unique opaque non-secret basename token for one version.

    The token is derived from the canonical version ID. It is never a signed
    URL and must not be reused across versions.

    Args:
        document_version_id: Canonical document version ID.

    Returns:
        Basename such as ``g-{version_id}.txt``.

    Raises:
        GraphSourceEnvelopeError: If the ID is empty or not a safe token.
    """

    if not _DOCUMENT_VERSION_ID_RE.fullmatch(document_version_id):
        raise GraphSourceEnvelopeError("graph_source_basename_invalid_document_id")
    return f"g-{document_version_id}.txt"


def canonical_passage_source_id(*, version_id: UUID, chunk_id: UUID) -> str:
    """Return the deterministic LightRAG source ID for one canonical passage.

    Args:
        version_id: Canonical document version ID.
        chunk_id: Canonical chunk UUID.

    Returns:
        ``{version_id}:{chunk_id}``. Safe for the identity envelope.

    Raises:
        GraphSourceEnvelopeError: If the composed token is not envelope-safe.
    """

    token = f"{version_id}:{chunk_id}"
    if not _DOCUMENT_VERSION_ID_RE.fullmatch(token):
        raise GraphSourceEnvelopeError("graph_source_passage_id_invalid")
    return token


def parse_canonical_passage_source_id(source_id: str) -> tuple[UUID, UUID]:
    """Parse a deterministic passage source ID into version and chunk UUIDs.

    Args:
        source_id: ``{version_id}:{chunk_id}`` token.

    Returns:
        Canonical version ID and chunk ID.

    Raises:
        GraphSourceEnvelopeError: If the token is not two UUIDs.
    """

    version_raw, separator, chunk_raw = source_id.partition(":")
    if separator != ":" or not version_raw or not chunk_raw:
        raise GraphSourceEnvelopeError("graph_source_passage_id_invalid")
    try:
        return UUID(version_raw), UUID(chunk_raw)
    except ValueError as exc:
        raise GraphSourceEnvelopeError("graph_source_passage_id_invalid") from exc


def opaque_passage_source_basename(*, version_id: UUID, chunk_id: UUID) -> str:
    """Return the opaque basename for one canonical-passage LightRAG source.

    Args:
        version_id: Canonical document version ID.
        chunk_id: Canonical chunk UUID.

    Returns:
        Basename such as ``g-{version_id}-{chunk_id}.txt``.

    Raises:
        GraphSourceEnvelopeError: If the composed token is not envelope-safe.
    """

    token = f"{version_id}-{chunk_id}"
    if not _DOCUMENT_VERSION_ID_RE.fullmatch(token):
        raise GraphSourceEnvelopeError("graph_source_basename_invalid_document_id")
    return f"g-{token}.txt"


def version_vendor_source_ids(
    version_id: UUID, chunk_ids: tuple[UUID, ...]
) -> tuple[str, ...]:
    """Return legacy whole-version plus per-passage vendor IDs.

    Args:
        version_id: Canonical version used as the historical vendor ID.
        chunk_ids: Canonical chunk IDs for the version, in chunk order.

    Returns:
        Unique IDs to insert or delete for this version. The legacy
        ``str(version_id)`` entry is first so old whole-document sources are
        always included in cleanup.
    """

    passage_ids = tuple(
        canonical_passage_source_id(version_id=version_id, chunk_id=chunk_id)
        for chunk_id in chunk_ids
    )
    return tuple(dict.fromkeys((str(version_id), *passage_ids)))


def graph_chunker_config_snapshot() -> dict[str, object]:
    """Return the pinned LightRAG chunker overlay recorded on workspace rows.

    Returns:
        JSON-safe mapping of chunk token size, overlap, tokenizer, and pin.
    """

    return {
        "lightrag_version": LIGHTRAG_PINNED_VERSION,
        "graph_pipeline_version": "graph_pipeline_v1",
        "chunk_token_size": LIGHTRAG_CHUNK_TOKEN_SIZE,
        "chunk_overlap_token_size": LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE,
        "tiktoken_model_name": LIGHTRAG_TIKTOKEN_MODEL,
        "llm_model_max_async": 1,
        "embedding_func_max_async": 1,
        "max_parallel_insert": 1,
    }
