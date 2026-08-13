"""Deterministic mock embedding vectors for MOCK_MODEL_MODE proofs."""

from __future__ import annotations

import hashlib
import math
import struct

from smart_rag_core.ingestion.embeddings.policy import EMBEDDING_DIMENSIONS


def mock_embedding_vector(text: str, *, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Return a finite unit-normalized vector derived from input text.

    Args:
        text: Contextual embedding input.
        dimensions: Output dimension count pinned by ADR.

    Returns:
        Deterministic float32-like values with L2 norm approximately 1.
    """

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        block = hashlib.sha256(digest + struct.pack(">I", counter)).digest()
        counter += 1
        for index in range(0, len(block) - 3, 4):
            raw = struct.unpack(">i", block[index : index + 4])[0]
            values.append((raw % 10000) / 5000.0 - 1.0)
            if len(values) >= dimensions:
                break
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
