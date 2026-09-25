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
