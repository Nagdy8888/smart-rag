# A7 - Keep contents and index pages stored but out of search (`navigation_v1`)

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.
This packet is one commit on `fix/answer-loss-repair`.

**Depends on:** A6 (committed). **Probe symbol:**
`smart_rag_core.ingestion.chunking.navigation.is_navigation_chunk`.
**Live run:** none. The stored book changes only in A8.

## Goal

The book's table of contents (13 chunks) and back-of-book index (74
chunks) hold topic words and page numbers but no answer text. On the
2026-09-24 answer-only run they took 66 of 600 BM25 top-12 slots and 46
of 575 final-evidence slots. ADR Fix 4 items 2 and 3: add a generic
structural detector, and mark matching chunks
`is_search_representative = false`, `duplicate_of_chunk_id = NULL`, with
provenance `search_exclusion_reason = "navigation_page"`. Existing
representative filters then keep them out of embedding, BM25, search
terms, and all three channels. No migration (provenance is JSONB).

## Why these choices (do not "improve" them)

- **Entries, not lines.** The ADR says "most of its lines end in page
  references". PDF reflow joins the lines of one block with spaces, so a
  stored contents chunk has a median of 3 lines of about 57 tokens. The
  rule counts runs of page references (one run closes one entry).
- **Structure only.** No title, hash, page number, heading name, or
  format is read. Thresholds were set from synthetic fixtures and from
  structural counts of the stored book (numbers only, below).
- **Every representative is judged on its own text, parents included.**
  Parents are search representatives and are embedded (274 of 274 on the
  stored book). A parent's text is its children's text. Own-text judging
  flags 20 parents; "all children flagged" would flag 17 and misses
  nothing own-text catches. A child is never excluded because its parent
  is.
- **Whole-version guard.** If every representative would be flagged,
  nothing is flagged. Otherwise a contents-only upload would become
  unsearchable and `EmbeddingService` would raise
  `no_search_representatives` (service.py lines ~127-131).
- **After dedup.** Duplicates are already non-representatives and keep
  their `duplicate_of_chunk_id`.
- **`CHUNKING_POLICY_VERSION` stays `chunking_v2`.** It is in the stable
  chunk-ID seed; A6 already gives the book new IDs. `navigation_v1` goes
  into the chunking config hash instead (feeds `embedding_policy_hash`;
  no test pins either hash and no retrieval SQL filters on it).
- **No table-row guard.** Checked and rejected: running heads put `" | "`
  in 304 prose passages and in most index chunks, and the guard cut
  detection from 68 to 40.

### Calibration on the stored book (version `e119bf87`, counts only)

| Group | Kind | Chunks | Flagged | Words per run (3+ runs) | Sentence breaks per 100 tokens |
| --- | --- | ---: | ---: | --- | --- |
| Contents pp. 7-13 | passage | 12 | 12 | 1.67-3.80 | 0 |
| Contents pp. 7-13 | parent | 1 | 1 | 3.09 | 0 |
| Index pp. 341-353 | passage | 47 | 36 | 2.00-4.33 | 0 |
| Index pp. 341-353 | parent | 27 | 19 | 2.00-3.82 | 0 |
| Glossary pp. 337-340 | passage | 6 | 0 | none reach 3 runs | 5.63-8.05 |
| Glossary pp. 337-340 | parent | 1 | 0 | 274.5 | 6.90 |
| Prose | passage | 677 | 0 | 5.83-105.33 | 0-8.11 |
| Prose | parent | 245 | 0 | 27.33-316 | 0-6.43 |

