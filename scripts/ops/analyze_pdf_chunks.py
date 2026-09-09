"""Count-only chunk-band analyzer. Never prints source text."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path
from uuid import uuid4

from smart_rag_core.ingestion.chunking.limits import (
    CHUNKING_POLICY_VERSION,
    PARENT_MAX_TOKENS,
    PASSAGE_HARD_MAX_TOKENS,
    PASSAGE_TARGET_MAX_TOKENS,
    PASSAGE_TARGET_MIN_TOKENS,
    TOKENIZER_VERSION,
)
from smart_rag_core.ingestion.chunking.service import chunk_parse_result
from smart_rag_core.ingestion.chunking.types import ChunkKind
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.types import ElementKind


def _band(token_count: int) -> str:
    """Map a token count onto a reporting band.

    Args:
        token_count: Passage token count.

    Returns:
        Band label used in the count-only report.
    """

    if token_count < PASSAGE_TARGET_MIN_TOKENS:
        return "under_200"
    if token_count <= PASSAGE_TARGET_MAX_TOKENS:
        return "200_400"
    if token_count <= PASSAGE_HARD_MAX_TOKENS:
        return "401_600"
    return "over_600"


def analyze_path(path: Path) -> dict[str, object]:
    """Parse and chunk one file and return count-only metrics.

    Args:
        path: Local file. Bytes are hashed; text is not returned.

    Returns:
        Versions, kind counts, token-band counts, parent stats, and hashes.
        Source text is omitted.

    Side Effects:
        Reads the file from disk. Does not print extracted text.
    """

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    parse_result = parse_file(path, digest)
    document_id = uuid4()
    version_id = uuid4()
    chunking = chunk_parse_result(
        parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    passages = [chunk for chunk in chunking.chunks if chunk.kind is ChunkKind.PASSAGE]
    parents = [chunk for chunk in chunking.chunks if chunk.kind is ChunkKind.PARENT]
    ordinary = [
        chunk
        for chunk in passages
        if not chunk.provenance.is_atomic_exception
        and chunk.provenance.atomic_element_id is None
    ]
    bands = Counter(_band(chunk.token_count) for chunk in ordinary)
    kind_counts = Counter(element.kind.value for element in parse_result.elements)
    over_hard = sum(
        1 for chunk in passages if chunk.token_count > PASSAGE_HARD_MAX_TOKENS
    )
    parent_over = sum(1 for chunk in parents if chunk.token_count > PARENT_MAX_TOKENS)
    eligible = len(ordinary)
    in_target = bands.get("200_400", 0)
    ratio = (in_target / eligible) if eligible else 0.0
    chunk_id_hash = hashlib.sha256(
        "".join(str(chunk.chunk_id) for chunk in chunking.chunks).encode()
    ).hexdigest()
    return {
        "path_sha256": digest,
        "byte_length": len(payload),
        "parser_version": parse_result.parser_version,
        "chunking_version": CHUNKING_POLICY_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "element_kind_counts": dict(kind_counts),
        "passage_count": len(passages),
        "parent_count": len(parents),
        "ordinary_prose_count": eligible,
        "token_bands": dict(bands),
        "ordinary_in_200_400_ratio": round(ratio, 4),
        "passages_over_600": over_hard,
        "parents_over_1500": parent_over,
        "page_break_count": kind_counts.get(ElementKind.PAGE_BREAK.value, 0),
        "locator_count": sum(
            len(chunk.provenance.locators) for chunk in chunking.chunks
        ),
        "config_hash": chunking.config_hash,
        "chunk_id_hash": chunk_id_hash,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the count-only analyzer.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(
        description="Count-only PDF/document chunk bands. Never prints source text."
    )
    parser.add_argument("path", type=Path, help="Local file to analyze")
    args = parser.parse_args(argv)
    path = args.path
    if not path.is_file():
        print("analyze_pdf_chunks_missing_file")
        return 2
    report = analyze_path(path)
    for key, value in report.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
