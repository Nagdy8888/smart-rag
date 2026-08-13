"""Stable chunk identity derivation for replay-safe ingestion."""

from __future__ import annotations

import hashlib
import uuid

from smart_rag_core.ingestion.chunking.limits import (
    CHUNKING_POLICY_VERSION,
    DEDUP_POLICY_VERSION,
    TOKENIZER_VERSION,
)


def chunk_namespace(*, document_id: uuid.UUID, version_id: uuid.UUID) -> uuid.UUID:
    """Derive the UUID namespace for one document version.

    Args:
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.

    Returns:
        Deterministic namespace UUID for chunk IDs in the version.
    """

    seed = f"{document_id}|{version_id}|{CHUNKING_POLICY_VERSION}|{TOKENIZER_VERSION}|{DEDUP_POLICY_VERSION}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return uuid.UUID(hex=digest[:32])


def stable_chunk_id(
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    element_ids: tuple[str, ...],
    element_path: tuple[str, ...],
    normalized_content_hash: str,
    parser_version: str,
    cleaning_version: str,
    fragment_ordinal: int = 0,
) -> uuid.UUID:
    """Build a replay-stable chunk identifier.

    Args:
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.
        element_ids: Source element IDs included in the chunk.
        element_path: Hierarchical element path segments.
        normalized_content_hash: Hash of normalized chunk text.
        parser_version: Parser bundle version.
        cleaning_version: Cleaning policy version.
        fragment_ordinal: Zero-based fragment index for oversized atomics.

    Returns:
        Deterministic UUID5 chunk identifier.
    """

    canonical = "|".join(
        [
            ",".join(element_ids),
            ",".join(element_path),
            normalized_content_hash,
            parser_version,
            cleaning_version,
            CHUNKING_POLICY_VERSION,
            TOKENIZER_VERSION,
            str(fragment_ordinal),
        ]
    )
    name = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return uuid.uuid5(chunk_namespace(document_id=document_id, version_id=version_id), name)
