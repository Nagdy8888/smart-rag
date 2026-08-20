"""Unit tests for canonical-passage LightRAG source identities."""

from __future__ import annotations

from uuid import UUID

from smart_rag_core.jobs.graph_source_text import CanonicalGraphSource
from smart_rag_core.retrieval.graph import (
    bind_graph_source_text,
    canonical_passage_source_id,
    opaque_passage_source_basename,
    parse_canonical_passage_source_id,
    strip_graph_source_envelope,
    version_vendor_source_ids,
)

VERSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CHUNK_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_passage_source_id_round_trips_and_binds_envelope() -> None:
    """Deterministic source IDs are envelope-safe and independently bound."""

    source_id = canonical_passage_source_id(version_id=VERSION_ID, chunk_id=CHUNK_ID)
    assert source_id == f"{VERSION_ID}:{CHUNK_ID}"
    parsed = parse_canonical_passage_source_id(source_id)
    assert parsed == (VERSION_ID, CHUNK_ID)
    bound = bind_graph_source_text(
        document_version_id=source_id,
        normalized_text="same passage",
    )
    other_chunk = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    other = bind_graph_source_text(
        document_version_id=canonical_passage_source_id(
            version_id=VERSION_ID,
            chunk_id=other_chunk,
        ),
        normalized_text="same passage",
    )
    assert bound != other
    assert strip_graph_source_envelope(bound) == "same passage"
    assert (
        opaque_passage_source_basename(
            version_id=VERSION_ID,
            chunk_id=CHUNK_ID,
        )
        == f"g-{VERSION_ID}-{CHUNK_ID}.txt"
    )


def test_deletion_ids_include_legacy_and_passage_sources() -> None:
    """Cleanup always deletes the whole-version ID plus every passage source."""

    ids = version_vendor_source_ids(VERSION_ID, (CHUNK_ID,))
    assert ids[0] == str(VERSION_ID)
    assert canonical_passage_source_id(version_id=VERSION_ID, chunk_id=CHUNK_ID) in ids


def test_canonical_graph_source_envelopes_with_passage_id() -> None:
    """Manifest sources bind the envelope to the passage source ID."""

    source = CanonicalGraphSource(
        version_id=VERSION_ID,
        chunk_id=CHUNK_ID,
        chunk_index=0,
        raw_text="passage body",
        content_hash="abc",
        source_id=canonical_passage_source_id(
            version_id=VERSION_ID,
            chunk_id=CHUNK_ID,
        ),
        source_token=opaque_passage_source_basename(
            version_id=VERSION_ID,
            chunk_id=CHUNK_ID,
        ),
    )
    text = source.enveloped_text()
    assert source.source_id in text
    assert strip_graph_source_envelope(text) == "passage body"