68 of 1,016 flagged (the root-cause doc's 87 is the page-range count).
The 19 unflagged index chunks have at most 13 tokens and at most 2 runs.
Against the baseline answers, the flagged chunks cover 66 of 66
contents/index BM25 top-12 slots, 46 of 46 final-evidence slots, and 9
of 13 dense top-12 slots.

## Read first (confirm each quote exists; line numbers may drift a few lines)

`packages/core/src/smart_rag_core/ingestion/chunking/service.py`
lines 17-20, 32, 48, 70-79:

```python
from smart_rag_core.ingestion.chunking.limits import (
    CHUNKING_POLICY_VERSION,
    TOKENIZER_VERSION,
)
```

```python
    """Chunk one typed parse result into canonical passages, parents, and tables.
```

```python
    chunks, dedup_metrics = apply_deduplication(chunks)
```

```python
        Lowercase hex SHA-256 digest including chunking/tokenizer/dedup versions.
    """

    payload = {
        "parser_config_hash": parser_config_hash,
        "chunking_version": CHUNKING_POLICY_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "dedup_policy_version": dedup_policy_version(),
    }
```

`packages/core/src/smart_rag_core/ingestion/chunking/types.py` lines
21-22, 39, 42-43:

```python
class ChunkProvenance(BaseModel):
    """Structured provenance for citations and reconstruction."""
```

```python
    normalized_content_hash: str
```

```python
class CanonicalChunk(BaseModel):
    """One hierarchical passage or parent chunk before persistence."""
```

`CanonicalChunk` has `duplicate_of_chunk_id: UUID | None = None` and
`is_search_representative: bool = True` (lines 54-55).

Also read: `chunking/dedup.py` `_mark_duplicate` (lines 95-109, the
in-place mutation pattern this packet copies);
`embeddings/service.py` lines 120-131; `embeddings/contextual.py`
lines 83-86; `ingestion/bm25_projection.py` lines 199-233;
`tests/unit/test_chunking_service.py` (fixture shapes).

## Reader audit (every reader of the two fields; no code change needed)

| Reader | Behavior with a navigation chunk |
| --- | --- |
| `ingestion/canonical/repository.py` 107-145 (upsert), 273-297 (insert order) | writes the flag, NULL duplicate, and JSON provenance; insert order accepts NULL |
| `ingestion/embeddings/service.py` 127-131 | filters to representatives: not embedded |
| `ingestion/embeddings/contextual.py` 85 | skips: no deterministic search terms |
| `ingestion/bm25_projection.py` 229; `retrieval/bm25_verifier.py` 175 | filter: not projected; verifier compares representative counts |
| SQL `dense_candidates_v2` 41, 164; `hybrid_retrieval_v1` 57, 110, 228, 303, 454; `retrieve_term_candidates_extra_terms_v1` 80 | filter: never a dense, BM25, or term candidate |
| SQL `sync_document_title_search_terms_v1` 30, `update_document_title_v1` 37 | filter: no title search term |
| SQL `list_authorized_eval_passages_v1` 62; scripts `seal_/draft_/review_pdf_eval_dataset.py`, `pdf_eval_runtime.py` 678, `ops/repair_pdf_page_numbers.py` 184 | filter: not an eval passage |
| SQL `pdf_paragraph_citations_v1` 168-211 | needs a representative child or self: a citation into a navigation chunk fails closed |
| `retrieval/source_scope.py` 297, 351 | counts representatives for the long-document profile (threshold 5): the book stays long |
| `retrieval/context_loader.py` 52-263, 420-460; SQL `hybrid_rerank_context_v1`, `hybrid_chunk_context_locators_v1` | pass the flag through; parent fetch ignores it by design |
| `jobs/graph_mapping_hybrid.py` 134; `evaluation/parser_bakeoff/mapping.py` 149 | sets True for graph rows / filters bakeoff passages |
| `jobs/graph_source_text.py` 170-178; `jobs/graph_mapping_persist.py` 571-574 | **no flag filter**: graph-eligible documents still send navigation chunks to LightRAG (the book is graph-ineligible; documented limit) |

No SQL reads `duplicate_of_chunk_id` except its DDL. No `apps/frontend`
reader exists.

## Steps

### 1. New module `packages/core/src/smart_rag_core/ingestion/chunking/navigation.py` (exact code)

```python
"""Structural detector for table-of-contents and back-of-book-index chunks.

Navigation pages pair short topic labels with page numbers. They share
topic words with many questions but hold no answer text, so they crowd
BM25, dense, and final-evidence slots. The rule reads only the chunk's own
text shape: how many page-reference runs it has, how many words sit
between those runs, and how many sentence breaks it has. It never reads a
document title, content hash, page number, heading name, or file format,
so the same rule applies to every upload.

PDF reflow joins the lines of one PyMuPDF block with spaces, so a stored
contents chunk holds a few long lines rather than one line per entry. The
rule therefore counts entries (runs of page references), not lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from smart_rag_core.ingestion.chunking.types import CanonicalChunk

NAVIGATION_POLICY_VERSION = "navigation_v1"
"""Version of the navigation rule, included in the chunking config hash."""

NAVIGATION_EXCLUSION_REASON = "navigation_page"
"""Provenance ``search_exclusion_reason`` written on excluded chunks."""

NAVIGATION_MIN_PAGE_REFERENCE_RUNS = 3
"""Fewest page-reference runs a navigation chunk must contain.

A run is one or more consecutive page-reference tokens, and each run closes
one entry. Prose that cites one or two numbers stays below this.
"""

NAVIGATION_MAX_WORDS_PER_PAGE_REFERENCE = 5.0
"""Largest mean number of word tokens per page-reference run.

Contents and index entries are short labels. On the calibration book,
navigation chunks measured 1.67 to 4.33 words per run, prose at least 5.83,
and the glossary parent 274.5.
"""

NAVIGATION_MAX_SENTENCE_BREAKS_PER_100_TOKENS = 1.0
"""Largest number of sentence breaks per 100 counted tokens.

A sentence break is a lowercase letter, ``.``, ``!``, or ``?``, an optional
closing quote or bracket, whitespace, then an uppercase letter. Topic lists
have none; the calibration glossary measured 5.63 to 8.05.
"""

_DOT_LEADER = re.compile(r"(?:\.\s?){3,}|\u2026+")
_ARABIC_PAGE = re.compile(r"\d{1,4}(?:[-\u2010\u2011\u2012\u2013\u2014]\d{1,4})?")
_ROMAN_PAGE = re.compile(
    r"(?=[ivxlcdm]{2})m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
)
_SENTENCE_BREAK = re.compile(r"[a-z][.!?][\"')\u201d\u2019]?\s+[A-Z]")
_REFERENCE_TRAILING_PUNCTUATION = ",;:."


@dataclass(frozen=True, slots=True)
class NavigationStats:
    """Structural counts the navigation rule reads from one chunk text.

    Attributes:
        word_tokens: Tokens that contain a letter and are not page
            references.
        page_reference_tokens: Tokens that are page references.
        page_reference_runs: Maximal runs of consecutive page references;
            each run closes one entry.
        sentence_breaks: Matches of the sentence-break pattern.
    """

    word_tokens: int
    page_reference_tokens: int
    page_reference_runs: int
    sentence_breaks: int


def is_page_reference(token: str) -> bool:
    """Return whether one whitespace token is a page reference.

    A page reference is 1 to 4 digits, optionally a range joined by ``-`` or
    U+2010 to U+2014, or a lowercase roman numeral of at least two letters.
    Trailing ``,``, ``;``, ``:``, and ``.`` are ignored. Uppercase letters
    never match, so acronyms such as ``LLM`` or ``XML`` stay words.

    Args:
        token: One whitespace-delimited token.

    Returns:
        True when the token is a page reference.

    Examples:
        >>> is_page_reference("45-47,")
        True
        >>> is_page_reference("xiv")
        True
        >>> is_page_reference("LLM")
        False
    """

    core = token.rstrip(_REFERENCE_TRAILING_PUNCTUATION)
    if not core:
        return False
    return (
        _ARABIC_PAGE.fullmatch(core) is not None
        or _ROMAN_PAGE.fullmatch(core) is not None
    )


def navigation_stats(text: str) -> NavigationStats:
    """Count page-reference runs, word tokens, and sentence breaks.

    Dot leaders (three or more dots, or U+2026) become a space first, so
    ``Methods ...... 12`` yields one word and one page reference. Tokens
    with no letter or digit are skipped and do not end a run.

    Args:
        text: Chunk ``raw_text``.

    Returns:
        Structural counts only; no text is kept.
    """

    word_tokens = 0
    page_reference_tokens = 0
    page_reference_runs = 0
    in_run = False
    for token in _DOT_LEADER.sub(" ", text).split():
        if not any(character.isalnum() for character in token):
            continue
        if is_page_reference(token):
            page_reference_tokens += 1
            if not in_run:
                page_reference_runs += 1
            in_run = True
            continue
        in_run = False
        if any(character.isalpha() for character in token):
            word_tokens += 1
    return NavigationStats(
        word_tokens=word_tokens,
        page_reference_tokens=page_reference_tokens,
        page_reference_runs=page_reference_runs,
        sentence_breaks=len(_SENTENCE_BREAK.findall(text)),
    )


def is_navigation_chunk(text: str) -> bool:
    """Return whether a chunk text is a contents or index page.

    All three must hold: at least ``NAVIGATION_MIN_PAGE_REFERENCE_RUNS``
    page-reference runs, at most ``NAVIGATION_MAX_WORDS_PER_PAGE_REFERENCE``
    words per run, and at most
    ``NAVIGATION_MAX_SENTENCE_BREAKS_PER_100_TOKENS`` sentence breaks per 100
    counted tokens (words plus page references).

    Args:
        text: Chunk ``raw_text``.

    Returns:
        True for navigation text. Prose, glossaries, and fragments with
        fewer than three runs return False.
    """

    stats = navigation_stats(text)
    if stats.page_reference_runs < NAVIGATION_MIN_PAGE_REFERENCE_RUNS:
        return False
    words_per_run = stats.word_tokens / stats.page_reference_runs
    if words_per_run > NAVIGATION_MAX_WORDS_PER_PAGE_REFERENCE:
        return False
    counted = stats.word_tokens + stats.page_reference_tokens
    breaks_per_100 = 100.0 * stats.sentence_breaks / counted
    return breaks_per_100 <= NAVIGATION_MAX_SENTENCE_BREAKS_PER_100_TOKENS


def apply_navigation_exclusion(chunks: list[CanonicalChunk]) -> list[CanonicalChunk]:
    """Keep navigation chunks stored but remove them from search.

    Runs after deduplication. Every chunk that is still a search
    representative, passage or parent, is judged on its own ``raw_text``. A
    parent is not excluded because a child is, and a child is not excluded
    because its parent is. Duplicates are left unchanged.

    When every representative in the version would be excluded, nothing
    changes: a document that is only a contents list stays searchable, and
    embedding keeps at least one input.

    Args:
        chunks: Passage and parent chunks for one version, in builder order.

    Returns:
        The same list object in the same order.

    Side Effects:
        Each flagged chunk gets ``is_search_representative = False``,
        ``duplicate_of_chunk_id = None``, and provenance
        ``search_exclusion_reason = NAVIGATION_EXCLUSION_REASON``. Chunk IDs
        do not change.
    """

    representatives = [chunk for chunk in chunks if chunk.is_search_representative]
    flagged = [
        chunk for chunk in representatives if is_navigation_chunk(chunk.raw_text)
    ]
    if not flagged or len(flagged) == len(representatives):
        return chunks
    for chunk in flagged:
        chunk.is_search_representative = False
        chunk.duplicate_of_chunk_id = None
        chunk.provenance = chunk.provenance.model_copy(
            update={"search_exclusion_reason": NAVIGATION_EXCLUSION_REASON}
        )
    return chunks
```

Keep every `\u` escape (Ruff `RUF001`). This module passes `ruff check`
and `ruff format` as written.

### 2. `types.py` (exact edits)

Replace the `ChunkProvenance` docstring line with:

```python
    """Structured provenance for citations and reconstruction.

    ``search_exclusion_reason`` explains a chunk that is stored but is not a
    search representative for a reason other than deduplication. It is
    ``None`` for representatives and for duplicates, which carry
    ``CanonicalChunk.duplicate_of_chunk_id`` instead. ``"navigation_page"``
    marks a contents or index chunk excluded by
    ``smart_rag_core.ingestion.chunking.navigation``. The value is stored in
    the ``provenance`` JSONB column, so no migration is needed; rows written
    before this field have no key and read as ``None``.
    """
```

After `    normalized_content_hash: str` add:

```python
    search_exclusion_reason: str | None = None
```

Replace the `CanonicalChunk` docstring line with:

```python
    """One hierarchical passage or parent chunk before persistence.

    ``is_search_representative`` is False for two reasons. An exact
    duplicate sets ``duplicate_of_chunk_id`` to the kept chunk. A navigation
    page leaves ``duplicate_of_chunk_id`` as ``None`` and sets
    ``provenance.search_exclusion_reason`` to ``"navigation_page"``. A
    non-representative stays stored with its locators but is not embedded,
    projected to BM25, given search terms, or returned by retrieval.
    """
```

### 3. `service.py` (exact edits)

After the `chunking.limits` import block add:

```python
from smart_rag_core.ingestion.chunking.navigation import (
    NAVIGATION_POLICY_VERSION,
    apply_navigation_exclusion,
)
```

In the `chunk_parse_result` docstring, after the summary line and its
blank line, insert (then keep the blank line before `Args:`):

```text
    Order: build passages and parents, mark exact duplicates, then keep
    table-of-contents and index chunks stored but not searchable
    (``apply_navigation_exclusion``).
```

After `    chunks, dedup_metrics = apply_deduplication(chunks)` add:

```python
    chunks = apply_navigation_exclusion(chunks)
```

In `stable_chunking_config_hash`, replace the `Returns:` line
`Lowercase hex SHA-256 digest including chunking/tokenizer/dedup versions.`
with the two lines:

```text
        Lowercase hex SHA-256 digest including chunking, tokenizer, dedup,
        and navigation policy versions.
```

and after `        "dedup_policy_version": dedup_policy_version(),` add:

```python
        "navigation_policy_version": NAVIGATION_POLICY_VERSION,
```

`collect_chunking_metrics` stays as is (no new metric field).

## New tests: `tests/unit/test_navigation_exclusion.py` (new file, exact code)

```python
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
```

It passes `ruff check` and `ruff format` as written and collects **32**
tests (8 detector cases, 14 token cases, and 10 single tests). Every
expected `NavigationStats` value and the four-chunk service result (two
passages, two parents) were checked against the real chunker while
writing this packet.

## Docs (exact edits)

`$runDate = Get-Date -Format yyyy-MM-dd`; use it for `<RUN_DATE>`.

1. `docs/ingestion/CHUNKING_CONTRACT.md` line 16. Replace
   `; they are not embedding targets.` at the end of the Hierarchy
   sentence with:

   ```text
   . A parent is stored as a search representative like a passage, so it is embedded, projected to BM25, and retrievable unless deduplication or the navigation rule below excludes it.
   ```

   (That statement was wrong: all 274 parents of the stored book are
   embedded.) Then insert this section right before
   `## Heading inventory (Phase 4 consumer)`:

   ````markdown
   ## Navigation pages

   `apply_navigation_exclusion` (`ingestion/chunking/navigation.py`, policy
   `navigation_v1`) runs right after deduplication. It judges every chunk
   that is still a search representative, passage or parent, on its own
   `raw_text`. A flagged chunk stays stored with its locators and gets
   `is_search_representative = false`, `duplicate_of_chunk_id = NULL`, and
   provenance `search_exclusion_reason = "navigation_page"`. The existing
   representative filters keep it out of embedding, the BM25 projection,
   deterministic and title search terms, and the dense, BM25, and term
   channels. No migration: provenance is JSONB.

   ```mermaid
   flowchart LR
     buildNode["build_hierarchical_chunks"] --> dedupNode["apply_deduplication"]
     dedupNode --> navNode["apply_navigation_exclusion"]
     navNode -->|"representative"| searchNode["Embedding, BM25 projection, search terms"]
     navNode -->|"navigation_page"| storedNode["Stored only, not searchable"]
     dedupNode -->|"duplicate"| storedNode
   ```

   **Meaning of the flag.** `is_search_representative = false` has two
   causes: `duplicate_of_chunk_id` set (exact duplicate of that chunk), or
   `duplicate_of_chunk_id` NULL with reason `navigation_page`. No reader
   dereferences `duplicate_of_chunk_id` except the repository insert
   order, which accepts NULL.

   **Rule (structure only; never a title, hash, page number, heading, or
   format).** Dot leaders become spaces and text splits on whitespace. A
   page reference is 1 to 4 digits, optionally a range joined by `-` or
   U+2010 to U+2014, or a lowercase roman numeral of two or more letters,
   with trailing `,;:.` ignored. A run of consecutive page references
   closes one entry. A chunk is navigation when it has at least 3 runs, at
   most 5.0 words per run, and at most 1.0 sentence break per 100 tokens.
   Entries are counted instead of lines because PDF reflow joins the lines
   of one block (median 3 lines of about 57 tokens per contents chunk).

   **Parents, children, guard.** Each chunk is judged on its own text, so
   an index parent is flagged even when one child is only a letter
   heading; a child is never excluded because its parent is. Parent
   context expansion does not filter on the flag, so a representative
   child of an excluded parent can still expand to index text. If every
   representative of a version would be flagged, nothing is flagged.

   | Calibration group (private PDF above) | Chunks | Flagged | Words per run (3+ runs) | Sentence breaks per 100 tokens |
   | --- | ---: | ---: | --- | --- |
   | Contents passages and parent | 13 | 13 | 1.67–3.80 | 0 |
   | Index passages and parents | 74 | 55 | 2.00–4.33 | 0 |
   | Glossary passages and parent | 7 | 0 | 274.5 (parent only) | 5.63–8.05 |
   | Prose passages and parents | 922 | 0 | 5.83–316 | 0–8.11 |

   **Limits.** Index fragments with fewer than 3 runs stay searchable (19
   of 74, each at most 13 tokens). Short-label number tables and code
   listings with per-line numbers can match. A lowercase word that is a
   valid roman numeral (`mix`, `cm`) counts as a page reference. LightRAG
   source loading (`jobs/graph_source_text.py`,
   `jobs/graph_mapping_persist.py`) reads undeleted chunks without this
   flag, so graph-eligible documents still send navigation chunks to graph
   extraction. `navigation_v1` is in the chunking config hash, not in the
   chunk ID; re-chunking a version under a new rule keeps IDs and the
   upsert rewrites the flag and provenance.
   ````

   In the **Verification** block, insert
   `tests/unit/test_navigation_exclusion.py ` right after
   `uv run pytest ` (the rest of the line stays). Set the front matter
   `last-reviewed:` to `<RUN_DATE>`.

2. `docs/ingestion/INGESTION_LIMITS.md`: in the Chunking table, after
   the `| Dedup policy version | ...` row, add:

   ```text
   | Navigation policy version | text | `navigation_v1` | — | Answer-loss repair (Fix 4) | worker | stored, not searchable (`navigation_page`) | Threshold change or a prose false positive |
   ```

   Set the front matter `last-reviewed:` to `<RUN_DATE>`.

3. `docs/adr/ADR-retrieved-answer-loss-repair.md`, Fix 4 item 2
   (lines ~182-186). Replace the five lines that start
   `2. Add a generic detector` and end `Glossaries and prose must not match.`
   with:

   ```markdown
   2. Add a generic detector for table-of-contents and back-of-book-index
      chunks. A chunk qualifies when its entries end in page references
      (numbers, ranges, roman numerals, dot leaders): at least 3 runs of
      page references, at most 5 words per run, and almost no sentence
      breaks. Entries are counted instead of lines because PDF reflow joins
      the lines of one block. Thresholds come from fixtures and structural
      counts, never from the book's title, hash, page numbers, or headings.
      Glossaries and prose must not match. Each representative passage or
      parent is judged on its own text.
   ```

4. `docs/README.md`: replace only the date cell with `<RUN_DATE>` in the
   rows for `ingestion/CHUNKING_CONTRACT.md`,
   `ingestion/INGESTION_LIMITS.md`, and
   `adr/ADR-retrieved-answer-loss-repair.md`; set front matter
   `last-reviewed:` to `<RUN_DATE>` if older.

## Commands (run in this order; all must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/ingestion/chunking/navigation.py packages/core/src/smart_rag_core/ingestion/chunking/types.py packages/core/src/smart_rag_core/ingestion/chunking/service.py tests/unit/test_navigation_exclusion.py
uv run python -m pytest tests/unit/test_navigation_exclusion.py -q
uv run python -m pytest tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py tests/unit/test_embedding_service.py tests/unit/test_pdf_line_joins.py tests/unit/test_pdf_heading_extraction.py -q
uv run python -c "from smart_rag_core.ingestion.chunking.navigation import is_navigation_chunk; print('A7', 'present')"
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier docs
```

Expected: the first pytest prints `32 passed`. If the lint tier reports
only `I001` (import order) on the new test file, run
`uv run python -m ruff check --select I --fix tests/unit/test_navigation_exclusion.py`
once and rerun lint. No contract test changes.

## Live proof

None in this packet. A8 re-ingests the book and measures the stored
flags.

## Done when

- [ ] `navigation.py` exists exactly as above; `NAVIGATION_POLICY_VERSION`
      is `navigation_v1` and every threshold constant has a docstring.
- [ ] `ChunkProvenance.search_exclusion_reason: str | None = None` and
      both updated docstrings exist in `types.py`.
- [ ] `chunk_parse_result` calls `apply_navigation_exclusion` right after
      `apply_deduplication`; the config hash payload includes
      `navigation_policy_version`.
- [ ] `test_navigation_exclusion.py`: `32 passed`; the five existing test
      files in the second pytest command pass unchanged.
- [ ] `lint`, `types`, `format`, `unit`, and `docs` tiers exit 0.
- [ ] `CHUNKING_CONTRACT.md` (line 16 corrected, Navigation section with
      Mermaid, Verification line), `INGESTION_LIMITS.md`, the ADR Fix 4
      item 2, and `docs/README.md` updated as above.
- [ ] Commit pushed; `gh pr checks --watch --fail-fast` exits 0.

## Commit

```text
feat(ingestion): exclude contents and index pages from search as navigation_page (A7)
```

Files to `git add`, one by one:

```text
packages/core/src/smart_rag_core/ingestion/chunking/navigation.py
packages/core/src/smart_rag_core/ingestion/chunking/types.py
packages/core/src/smart_rag_core/ingestion/chunking/service.py
tests/unit/test_navigation_exclusion.py
docs/ingestion/CHUNKING_CONTRACT.md
docs/ingestion/INGESTION_LIMITS.md
docs/adr/ADR-retrieved-answer-loss-repair.md
docs/README.md
```

(Eight paths. Any other changed tracked file: stop and explain.)

## Do not

- Do not key the detector on a document title, content hash, page
  number, section or heading name, file format, or chunk kind.
- Do not change the thresholds, the regexes, or the whole-version guard.
- Do not bump `CHUNKING_POLICY_VERSION`, `DEDUP_POLICY_VERSION`, or
  `PDF_PARSER_VERSION`, and do not add a chunk-ID input.
- Do not add a SQL migration, a new column, or a new metric field.
- Do not change any reader in the audit table (including the LightRAG
  loaders); report the LightRAG limit instead.
- Do not add a table-row (`" | "`) guard.
- Do not rebuild images, upload, re-ingest, or run a live eval.
- Do not put book text, question text, or gold phrases in any tracked
  file; the calibration numbers above are the only book-derived content.
