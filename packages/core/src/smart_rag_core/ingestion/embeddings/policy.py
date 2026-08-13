"""Pinned embedding model and policy constants from ADR-embedding-model-dimension."""

from __future__ import annotations

import hashlib
import json

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 1024
CONTEXTUAL_EMBEDDING_VERSION = "contextual_v1"
TOKENIZER_VERSION = "cl100k_base_v1"


def embedding_policy_hash(*, chunking_config_hash: str) -> str:
    """Compute stable policy hash for ledger idempotency keys.

    Args:
        chunking_config_hash: Chunking replay hash from ``ChunkingResult``.

    Returns:
        Lowercase hex SHA-256 digest covering model, dimension, and policy version.
    """

    payload = {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "contextual_version": CONTEXTUAL_EMBEDDING_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "chunking_config_hash": chunking_config_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
