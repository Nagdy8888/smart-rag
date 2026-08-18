"""CSV/XLSX hybrid index accepts table artifacts without prose chunks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from smart_rag_agents.ingestion.index_graph import (
    hybrid_index_has_content,
    table_only_embedding_result,
)
from smart_rag_core.ingestion.chunking.service import chunk_parse_result
from smart_rag_core.ingestion.parser.adapters import parse_file

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_csv_hybrid_index_uses_table_artifacts(tmp_path: Path) -> None:
    """Table-only CSV chunking is indexable and skips embedding inputs."""

    payload = (
        b"wikipedia_movie_id,movie_name,genres\n"
        b"870,Ghosts of Mars,Science Fiction; Horror\n"
    )
    digest = hashlib.sha256(payload).hexdigest()
    path = tmp_path / "movie.metadata.demo.csv"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "csv")
    chunking = chunk_parse_result(
        parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID
    )
    assert chunking.chunks == ()
    assert chunking.table_artifacts
    assert hybrid_index_has_content(chunking) is True
    embedding = table_only_embedding_result(
        version_id=VERSION_ID, chunking=chunking
    )
    assert embedding.embedded == ()
    assert embedding.provider_request_id == "table_only"
    assert len(embedding.chunk_set_hash) == 64
