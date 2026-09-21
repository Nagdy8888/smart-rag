"""Versioned Hybrid cache keys. Values are IDs and ranks only."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from smart_rag_core.query_profile.versions import (
    NORMALIZER_VERSION,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.retrieval.profiles import (
    BM25_INDEX_SCHEMA_VERSION,
    HYBRID_DEFAULT_PROFILE_ID,
    NORMALIZATION_VERSION,
)


def hybrid_cache_key(
    *,
    principal_scope_hash: str,
    query_normalized: str,
    retrieval_profile_id: str = HYBRID_DEFAULT_PROFILE_ID,
    visibility_generation: int,
    index_version: str = BM25_INDEX_SCHEMA_VERSION,
) -> str:
    """Build a cache key that cannot be reused across ACL or index versions.

    This is the Phase 6 cache interface. Packet 4 does not store a Valkey
    payload. Any later cache hit must call
    ``recheck_retrieval_candidates`` before IDs become evidence.

    Args:
        principal_scope_hash: Server-derived hash of caller plus ACL scope.
            Never a raw user id in logs.
        query_normalized: ``arabic_norm_v1`` query form.
        retrieval_profile_id: Allow-listed profile ID.
        visibility_generation: Document visibility generation.
        index_version: BM25 index schema version.

    Returns:
        SHA-256 hex digest of the canonical key material.

    Raises:
        ValueError: If the retrieval profile is not allow-listed.
    """

    from smart_rag_core.retrieval.frozen_profile import runtime_profile_ids

    if retrieval_profile_id not in runtime_profile_ids():
        raise ValueError("unknown_retrieval_profile")
    payload = {
        "principal_scope_hash": principal_scope_hash,
        "query_normalized": query_normalized,
        "retrieval_profile_id": retrieval_profile_id,
        "visibility_generation": visibility_generation,
        "index_version": index_version,
        "normalizer": NORMALIZATION_VERSION,
        "prompt": PROFILE_PROMPT_VERSION,
        "arabic_norm": NORMALIZER_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def cache_payload(
    chunk_ids: tuple[UUID, ...], ranks: tuple[int, ...]
) -> dict[str, object]:
    """Return an ID-only cache payload. Snippets are forbidden.

    Args:
        chunk_ids: Authorized canonical IDs.
        ranks: Fused ranks aligned with ``chunk_ids``.

    Returns:
        JSON-safe mapping of ids and ranks.

    Raises:
        ValueError: If lengths differ.
    """

    if len(chunk_ids) != len(ranks):
        raise ValueError("cache_payload_length_mismatch")
    return {
        "chunk_ids": [str(item) for item in chunk_ids],
        "ranks": list(ranks),
    }
