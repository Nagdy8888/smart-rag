"""Application-owned graph retrieval and indexing protocols.

LightRAG remains a replaceable lead generator behind these protocols.
Vendor descriptions, keywords, file paths, reference ordinals, source
hashes, track IDs, normalized entity names, and relation endpoint pairs are
never application integrity, idempotency, or citation identifiers.
Production insert/query wiring is intentionally absent from this module.
"""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

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
LIGHTRAG_TIKTOKEN_MODEL = "gpt-4o-mini"
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


class GraphRetriever(Protocol):
    """Project protocol for structured graph lead retrieval.

    Implementations live in later packets. This packet defines the contract
    only so application and LangGraph nodes never import vendor classes.
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


_DOCUMENT_VERSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_ENVELOPE_RE = re.compile(
    r"^<<smart-rag-graph-source:"
    + re.escape(GRAPH_SOURCE_ENVELOPE_VERSION)
    + r":([A-Za-z0-9._-]{1,128})>>\n",
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
        document_version_id: Canonical document version ID used as vendor
            ``ids`` and as the envelope token.
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
