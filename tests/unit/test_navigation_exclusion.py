"""Navigation-page detection and search exclusion (answer-loss repair A7).

Every fixture is synthetic. Each mirrors the structure of a reflowed
contents page, a dot-leader contents page, a back-of-book index, a
glossary, or prose; none is copied from a real document.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.chunking import (
    chunk_parse_result,
    stable_chunking_config_hash,
)
from smart_rag_core.ingestion.chunking.navigation import (
    NAVIGATION_EXCLUSION_REASON,
    NAVIGATION_MAX_WORDS_PER_PAGE_REFERENCE,
    NavigationStats,
    apply_navigation_exclusion,
    is_navigation_chunk,
    is_page_reference,
    navigation_stats,
)
from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkingResult,
    ChunkKind,
    ChunkProvenance,
)
from smart_rag_core.ingestion.embeddings.contextual import (
    extract_deterministic_search_terms,
)
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddingBatchInput,
    EmbeddingGateError,
    EmbeddingService,
)
from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    ElementKind,
    MarkdownLocator,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
)

DOCUMENT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")

REFLOWED_CONTENTS = (
    "Preface ix 1. Getting Started 1 Installing the toolkit 3 "
    "First project 7 2. Core Concepts 15 Data models 17 Pipelines 24 "
    "3. Deployment 41 Monitoring 48 Scaling out 55 Index 301"
)
DOT_LEADER_CONTENTS = "\n".join(
    (
        "Introduction .......... 1",
        "Background .......... 5",
        "Methods .......... 12",
        "Results .......... 20",
    )
)
BACK_OF_BOOK_INDEX = (
    "A access control, 12, 45\u201347 adapters, 88 agents, 3, 19-22, 140 "
    "alerts, 201 B backups, 77, 79 batching, 150-152 benchmarks, 9"
)
GLOSSARY = (
    "Agent: A program that plans and acts toward a goal. It calls about 3 tools "
    "and reads their results before it decides the next step. "
    "Embedding: A vector of 1024 numbers that encodes the meaning of a text span. "
    "Similar texts map to nearby vectors. "
    "Retriever: The component that selects the top 10 passages for a question. "
    "It ranks candidates and returns the best results."
)
PROSE = (
    "The ingestion worker parses each upload in a sandbox without network access. "
    "It then splits the text into passages, removes exact duplicates, and stores "
    "every passage with its page locator. Retrieval reads only passages that remain "
    "search representatives, so a duplicate never competes with its original."
)
PROSE_WITH_ONE_NUMBER = (
    "In 2023 the team moved every ingestion job onto one queue so that "
    "retries, budgets, and leases share a single durable record."
)
PROSE_WITH_THREE_NUMBERS = (
    "The first run used 4 workers and finished the batch in about an hour. "
    "A second run used 8 workers and finished in roughly half that time, "
    "while a third run with 16 workers gained almost nothing because the "
    "database became the bottleneck."
)
SHORT_SENTENCES_WITH_NUMBERS = (
    "Run it. Then check 1. Read it. Then fix 2. Ship it. Then wait 3."
)


def _chunk(text: str, *, duplicate_of: uuid.UUID | None = None) -> CanonicalChunk:
    """Build one passage chunk; a ``duplicate_of`` id makes it a duplicate.

    Args:
        text: Raw chunk text.
        duplicate_of: Representative id when this chunk is a duplicate.

    Returns:
        Canonical passage chunk with fixture provenance.
    """

    return CanonicalChunk(
        chunk_id=uuid.uuid4(),
        chunk_index=0,
        kind=ChunkKind.PASSAGE,
        raw_text=text,
        token_count=10,
        duplicate_of_chunk_id=duplicate_of,
        is_search_representative=duplicate_of is None,
        provenance=ChunkProvenance(
            parser_version="parser_v1",
            cleaning_version="cleaning_v1",
            chunking_version="chunking_v2",
            tokenizer_version="cl100k_base_v1",
            dedup_policy_version="dedup_v1",
            normalized_content_hash="fixture",
        ),
    )


def _chunked() -> ChunkingResult:
    """Chunk a two-section Markdown document: contents, then a prose chapter.

    Returns:
        Output of the real chunking service.
    """

    texts = (
        (ElementKind.HEADING, "Contents"),
        (ElementKind.PARAGRAPH, REFLOWED_CONTENTS),
        (ElementKind.HEADING, "Chapter One"),
        (ElementKind.PARAGRAPH, PROSE),
    )
    elements = tuple(
        TypedElement(
            element_id=f"e{order}",
            kind=kind,
            text=text,
            reading_order=order,
            locator=MarkdownLocator(line_start=order + 1, line_end=order + 1),
        )
        for order, (kind, text) in enumerate(texts)
    )
    parse_result = ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format="markdown",
        content_hash="navigation-fixture",
        parser_version="parser_v1",
        cleaning_version="cleaning_v1",
        config_hash="cfg",
        elements=elements,
        coverage=CoverageAccounting(
            total_elements=4,
            text_elements=4,
            media_only_elements=0,
            removed_nodes=0,
            unsupported_regions=0,
            char_coverage_ratio=1.0,
        ),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.1),
    )
    return chunk_parse_result(
        parse_result, document_id=DOCUMENT_ID, version_id=VERSION_ID
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (REFLOWED_CONTENTS, True),
        (DOT_LEADER_CONTENTS, True),
        (BACK_OF_BOOK_INDEX, True),
        (GLOSSARY, False),
        (PROSE, False),
        (PROSE_WITH_ONE_NUMBER, False),
        (PROSE_WITH_THREE_NUMBERS, False),
        (SHORT_SENTENCES_WITH_NUMBERS, False),
    ],
    ids=[
        "reflowed_contents",
        "dot_leader_contents",
        "back_of_book_index",
        "glossary",
        "prose",
        "prose_with_one_number",
        "prose_with_three_numbers",
        "short_sentences_with_numbers",
    ],
)
def test_detector_separates_navigation_from_content(text: str, expected: bool) -> None:
    """Contents and index shapes match; glossaries and prose do not.

    Args:
        text: Synthetic fixture text.
        expected: Whether the fixture is a navigation page.
    """

    assert is_navigation_chunk(text) is expected


def test_index_stats_count_entries_not_lines() -> None:
    """Each run of page references closes one index entry."""

    assert navigation_stats(BACK_OF_BOOK_INDEX) == NavigationStats(
        word_tokens=10,
        page_reference_tokens=11,
        page_reference_runs=7,
        sentence_breaks=0,
    )


def test_sentence_guard_rejects_short_numbered_sentences() -> None:
    """Short numbered sentences pass the word rule but fail the sentence rule."""

    stats = navigation_stats(SHORT_SENTENCES_WITH_NUMBERS)
    assert stats == NavigationStats(
        word_tokens=12,
        page_reference_tokens=3,
        page_reference_runs=3,
        sentence_breaks=3,
    )
    assert (
        stats.word_tokens / stats.page_reference_runs
        <= NAVIGATION_MAX_WORDS_PER_PAGE_REFERENCE
    )
    assert not is_navigation_chunk(SHORT_SENTENCES_WITH_NUMBERS)


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("12", True),
        ("12,", True),
        ("45\u201347", True),
        ("19-22", True),
        ("301.", True),
        ("2023", True),
        ("ix", True),
        ("xiv.", True),
        ("i", False),
        ("LLM", False),
        ("XML", False),
        ("12345", False),
        ("v2", False),
        (",", False),
    ],
)
def test_page_reference_tokens(token: str, expected: bool) -> None:
    """Digits, ranges, and lowercase roman numerals are page references.

    Args:
        token: One whitespace token.
        expected: Whether it is a page reference.
    """

    assert is_page_reference(token) is expected


def test_exclusion_marks_navigation_and_keeps_prose() -> None:
    """A flagged chunk stays in place with a NULL duplicate target and a reason."""

    prose = _chunk(PROSE)
    index_page = _chunk(BACK_OF_BOOK_INDEX)
    chunks = [prose, index_page]
    result = apply_navigation_exclusion(chunks)
    assert result is chunks
    assert [chunk.chunk_id for chunk in result] == [prose.chunk_id, index_page.chunk_id]
    assert prose.is_search_representative
    assert prose.provenance.search_exclusion_reason is None
    assert not index_page.is_search_representative
    assert index_page.duplicate_of_chunk_id is None
    assert index_page.provenance.search_exclusion_reason == NAVIGATION_EXCLUSION_REASON


def test_exclusion_leaves_an_all_navigation_version_searchable() -> None:
    """A version made only of navigation text keeps every representative."""

    chunks = [_chunk(REFLOWED_CONTENTS), _chunk(BACK_OF_BOOK_INDEX)]
    apply_navigation_exclusion(chunks)
    assert all(chunk.is_search_representative for chunk in chunks)
    assert all(chunk.provenance.search_exclusion_reason is None for chunk in chunks)


def test_exclusion_does_not_touch_duplicates() -> None:
    """A duplicate keeps its duplicate target and gets no navigation reason."""

    prose = _chunk(PROSE)
    index_page = _chunk(BACK_OF_BOOK_INDEX)
    copy = _chunk(BACK_OF_BOOK_INDEX, duplicate_of=index_page.chunk_id)
    apply_navigation_exclusion([prose, index_page, copy])
    assert not index_page.is_search_representative
    assert copy.duplicate_of_chunk_id == index_page.chunk_id
    assert copy.provenance.search_exclusion_reason is None


def test_chunking_service_stores_navigation_chunks_as_non_representatives() -> None:
    """The contents passage and its parent are stored, flagged, and explained."""

    result = _chunked()
    excluded = [chunk for chunk in result.chunks if not chunk.is_search_representative]
    kept = [chunk for chunk in result.chunks if chunk.is_search_representative]
    assert sorted(chunk.kind.value for chunk in excluded) == ["parent", "passage"]
    assert all(chunk.section_path == ["Contents"] for chunk in excluded)
    assert all(chunk.duplicate_of_chunk_id is None for chunk in excluded)
    assert all(
        chunk.provenance.model_dump(mode="json")["search_exclusion_reason"]
        == NAVIGATION_EXCLUSION_REASON
        for chunk in excluded
    )
    assert sorted(chunk.kind.value for chunk in kept) == ["parent", "passage"]
    assert all(chunk.section_path == ["Chapter One"] for chunk in kept)
    assert all(chunk.provenance.search_exclusion_reason is None for chunk in kept)


def test_search_terms_skip_navigation_chunks() -> None:
    """Deterministic search terms are written only for representatives."""

    result = _chunked()
    terms = extract_deterministic_search_terms(
        document_title="Field Guide", filename=None, chunks=result.chunks
    )
    assert set(terms) == {
        chunk.chunk_id for chunk in result.chunks if chunk.is_search_representative
    }


def test_embedding_service_drops_navigation_chunks() -> None:
    """A batch of only navigation chunks stops before any database access."""

    result = _chunked()
    navigation_only = tuple(
        chunk for chunk in result.chunks if not chunk.is_search_representative
    )
    assert len(navigation_only) == 2
    connection = MagicMock()
    connection.cursor.side_effect = AssertionError("database should not be reached")
    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
    service = EmbeddingService(connection, gateway=gateway)
    batch = EmbeddingBatchInput(
        version_id=VERSION_ID,
        document_title="Field Guide",
        chunks=navigation_only,
        chunking_config_hash=result.config_hash,
        operation_key="embed:navigation",
        governance=ExternalProcessingDecisionInput(
            attestation_present=True,
            category=CategoryDisposition.ALLOWED,
            review_approved=True,
            scan_evidence_current=True,
            provider_settings_verified=True,
            policy_version_matches=True,
            content_class=ContentClass.SYNTHETIC,
        ),
    )
    with pytest.raises(EmbeddingGateError, match="no_search_representatives"):
        service.embed_version(batch)
    connection.cursor.assert_not_called()


def test_bm25_projection_reads_only_search_representatives() -> None:
    """The ParadeDB projection query filters on the representative flag."""

    supabase = MagicMock()
    cursor = supabase.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    service = Bm25ProjectionService(supabase, MagicMock())
    rows = service._load_projection_rows(VERSION_ID)  # pyright: ignore[reportPrivateUsage]
    assert rows == []
    query = str(cursor.execute.call_args.args[0])
    assert "dc.is_search_representative = true" in query


def test_config_hash_includes_navigation_policy_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing the navigation rule version changes the chunking config hash.

    Args:
        monkeypatch: Pytest fixture used to swap the version constant.
    """

    before = stable_chunking_config_hash("cfg")
    monkeypatch.setattr(
        "smart_rag_core.ingestion.chunking.service.NAVIGATION_POLICY_VERSION",
        "navigation_test",
    )
    assert stable_chunking_config_hash("cfg") != before
