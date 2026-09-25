"""Chunking orchestration for typed parser outputs."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from smart_rag_core.ingestion.chunking.builder import (
    build_hierarchical_chunks,
    collect_chunking_metrics,
)
from smart_rag_core.ingestion.chunking.dedup import (
    apply_deduplication,
    dedup_policy_version,
)
from smart_rag_core.ingestion.chunking.limits import (
    CHUNKING_POLICY_VERSION,
    TOKENIZER_VERSION,
)
from smart_rag_core.ingestion.chunking.navigation import (
    NAVIGATION_POLICY_VERSION,
    apply_navigation_exclusion,
)
from smart_rag_core.ingestion.chunking.types import ChunkingResult
from smart_rag_core.ingestion.parser.types import ParseResult
from smart_rag_core.ingestion.tables.service import build_table_artifacts


def chunk_parse_result(
    parse_result: ParseResult,
    *,
    document_id: UUID,
    version_id: UUID,
) -> ChunkingResult:
    """Chunk one typed parse result into canonical passages, parents, and tables.

    Order: build passages and parents, mark exact duplicates, then keep
    table-of-contents and index chunks stored but not searchable
    (``apply_navigation_exclusion``).

    Args:
        parse_result: Closed parser output; raw bytes are not re-read.
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.

    Returns:
        Stable chunk IDs, provenance, optional table artifacts, and metrics.
    """

    chunks = build_hierarchical_chunks(
        parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    chunks, dedup_metrics = apply_deduplication(chunks)
    chunks = apply_navigation_exclusion(chunks)
    table_artifacts = build_table_artifacts(
        parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    metrics = collect_chunking_metrics(chunks, dedup_metrics=dedup_metrics)
    config_hash = stable_chunking_config_hash(parse_result.config_hash)
    return ChunkingResult(
        chunks=tuple(chunks),
        table_artifacts=table_artifacts,
        metrics=metrics,
        config_hash=config_hash,
    )


def stable_chunking_config_hash(parser_config_hash: str) -> str:
    """Compute deterministic chunking config hash for replay comparisons.

    Args:
        parser_config_hash: Parser/cleaning config hash from ``ParseResult``.

    Returns:
        Lowercase hex SHA-256 digest including chunking, tokenizer, dedup,
        and navigation policy versions.
    """

    payload = {
        "parser_config_hash": parser_config_hash,
        "chunking_version": CHUNKING_POLICY_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "dedup_policy_version": dedup_policy_version(),
        "navigation_policy_version": NAVIGATION_POLICY_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
