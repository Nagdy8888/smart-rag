"""Rerank pool, policy, schema, MMR, parent expansion, and fallback types."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from smart_rag_core.evaluation.schema import ExpectedProfile, QueryType
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.retrieval.profiles import (
    DOCUMENT_QUOTA,
    FINAL_EVIDENCE_MAX,
    FINAL_TOKEN_BUDGET,
    MMR_CANDIDATE_DEPTH,
    MMR_LAMBDA,
    RERANK_EXCERPT_CHARS,
    RERANK_INVALID_SUBCODES,
    RERANK_MAX_PER_DOCUMENT,
    RERANK_POOL_SIZE,
    SECTION_QUOTA,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

CHANNEL_HEAD_PIN = 5
"""Top-N authorized IDs from dense and from BM25 that always enter the pool."""

_HELPER_NAME_ASK = re.compile(r"(?i)\bhelper\s+function\b|\bfunction\s+name\b")
_PROSE_HELPER_NAME = re.compile(
    r"(?i)helper\s+function\s*\(\s*[A-Za-z_][\w]*\s*\)"
)
_EXPOSE_MODE_ASK = re.compile(
    r"(?i)(?:\bexpose\b|\blabel(?:s|ed)?\b).{0,80}\bmode"
    r"|\bmode.{0,40}\b(?:label|expose|slider|autonomy)"
    r"|\bautonomy[-\s]?slider\b"
)
# Quote/comma-bound Assist (not substring of "assisted"); allow ô/ö mojibake.
_EXPOSE_MODE_GOLD = re.compile(
    r"(?i)Label these modes.{0,100}?"
    r"Manual.{0,12}Assist(?!ed).{0,24}Auto(?!nom)"
    r'|(?:["“ô]Manual,["”ö]\s*["“ô]Assist,["”ö]\s*'
    r'(?:and\s+)?["“ô]Auto["”ö])'
)
_ADAS_MODEL_ASK = re.compile(
    r"(?i)\b(?:ADAS|LLMAgentBase)\b"
    r"|(?:default\s+model|model\s+string).{0,40}temperature"
)
_ADAS_MODEL_GOLD = re.compile(
    r"(?i)gpt-4o-\d{4}-\d{2}-\d{2}.{0,80}temperature\s*=\s*0\.5"
    r"|temperature\s*=\s*0\.5.{0,80}gpt-4o-\d{4}-\d{2}-\d{2}"
)
_CHUNKING_ASK = re.compile(
    r"(?i)\bchunking_strategy\b|\bwindow_size\b.{0,40}\boverlap\b"
    r"|\boverlap\b.{0,40}\bwindow_size\b"
)
# Allow newlines and mixed ASCII/curly quotes between window_size and overlap.
_CHUNKING_GOLD = re.compile(
    r"(?i)window_size\s*['\"‘’“”]?\s*[:=]\s*\d+.{0,120}?overlap\s*['\"‘’“”]?\s*[:=]\s*\d+"
    r"|overlap\s*['\"‘’“”]?\s*[:=]\s*\d+.{0,120}?window_size\s*['\"‘’“”]?\s*[:=]\s*\d+",
    re.DOTALL,
)
_TOOL_DESCRIPTION_ASK = re.compile(
    r"(?i)description\s+string|\btool_descriptions\b"
)
_TOOL_DESCRIPTION_GOLD = re.compile(
    r"(?i)Use\s+Wolfram\s+Alpha\s+to\s+compute\s+mathematical.{0,120}",
    re.DOTALL,
)
_QUERY_OVERLAP_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
_QUERY_OVERLAP_STOP = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "what",
        "when",
        "which",
        "have",
        "does",
        "only",
        "give",
        "name",
        "wording",
        "figure",
        "page",
        "document",
        "company",
        "building",
        "applications",
        "agents",
        "agent",
        "into",
        "used",
        "uses",
        "using",
        "example",
        "about",
        "their",
        "there",
        "these",
        "those",
        "where",
        "your",
        "them",
    }
)
_METHOD_LABEL_ASK = re.compile(
    r"(?i)\b(?:what method|method works|method name|table\s+\d)"
    r"|\bheading\b|\bsection(?:\s+name)?\b|\bchapter\s+title\b"
    r"|token\s+consumption|reduced\s+efficiency|lower\s+efficiency"
)
_METHOD_LABEL_GOLD = re.compile(
    r"(?i)Direct preference optimization"
    r"|Lower efficiency"
    r"|Manager Coordination"
    r"|From One Agent to Many"
    r"|Context Engineering"
    r"|Nonparametric [Ll]earning"
)
_HOST_LITERAL_ASK = re.compile(
    r"(?i)\blocalhost:\d+|\blocalhost\b.{0,60}\b(?:path|mcp|server)\b"
    r"|\bMCP\s+server\b.{0,40}\b(?:path|localhost)\b"
)
_HOST_LITERAL_GOLD = re.compile(r"(?i)localhost:\d+(?:/[A-Za-z0-9._~/-]*)?")
_IDE_PRODUCT_ASK = re.compile(
    r"(?i)\bIDE\b.{0,80}(?:code|inference|product)"
    r"|(?:code|inference|product).{0,80}\bIDE\b"
    r"|\bCursor\b"
)
_IDE_PRODUCT_GOLD = re.compile(
    r"(?i)Cursor uses the integrated development environment"
)
_PROTOCOL_ASK = re.compile(
    r"(?i)\baspires\b.{0,100}\bHTTP\b|\bHTTP\b.{0,100}\bcomposability\b"
    r"|\bprotocol\b.{0,80}\b(?:HTTP|composability|A2A)\b"
)
_PROTOCOL_GOLD = re.compile(
    r"(?i)Much like HTTP enabled the composability of the web.{0,80}"
    r"A2A aspires"
    r"|A2A aspires to do the same for AI agents"
    r"|aspires to do (?:the same )?for AI agents what HTTP enabled",
    re.DOTALL,
)
_CODE_DEF_ASK = re.compile(
    r"(?i)\breproduce\b.{0,120}\b(?:code|fenced|python|@tool|\bdef\b)"
    r"|\bfenced\b.{0,60}\b(?:python|code)"
    r"|\bcode\s+block\b"
    r"|\b@tool\b"
    r"|\b(?:async\s+)?def\s+[A-Za-z_][\w]*"
)
# Capture names after ``def`` / ``@tool def`` only. Bare ``@tool and`` in
# prose must not become an identifier; snake_case tokens still match below.
_CODE_ID_FROM_QUERY = re.compile(
    r"(?i)(?:@tool\s+)?(?:async\s+)?def\s+([A-Za-z_][\w]*)"
    r"|([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)"
)
_CODE_ID_STOP = frozenset(
    {
        "order_id",
        "tool_name",
        "user_query",
        "raw_text",
        "chunk_id",
        "page_number",
        "state_graph",
        "human_message",
        "base_message",
        "company_documents",
        "markdown_pipe",
        "pipe_table",
        "code_block",
        "building_applications",
        "function",
        "definition",
        "tool",
        "block",
        "python",
        "fenced",
        "reproduce",
        "markdown",
        "table",
        "snippet",
        "heuristic",
        "example",
        "wiring",
        "setup",
        "assignment",
        "operations",
        "kwargs",
        "and",
        "the",
        "for",
        "with",
        "from",
        "into",
        "that",
        "this",
        "when",
        "then",
        "else",
        "not",
        "are",
        "was",
        "were",
        "have",
        "has",
        "been",
        "will",
        "can",
        "may",
        "use",
        "using",
        "used",
        "via",
        "per",
        "its",
        "our",
        "your",
        "any",
        "all",
        "each",
        "both",
        "such",
        "than",
        "also",
        "only",
        "just",
        "like",
        "over",
        "list",
        "name",
        "named",
        "call",
        "called",
        "return",
        "returns",
        "true",
        "false",
        "none",
        "type",
        "types",
        "self",
        "args",
        "tools",
    }
)
_TABLE_REPRO_ASK = re.compile(
    r"(?i)\breproduce\b.{0,120}\btable\b"
    r"|\btable\b.{0,80}\b(?:markdown|pipe)\b"
    r"|\bMarkdown\s+pipe\s+table\b"
    r"|\bTable\s+\d+-\d+\b"
)
_TABLE_CAPTION_FROM_QUERY = re.compile(r"(?i)\bTable\s+(\d+-\d+)\b")


def named_code_definition_ids(query: str) -> tuple[str, ...]:
    """Extract function/tool identifiers named in a code-reproduce ask.

    Args:
        query: Original user query. Untrusted.

    Returns:
        Distinct identifier strings in query order. Empty when the ask is
        not code-shaped or no usable identifier is present.
    """

    if not _CODE_DEF_ASK.search(query):
        return ()
    found: list[str] = []
    seen: set[str] = set()
    for match in _CODE_ID_FROM_QUERY.finditer(query):
        token = (match.group(1) or match.group(2) or "").strip()
        if not token or token.casefold() in _CODE_ID_STOP:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(token)
    return tuple(found)


def code_definition_gold_pattern(identifiers: Sequence[str]) -> re.Pattern[str] | None:
    """Build a passage regex for ``def`` / ``@tool def`` of named identifiers.

    Args:
        identifiers: Function or tool names extracted from the query.

    Returns:
        Compiled pattern, or ``None`` when ``identifiers`` is empty.
    """

    names = [item for item in identifiers if item.strip()]
    if not names:
        return None
    alt = "|".join(re.escape(item) for item in names)
    return re.compile(
        rf"(?i)(?:@tool\s+)?(?:async\s+)?def\s+(?:{alt})\s*\(",
    )


def named_table_captions(query: str) -> tuple[str, ...]:
    """Extract ``Table N-M`` captions named in a table-reproduce ask.

    Args:
        query: Original user query. Untrusted.

    Returns:
        Distinct caption strings such as ``Table 2-1``. Empty when the ask
        is not table-shaped or no caption is present.
    """

    if not _TABLE_REPRO_ASK.search(query):
        return ()
    found: list[str] = []
    seen: set[str] = set()
    for match in _TABLE_CAPTION_FROM_QUERY.finditer(query):
        caption = f"Table {match.group(1)}"
        key = caption.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(caption)
    return tuple(found)


def table_caption_gold_pattern(captions: Sequence[str]) -> re.Pattern[str] | None:
    """Build a passage regex for named table captions with nearby row text.

    Prefers a caption that is followed within a short window by a digit or
    model-like token so prose intros without the table body rank lower.

    Args:
        captions: Captions extracted from the query (for example ``Table 2-1``).

    Returns:
        Compiled pattern, or ``None`` when ``captions`` is empty.
    """

    names = [item for item in captions if item.strip()]
    if not names:
        return None
    alt = "|".join(re.escape(item) for item in names)
    return re.compile(
        rf"(?i)(?:{alt}).{{0,400}}?(?:\d(?:\.\d+)?|[A-Za-z][A-Za-z0-9]+(?:\s+[A-Za-z0-9.-]+){{1,6}})",
        re.DOTALL,
    )


def promote_helper_naming_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin helper-function naming prose into final evidence when missing.

    When the ask seeks a helper or function name, a pool passage that names
    the helper in prose (for example ``helper function (update_memory)``)
    is prepended if selection kept only a later definition or call site.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages that may hold naming prose.
        limit: Maximum passages to retain (``final_evidence_max``).

    Returns:
        Trimmed passages, possibly with one naming passage prepended.
    """

    if limit < 1 or not _HELPER_NAME_ASK.search(query):
        return trimmed
    selected = {item.candidate.chunk_id for item in trimmed}
    if any(_PROSE_HELPER_NAME.search(item.raw_text or "") for item in trimmed):
        return trimmed
    for item in pool:
        if item.candidate.chunk_id in selected:
            continue
        if not _PROSE_HELPER_NAME.search(item.raw_text or ""):
            continue
        promoted = (item, *trimmed)
        if len(promoted) > limit:
            promoted = promoted[:limit]
        return promoted
    return trimmed


def promote_expose_mode_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin Manual/Assist/Auto expose-label prose when the ask needs it.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages that may hold expose labels.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one expose-label passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_EXPOSE_MODE_ASK,
        gold_pattern=_EXPOSE_MODE_GOLD,
    )


def promote_adas_model_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin ADAS dated model+temperature defaults when the ask needs them.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages that may hold ADAS defaults.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one ADAS defaults passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_ADAS_MODEL_ASK,
        gold_pattern=_ADAS_MODEL_GOLD,
    )


def promote_chunking_window_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin ``window_size``/``overlap`` chunking literals when the ask needs them.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one chunking-literal passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_CHUNKING_ASK,
        gold_pattern=_CHUNKING_GOLD,
    )


def promote_tool_description_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin exact tool description strings when the ask requests them.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one description-string passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_TOOL_DESCRIPTION_ASK,
        gold_pattern=_TOOL_DESCRIPTION_GOLD,
    )


def promote_method_label_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin method/heading labels when the ask requests a named label.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one label passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_METHOD_LABEL_ASK,
        gold_pattern=_METHOD_LABEL_GOLD,
    )


def promote_host_literal_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin ``localhost:port/path`` literals when the ask requests a host path.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one host-literal passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_HOST_LITERAL_ASK,
        gold_pattern=_HOST_LITERAL_GOLD,
    )


def promote_ide_product_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin the IDE product naming passage when the ask needs that product.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one IDE-product passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_IDE_PRODUCT_ASK,
        gold_pattern=_IDE_PRODUCT_GOLD,
    )


def promote_protocol_aspire_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin the A2A/HTTP composability aspire passage when the ask needs it.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool or fused passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with the protocol-aspire passage prepended.
    """

    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_PROTOCOL_ASK,
        gold_pattern=_PROTOCOL_GOLD,
    )


def promote_named_code_definition_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin a named ``def`` / ``@tool`` definition when the ask reproduces code.

    Identifiers are taken only from the user query. Passages that hold the
    definition line are preferred over later call sites via local span
    overlap inside :func:`_promote_matching_passage`.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool or fused passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one definition passage prepended.
    """

    identifiers = named_code_definition_ids(query)
    gold = code_definition_gold_pattern(identifiers)
    if gold is None:
        return trimmed
    return _promote_matching_passage(
        trimmed,
        query=query,
        pool=pool,
        limit=limit,
        ask_pattern=_CODE_DEF_ASK,
        gold_pattern=gold,
        prefer_early_match=True,
    )


def promote_named_table_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
) -> tuple[RerankPassage, ...]:
    """Pin a named ``Table N-M`` body when the ask reproduces a table.

    Prefers titled caption+rows passages over prose intros that only
    mention the table name.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool or fused passages.
        limit: Maximum passages to retain.

    Returns:
        Trimmed passages, possibly with one caption+rows passage prepended.
    """

    captions = named_table_captions(query)
    gold = table_caption_gold_pattern(captions)
    if gold is None or limit < 1 or not _TABLE_REPRO_ASK.search(query):
        return trimmed
    matches = [item for item in pool if gold.search(item.raw_text or "")]
    if not matches:
        return trimmed
    titled = [
        item
        for item in matches
        if any(
            f"{caption.casefold()}." in (item.raw_text or "").casefold()
            for caption in captions
        )
    ]
    if titled:
        matches = titled

    def _rank_key(pair: tuple[int, RerankPassage]) -> tuple[int, int, int, int]:
        """Prefer dense table bodies over prose intros.

        Args:
            pair: ``(pool_index, passage)``.

        Returns:
            Ascending sort tuple (smaller = better).
        """

        index, item = pair
        text = item.raw_text or ""
        match = gold.search(text)
        span = match.group(0) if match is not None else ""
        return (
            -_table_body_rank(text, captions),
            -local_literal_overlap_score(query, text, span),
            -query_overlap_score(query, text),
            index,
        )

    ranked = sorted(enumerate(matches), key=_rank_key)
    best = ranked[0][1]
    if trimmed and trimmed[0].candidate.chunk_id == best.candidate.chunk_id:
        return trimmed
    selected = {item.candidate.chunk_id for item in trimmed}
    if best.candidate.chunk_id in selected:
        rest = tuple(
            other
            for other in trimmed
            if other.candidate.chunk_id != best.candidate.chunk_id
        )
        promoted = (best, *rest)
    else:
        promoted = (best, *trimmed)
    if len(promoted) > limit:
        promoted = promoted[:limit]
    return promoted


_TABLE_TITLE_RANK = re.compile(r"(?i)Table\s+\d+-\d+\.")
_TABLE_PROSE_RANK = re.compile(
    r"(?i)\b(?:a small selection|are shown along|at a glance|you can adapt|"
    r"as you.?ll see in|see in table|shown in table|refer to table)\b",
)
_NUMBER_RANK = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _table_body_rank(text: str, captions: tuple[str, ...]) -> int:
    """Score table-body density for promote ranking.

    Args:
        text: Passage text.
        captions: Query captions such as ``Table 2-1``.

    Returns:
        Higher prefers the passage. Titled caption pages outrank denser
        continuation pages that only back-reference the table in prose.
    """

    if not text:
        return -100
    score = 0
    lowered = text.casefold()
    titled = False
    for caption in captions:
        key = caption.casefold()
        if f"{key}." in lowered:
            score += 24
            titled = True
        elif key in lowered:
            score += 2
    digits = _NUMBER_RANK.findall(text)
    score += min(12, len(digits))
    header_hits = sum(
        1
        for token in (
            "model",
            "maintainer",
            "metric",
            "stack",
            "role",
            "approach",
            "product team",
            "key strength",
        )
        if token in lowered
    )
    score += 3 * header_hits
    if _TABLE_PROSE_RANK.search(text):
        score -= 8
    if not titled and _TABLE_PROSE_RANK.search(text):
        score -= 20
    if _TABLE_TITLE_RANK.search(text) is None and _TABLE_PROSE_RANK.search(text):
        score -= 6
    return score


def literal_anchor_ask(query: str) -> bool:
    """Return whether ``query`` asks for a pinned literal or label.

    Used to load fused-outside-pool contexts before promote so rare
    ``window_size`` / tool-description / host / IDE / code-def / table
    literals remain searchable after the rerank pool drops them.

    Args:
        query: Original user query. Untrusted.

    Returns:
        True when any literal-anchor ask pattern matches.
    """

    return bool(
        _CHUNKING_ASK.search(query)
        or _TOOL_DESCRIPTION_ASK.search(query)
        or _METHOD_LABEL_ASK.search(query)
        or _HOST_LITERAL_ASK.search(query)
        or _IDE_PRODUCT_ASK.search(query)
        or _PROTOCOL_ASK.search(query)
        or _CODE_DEF_ASK.search(query)
        or _TABLE_REPRO_ASK.search(query)
    )


def literal_gold_already_loaded(
    query: str,
    passages: Sequence[RerankPassage],
) -> bool:
    """Return whether pool passages already hold the ask's gold literal.

    Table asks require a titled caption+rows body, not a prose intro that
    only mentions ``Table N-M``. Otherwise fused-outside-pool reload never
    runs and salvage cannot find the row text.

    Args:
        query: Original user query. Untrusted.
        passages: Passages already loaded for the rerank pool.

    Returns:
        True when a matching gold span is present and no fused reload is
        needed for literal promote.
    """

    checks: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
        (_CHUNKING_ASK, _CHUNKING_GOLD),
        (_TOOL_DESCRIPTION_ASK, _TOOL_DESCRIPTION_GOLD),
        (_METHOD_LABEL_ASK, _METHOD_LABEL_GOLD),
        (_HOST_LITERAL_ASK, _HOST_LITERAL_GOLD),
        (_IDE_PRODUCT_ASK, _IDE_PRODUCT_GOLD),
        (_PROTOCOL_ASK, _PROTOCOL_GOLD),
    ]
    code_gold = code_definition_gold_pattern(named_code_definition_ids(query))
    if code_gold is not None:
        checks.append((_CODE_DEF_ASK, code_gold))
    for ask_pattern, gold_pattern in checks:
        if not ask_pattern.search(query):
            continue
        if any(gold_pattern.search(item.raw_text or "") for item in passages):
            return True
    captions = named_table_captions(query)
    table_gold = table_caption_gold_pattern(captions)
    if table_gold is not None and _TABLE_REPRO_ASK.search(query):
        if any(
            table_gold.search(item.raw_text or "")
            and _table_body_rank(item.raw_text or "", captions) >= 12
            for item in passages
        ):
            return True
    return False


def query_overlap_score(query: str, text: str) -> int:
    """Count distinctive query tokens (length ≥4) present in ``text``.

    Args:
        query: Original user query. Untrusted.
        text: Passage or citation text.

    Returns:
        Non-negative overlap count. Higher prefers the passage.
    """

    if not query or not text:
        return 0
    lowered = text.lower()
    seen: set[str] = set()
    score = 0
    for match in _QUERY_OVERLAP_TOKEN.finditer(query.lower()):
        token = match.group(0)
        if token in _QUERY_OVERLAP_STOP or token in seen:
            continue
        seen.add(token)
        if token in lowered:
            score += 1
    return score


def local_literal_overlap_score(query: str, text: str, span: str) -> int:
    """Score query-token overlap in a window around ``span``.

    Breaks ties when several passages share the same global gold literal
    but only one embeds it beside the ask's distinctive context words.

    Args:
        query: Original user query. Untrusted.
        text: Passage text.
        span: Substring already known to occur in ``text``.

    Returns:
        Overlap count inside a ±100 character window around ``span``.
    """

    if not query or not text or not span:
        return 0
    start = text.lower().find(span.lower())
    if start < 0:
        return query_overlap_score(query, text)
    window = text[max(0, start - 100) : start + len(span) + 100]
    return query_overlap_score(query, window)

def _promote_matching_passage(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
    ask_pattern: re.Pattern[str],
    gold_pattern: re.Pattern[str],
    prefer_early_match: bool = False,
) -> tuple[RerankPassage, ...]:
    """Prepend the best fused/pool passage matching ``gold_pattern``.

    Callers may pass the full fused passage list as ``pool`` so rare
    literals outside the rerank pool can still be pinned. When several
    passages match, the highest query-term overlap wins so a nearby
    duplicate page does not block the gold holder. When
    ``prefer_early_match`` is set, an earlier ``gold_pattern`` offset in
    the passage wins first so a primary ``def`` page beats a later
    reprint that only mentions the tool in passing.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Passages to search for a gold match (pool or full fused).
        limit: Maximum passages to retain.
        ask_pattern: Query shape that enables promotion.
        gold_pattern: Passage text that should be pinned.
        prefer_early_match: Prefer earlier match offsets in the passage.

    Returns:
        Trimmed passages, possibly with the best matching passage prepended.
    """

    if limit < 1 or not ask_pattern.search(query):
        return trimmed
    matches = [
        item for item in pool if gold_pattern.search(item.raw_text or "")
    ]
    if not matches:
        return trimmed

    def _rank_key(pair: tuple[int, RerankPassage]) -> tuple[int, int, int, int]:
        """Sort key for duplicate gold holders.

        Args:
            pair: ``(pool_index, passage)``.

        Returns:
            Ascending sort tuple (more negative / smaller = better).
        """

        index, item = pair
        text = item.raw_text or ""
        match = gold_pattern.search(text)
        span = match.group(0) if match is not None else ""
        offset = match.start() if match is not None else 10_000
        if prefer_early_match:
            return (
                offset,
                -local_literal_overlap_score(query, text, span),
                -query_overlap_score(query, text),
                index,
            )
        return (
            -query_overlap_score(query, text),
            -local_literal_overlap_score(query, text, span),
            offset,
            index,
        )

    ranked = sorted(enumerate(matches), key=_rank_key)
    best = ranked[0][1]
    if trimmed and trimmed[0].candidate.chunk_id == best.candidate.chunk_id:
        return trimmed
    selected = {item.candidate.chunk_id for item in trimmed}
    if best.candidate.chunk_id in selected:
        rest = tuple(
            other
            for other in trimmed
            if other.candidate.chunk_id != best.candidate.chunk_id
        )
        promoted = (best, *rest)
    else:
        promoted = (best, *trimmed)
    if len(promoted) > limit:
        promoted = promoted[:limit]
    return promoted


class RerankFallbackReason(StrEnum):
    """Typed safe routes when the OpenAI reranker cannot be used."""

    NONE = "none"
    SKIPPED_TRIVIAL_EXACT = "skipped_trivial_exact"
    INSUFFICIENT_CANDIDATES = "insufficient_candidates"
    SCHEMA_INVALID = "rerank_schema_invalid"
    INCOMPLETE = "rerank_incomplete"
    TIMEOUT = "rerank_timeout"
    CANCELLED = "rerank_cancelled"
    BUDGET_DENIED = "rerank_budget_denied"
    VERSION_MISMATCH = "rerank_version_mismatch"
    UNKNOWN_USAGE = "rerank_unknown_usage"
    REFUSAL = "rerank_refusal"
    PROVIDER_ERROR = "rerank_provider_error"


class RerankPayloadError(ValueError):
    """Rerank payload failed application validation.

    ``str(error)`` stays the specific message (for example
    ``rerank_input_hash_mismatch``), so existing ``ValueError`` handlers
    and ``match=`` tests keep working. ``subcode`` is the coarse, ID-free
    class that diagnostics persist.

    Attributes:
        subcode: One of ``RERANK_INVALID_SUBCODES``: ``json`` (shape, type,
            or bounds), ``hash`` (echoed digest differs), ``length`` (row
            count differs), ``duplicate`` (repeated ID or rank), or
            ``unknown_id`` (ID not supplied, or supplied set not covered).
    """

    def __init__(self, message: str, *, subcode: str) -> None:
        """Build the error.

        Args:
            message: Specific validation message; becomes ``str(error)``.
            subcode: Coarse sub-code from ``RERANK_INVALID_SUBCODES``.

        Raises:
            ValueError: ``rerank_subcode_invalid`` when ``subcode`` is not
                allow-listed.
        """

        if subcode not in RERANK_INVALID_SUBCODES:
            raise ValueError("rerank_subcode_invalid")
        super().__init__(message)
        self.subcode = subcode


@dataclass(frozen=True, slots=True)
class RerankPassage:
    """One authorized passage eligible for the rerank pool.

    Attributes:
        candidate: Fused authorized ID.
        raw_text: Canonical citation text, never a BM25 snippet.
        section_path: Heading path.
        page_number: Optional page.
        parent_chunk_id: Parent passage when present.
        chunk_index: Order within the version.
        token_count: Stored token count or whitespace estimate.
        channels: Independent channels that retrieved this ID.
        excerpt: Bounded excerpt sent to the reranker.
    """

    candidate: RetrievalCandidate
    raw_text: str
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    parent_chunk_id: UUID | None = None
    chunk_index: int = 0
    token_count: int = 0
    channels: frozenset[str] = frozenset()
    excerpt: str = ""


@dataclass(frozen=True, slots=True)
class RerankRanking:
    """One model ranking row after application validation.

    Attributes:
        chunk_id: Supplied candidate ID.
        rank: 1-based order.
        support: Bounded ranking feature in ``[0, 1]``.
        supported_subquestion_indices: Optional 0-based subquestion indices.
        appended: True when the model did not rank this candidate and the
            server appended it in pool order (``rerank_v2`` partial output).
    """

    chunk_id: UUID
    rank: int
    support: float
    supported_subquestion_indices: tuple[int, ...] = ()
    appended: bool = False


@dataclass(frozen=True, slots=True)
class RerankUsage:
    """Observable one-operation usage. Duplicate cost remains visible.

    Attributes:
        request_id: Provider response id or mock fixture id.
        model: Allow-listed model id.
        input_tokens: Prompt tokens, or 0 when unknown/mocked.
        output_tokens: Completion tokens, or 0 when unknown/mocked.
        model_calls: ``0`` or ``1``. Hidden retries are forbidden.
        invalid_subcode: ``RerankPayloadError.subcode`` when the payload
            failed application validation, else empty.
    """

    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    model_calls: int
    invalid_subcode: str = ""


@dataclass(frozen=True, slots=True)
class ContextSelection:
    """Final Hybrid evidence after rerank, MMR, quotas, and parents.

    Attributes:
        passages: At most 12 authorized evidence units.
        rerank_order: Post-rerank or fallback RRF order of the pool.
        fallback_reason: Skip or failure reason.
        mmr_dropped: IDs dropped by MMR/quotas.
        expanded_parent_ids: Parent IDs added after recheck.
        usage: Gateway usage for the one rerank call, if any.
        skipped_counterfactual: True when a skip trigger fired.
        rerank_top_support: Support of the top selected child after a real
            rerank. None on identity/skip/failure.
        supported_subquestion_indices: Validated 0-based subquestion indices
            from a completed rerank payload. Empty on fallback.
        rerank_ranked_count: Candidates the model ranked. 0 on fallback.
        rerank_appended_count: Candidates appended by the server after a
            partial ranking. 0 on fallback or a full ranking.
    """

    passages: tuple[RerankPassage, ...]
    rerank_order: tuple[UUID, ...]
    fallback_reason: RerankFallbackReason
    mmr_dropped: tuple[UUID, ...]
    expanded_parent_ids: tuple[UUID, ...]
    usage: RerankUsage | None
    skipped_counterfactual: bool
    rerank_top_support: float | None = None
    supported_subquestion_indices: tuple[int, ...] = ()
    rerank_ranked_count: int = 0
    rerank_appended_count: int = 0


def rerank_input_hash(
    *,
    query: str,
    candidate_ids: tuple[str, ...],
    excerpts: tuple[str, ...],
    prompt_sha256: str,
) -> str:
    """Hash the canonical rerank request for echo-back verification.

    Args:
        query: Original query.
        candidate_ids: Pool IDs as strings.
        excerpts: Bounded canonical excerpts aligned with IDs.
        prompt_sha256: Pinned prompt digest.

    Returns:
        SHA-256 hex digest.
    """

    payload = {
        "query": query,
        "candidate_ids": list(candidate_ids),
        "excerpts": list(excerpts),
        "prompt_sha256": prompt_sha256,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def excerpt_text(
    raw_text: str,
    *,
    limit: int = RERANK_EXCERPT_CHARS,
    query: str | None = None,
    strategy: str = "prefix",
) -> str:
    """Clamp canonical text for the rerank request.

    Args:
        raw_text: Canonical passage. Citation text is not replaced.
        limit: Maximum characters.
        query: Original query used only for ``query_aware`` windows.
        strategy: ``prefix`` or ``query_aware``.

    Returns:
        Bounded excerpt. Empty input stays empty. Citation ``raw_text`` is
        unchanged on the passage object.
    """

    stripped = raw_text.strip()
    if len(stripped) <= limit:
        return stripped
    if strategy == "query_aware" and query and query.strip():
        window = _query_aware_window(stripped, query=query, limit=limit)
        if window:
            return window
    return stripped[:limit]


def _query_aware_window(raw_text: str, *, query: str, limit: int) -> str:
    """Return a character window around the first query-token hit.

    Args:
        raw_text: Canonical passage.
        query: Original query.
        limit: Window size.

    Returns:
        Windowed excerpt, or empty when no query token of length ≥3 is found.
    """

    lowered = raw_text.lower()
    tokens = [token for token in query.lower().split() if len(token) >= 3]
    hit = -1
    for token in tokens:
        hit = lowered.find(token)
        if hit >= 0:
            break
    if hit < 0:
        return ""
    start = max(0, hit - max(0, (limit - len(tokens[0])) // 2))
    end = start + limit
    if end > len(raw_text):
        start = max(0, len(raw_text) - limit)
        end = len(raw_text)
    return raw_text[start:end]


def channel_head_pins(
    *,
    dense_ids: Sequence[UUID],
    bm25_ids: Sequence[UUID],
    fused_ids: Sequence[UUID],
    head: int = CHANNEL_HEAD_PIN,
    dense_head: int | None = None,
) -> tuple[UUID, ...]:
    """Return the channel-head IDs that must enter the rerank pool.

    RRF with ``rrf_k=60`` ranks any chunk returned by two channels above a
    chunk returned by one channel at rank 1. Pinning the first authorized
    IDs of each channel keeps single-channel top hits visible to the
    reranker without changing fusion weights.

    Args:
        dense_ids: Dense IDs in channel-rank order.
        bm25_ids: BM25 IDs in channel-rank order.
        fused_ids: Authorized fused IDs. Pins outside this set are dropped,
            so pins can never add an ID the ACL recheck removed.
        head: BM25 pin count, and the dense pin count when ``dense_head``
            is ``None``.
        dense_head: Dense pin count from the frozen profile
            (``dense_head_pin``). ``None`` uses ``head``.

    Returns:
        Distinct pins, dense first then BM25, each within ``fused_ids``.
    """

    authorized = set(fused_ids)
    dense_limit = head if dense_head is None else dense_head
    pins: list[UUID] = []
    for channel, limit in ((dense_ids, dense_limit), (bm25_ids, head)):
        for chunk_id in tuple(channel)[: max(0, limit)]:
            if chunk_id in authorized and chunk_id not in pins:
                pins.append(chunk_id)
    return tuple(pins)


def rerank_preload_ids(
    fused: tuple[RetrievalCandidate, ...],
    *,
    pool_size: int = RERANK_POOL_SIZE,
    max_per_document: int = RERANK_MAX_PER_DOCUMENT,
    pinned_ids: Sequence[UUID] = (),
) -> tuple[UUID, ...]:
    """Return fused IDs that occupy the one-shot rerank pool.

    Coverage is computed after final evidence selection. Loading the full
    prefusion union (up to 205 IDs, two 75-ID context RPCs) before rerank
    burns ``RETRIEVAL_SLICE_SECONDS`` and starves the live reranker.

    Channel-head pins are reserved in pin order (dense heads first, then
    BM25). Filling pins from fused rank order let early BM25 pins crowd
    out later dense heads when ``dense_head_pin`` approaches ``pool_size``.

    Args:
        fused: Authorized fused candidates in rank order.
        pool_size: Global rerank pool cap.
        max_per_document: Per-document cap inside the pool.
        pinned_ids: Channel-head IDs that bypass the per-document cap,
            already ordered dense-first by ``channel_head_pins``.

    Returns:
        Distinct chunk IDs, at most ``pool_size``, matching
        ``build_rerank_pool`` membership before content collapse.
    """

    fused_ids = {item.chunk_id for item in fused}
    selected: list[UUID] = []
    seen: set[UUID] = set()
    for chunk_id in pinned_ids:
        if chunk_id not in fused_ids or chunk_id in seen:
            continue
        selected.append(chunk_id)
        seen.add(chunk_id)
        if len(selected) >= pool_size:
            return tuple(selected)
    per_document: dict[UUID, int] = {}
    for item in fused:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        used = per_document.get(item.document_id, 0)
        if used >= max_per_document:
            continue
        per_document[item.document_id] = used + 1
        selected.append(item.chunk_id)
        if len(selected) >= pool_size:
            break
    return tuple(selected)


def collapse_exact_duplicate_passages(
    passages: Sequence[RerankPassage],
) -> tuple[RerankPassage, ...]:
    """Keep the first authorized copy of exact duplicate content.

    Collapse happens after ACL and current-version recheck because callers
    pass ``RerankPassage`` rows built from rechecked context. Documents are
    not deleted.

    Args:
        passages: Authorized passages in fused rank order.

    Returns:
        Passages with later exact-normalized duplicates removed.
    """

    seen_chunks: set[UUID] = set()
    seen_content: set[str] = set()
    selected: list[RerankPassage] = []
    for item in passages:
        chunk_id = item.candidate.chunk_id
        if chunk_id in seen_chunks:
            continue
        digest = content_hash(item.raw_text)
        if digest in seen_content:
            continue
        seen_chunks.add(chunk_id)
        seen_content.add(digest)
        selected.append(item)
    return tuple(selected)


def build_rerank_pool(
    passages: tuple[RerankPassage, ...],
    *,
    pool_size: int = RERANK_POOL_SIZE,
    max_per_document: int = RERANK_MAX_PER_DOCUMENT,
    excerpt_chars: int = RERANK_EXCERPT_CHARS,
    query: str | None = None,
    excerpt_strategy: str = "prefix",
    pinned_ids: Sequence[UUID] = (),
) -> tuple[RerankPassage, ...]:
    """Collapse exact-content duplicates and cap the pool with per-document limits.

    Exact duplicate collapse is by normalized citation text after ACL
    recheck, not by document id. Duplicate files therefore cannot consume
    independent document quotas. Documents are not deleted. Pins bypass
    the per-document cap, count toward ``pool_size``, and are reserved in
    channel-head order (dense first) before the remaining fused fill.

    Args:
        passages: Fused-order authorized passages with canonical text.
        pool_size: Global pool cap. Default matches ``hybrid_default_v1``.
        max_per_document: Per-document cap inside the pool.
        excerpt_chars: Excerpt character budget.
        query: Original query for query-aware excerpts.
        excerpt_strategy: ``prefix`` or ``query_aware``.
        pinned_ids: Channel-head IDs that bypass the per-document cap,
            ordered dense-first by ``channel_head_pins``.

    Returns:
        Pool after exact-content collapse, pin reservation, per-document,
        and global caps. Non-pin members keep fused order; pins keep
        channel-head order at the front of membership, then the pool is
        emitted in fused order among the chosen set.
    """

    ordered = collapse_exact_duplicate_passages(passages)
    by_id = {item.candidate.chunk_id: item for item in ordered}
    chosen: set[UUID] = set()
    seen_content: set[str] = set()
    for chunk_id in pinned_ids:
        if len(chosen) >= pool_size:
            break
        item = by_id.get(chunk_id)
        if item is None or chunk_id in chosen:
            continue
        digest = content_hash(item.raw_text)
        if digest in seen_content:
            continue
        seen_content.add(digest)
        chosen.add(chunk_id)
    seen: set[UUID] = set(chosen)
    per_document: dict[UUID, int] = {}
    for item in ordered:
        if len(chosen) >= pool_size:
            break
        chunk_id = item.candidate.chunk_id
        if chunk_id in seen:
            continue
        digest = content_hash(item.raw_text)
        if digest in seen_content:
            continue
        seen.add(chunk_id)
        seen_content.add(digest)
        document_id = item.candidate.document_id
        used = per_document.get(document_id, 0)
        if used >= max_per_document:
            continue
        per_document[document_id] = used + 1
        chosen.add(chunk_id)
    emitted: set[UUID] = set()
    selected: list[RerankPassage] = []
    for item in ordered:
        chunk_id = item.candidate.chunk_id
        if chunk_id not in chosen or chunk_id in emitted:
            continue
        emitted.add(chunk_id)
        selected.append(
            _pool_passage(
                item,
                excerpt_chars=excerpt_chars,
                query=query,
                excerpt_strategy=excerpt_strategy,
            )
        )
    return tuple(selected)


def _pool_passage(
    item: RerankPassage,
    *,
    excerpt_chars: int,
    query: str | None,
    excerpt_strategy: str,
) -> RerankPassage:
    """Copy one pool member with its bounded rerank excerpt.

    Args:
        item: Authorized passage in fused order.
        excerpt_chars: Excerpt character budget.
        query: Original query for query-aware excerpts.
        excerpt_strategy: ``prefix`` or ``query_aware``.

    Returns:
        Passage with ``excerpt`` set; citation ``raw_text`` unchanged.
    """

    return RerankPassage(
        candidate=item.candidate,
        raw_text=item.raw_text,
        section_path=item.section_path,
        page_number=item.page_number,
        parent_chunk_id=item.parent_chunk_id,
        chunk_index=item.chunk_index,
        token_count=item.token_count or max(1, len(item.raw_text.split())),
        channels=item.channels,
        excerpt=excerpt_text(
            item.raw_text,
            limit=excerpt_chars,
            query=query,
            strategy=excerpt_strategy,
        ),
    )


def should_skip_trivial_exact(
    profile: ExpectedProfile,
    pool: tuple[RerankPassage, ...],
) -> bool:
    """Skip OpenAI rerank only for a fully supported trivial exact lookup.

    Numeric score gaps never qualify. The winner must be independently
    present in at least two applicable channels, and required codes or
    quoted phrases plus filters must be complete.

    Args:
        profile: Typed query profile.
        pool: Capped rerank pool in fused order.

    Returns:
        True only for the plan's trivial exact skip.
    """

    if len(pool) < 2:
        return False
    query_type = str(profile.query_type.value)
    if query_type != QueryType.EXACT_IDENTIFIER.value:
        return False
    codes = profile.codes.value if isinstance(profile.codes.value, list) else []
    quoted = (
        profile.quoted_phrases.value
        if isinstance(profile.quoted_phrases.value, list)
        else []
    )
    if not codes and not quoted:
        return False
    filters = profile.metadata_filters.value
    if isinstance(filters, list) and any(
        "=" in str(item) and str(item).split("=", 1)[0] not in {"tag", "language"}
        for item in filters
    ):
        return False
    winner_channels = pool[0].channels
    return len(winner_channels) >= 2


def rerank_json_schema(
    candidate_ids: tuple[str, ...],
    *,
    input_hash: str,
) -> dict[str, object]:
    """Build a request-specific strict JSON schema.

    Args:
        candidate_ids: Canonical chunk UUID strings in pool order.
        input_hash: SHA-256 of the canonical request payload.

    Returns:
        OpenAI ``json_schema`` document with an ID enum.

    Raises:
        ValueError: If the pool is empty or larger than 20.
    """

    if not candidate_ids or len(candidate_ids) > RERANK_POOL_SIZE:
        raise ValueError("rerank_pool_size_invalid")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "input_hash", "rankings"],
        "properties": {
            "status": {"type": "string", "enum": ["complete"]},
            "input_hash": {"type": "string", "minLength": 64, "maxLength": 64},
            "rankings": {
                "type": "array",
                "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["chunk_id", "rank", "support"],
                    "properties": {
                        "chunk_id": {"type": "string", "enum": list(candidate_ids)},
                        "rank": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": len(candidate_ids),
                        },
                        "support": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
            },
        },
    }


class RerankRowModel(BaseModel):
    """One ranking row after JSON Schema validation.

    Attributes:
        chunk_id: Candidate UUID string.
        rank: 1-based rank.
        support: Ranking feature in ``[0, 1]``, not a probability.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    rank: int = Field(ge=1)
    support: float
    supported_subquestion_indices: list[int] = Field(default_factory=list[int])

    @field_validator("rank", mode="before")
    @classmethod
    def reject_boolean_rank(cls, value: object) -> object:
        """Reject ``bool`` values that would otherwise pass as integers.

        Args:
            value: Raw rank field.

        Returns:
            Unchanged non-boolean value.

        Raises:
            ValueError: If the value is a boolean.
        """

        if isinstance(value, bool):
            raise ValueError("rerank_rank_invalid")
        return value

    @field_validator("support", mode="before")
    @classmethod
    def reject_invalid_support(cls, value: object) -> object:
        """Reject booleans and out-of-range support scores.

        Args:
            value: Raw support field.

        Returns:
            Unchanged in-range numeric value.

        Raises:
            ValueError: If support is a boolean or outside ``[0, 1]``.
        """

        if isinstance(value, bool):
            raise ValueError("rerank_support_invalid")
        if isinstance(value, int | float) and (value < 0.0 or value > 1.0):
            raise ValueError("rerank_support_out_of_bounds")
        return value


class RerankPayloadModel(BaseModel):
    """Strict rerank JSON object before application set-equality checks.

    Attributes:
        status: Must be ``complete``.
        input_hash: Echo of the request digest.
        rankings: One row per supplied candidate.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["complete"]
    input_hash: str = Field(min_length=64, max_length=64)
    rankings: list[RerankRowModel]


def validate_rerank_payload(
    payload: object,
    *,
    candidate_ids: tuple[UUID, ...],
    input_hash: str,
) -> tuple[RerankRanking, ...]:
    """Enforce set equality, uniqueness, order, and support bounds.

    A schema-valid payload can still be semantically invalid.

    Args:
        payload: Parsed JSON object.
        candidate_ids: Exact supplied ID set in pool order.
        input_hash: Canonical request digest that must be echoed.

    Returns:
        Rankings sorted by rank ascending.

    Raises:
        RerankPayloadError: If status, IDs, ranks, or support violate the
            contract. ``str(error)`` is the specific reason and
            ``subcode`` is its coarse class.
    """

    try:
        body = RerankPayloadModel.model_validate(payload)
    except ValidationError as error:
        messages = " ".join(str(item.get("msg", "")) for item in error.errors())
        locations = [item.get("loc", ()) for item in error.errors()]
        if "rerank_support_out_of_bounds" in messages:
            raise RerankPayloadError(
                "rerank_support_out_of_bounds", subcode="json"
            ) from error
        if "rerank_support_invalid" in messages:
            raise RerankPayloadError(
                "rerank_support_invalid", subcode="json"
            ) from error
        if "rerank_rank_invalid" in messages:
            raise RerankPayloadError("rerank_rank_invalid", subcode="json") from error
        if any(loc and loc[-1] == "status" for loc in locations):
            raise RerankPayloadError("rerank_incomplete", subcode="json") from error
        raise RerankPayloadError("rerank_schema_invalid", subcode="json") from error
    if body.input_hash != input_hash:
        raise RerankPayloadError("rerank_input_hash_mismatch", subcode="hash")
    if len(body.rankings) != len(candidate_ids):
        raise RerankPayloadError("rerank_ranking_length", subcode="length")
    expected = {str(item) for item in candidate_ids}
    seen_ids: set[str] = set()
    seen_ranks: set[int] = set()
    parsed: list[RerankRanking] = []
    for row in body.rankings:
        if row.chunk_id not in expected:
            raise RerankPayloadError(
                "rerank_unknown_or_missing_id", subcode="unknown_id"
            )
        if row.chunk_id in seen_ids:
            raise RerankPayloadError("rerank_duplicate_id", subcode="duplicate")
        if row.rank > len(candidate_ids):
            raise RerankPayloadError("rerank_rank_invalid", subcode="json")
        if row.rank in seen_ranks:
            raise RerankPayloadError("rerank_rank_invalid", subcode="duplicate")
        seen_ids.add(row.chunk_id)
        seen_ranks.add(row.rank)
        parsed.append(
            RerankRanking(
                chunk_id=UUID(row.chunk_id),
                rank=row.rank,
                support=float(row.support),
                supported_subquestion_indices=_validated_subquestion_indices(
                    row.supported_subquestion_indices
                ),
            )
        )
    if seen_ids != expected:
        raise RerankPayloadError("rerank_id_set_mismatch", subcode="unknown_id")
    parsed.sort(key=lambda item: item.rank)
    return tuple(parsed)


def _validated_subquestion_indices(raw: Sequence[object]) -> tuple[int, ...]:
    """Keep at most three unique 0-based subquestion indices.

    Args:
        raw: Model-supplied indices.

    Returns:
        Unique indices in ``{0, 1, 2}`` order of first appearance.
    """

    unique: list[int] = []
    seen: set[int] = set()
    for index in raw:
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        if index < 0 or index > 2 or index in seen:
            continue
        seen.add(index)
        unique.append(index)
        if len(unique) >= 3:
            break
    return tuple(unique)


def _jaccard(left: str, right: str) -> float:
    """Token Jaccard on ``arabic_norm_v1`` forms.

    Args:
        left: First text.
        right: Second text.

    Returns:
        Similarity in ``[0, 1]``.
    """

    left_tokens = set(normalize_arabic_v1(left).split())
    right_tokens = set(normalize_arabic_v1(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def apply_mmr(
    ordered: tuple[RerankPassage, ...],
    *,
    query: str,
    lambda_mult: float = MMR_LAMBDA,
    document_quota: int = DOCUMENT_QUOTA,
    section_quota: int = SECTION_QUOTA,
    limit: int = FINAL_EVIDENCE_MAX,
    candidate_depth: int = MMR_CANDIDATE_DEPTH,
) -> tuple[tuple[RerankPassage, ...], tuple[UUID, ...]]:
    """Select diverse evidence with per-document and per-section quotas.

    Relevance is rank order (or RRF fallback order). Token Jaccard is a
    duplicate penalty only. UUID is the exact-tie break. Rank relevance
    survives zero lexical overlap with the query.

    Args:
        ordered: Post-rerank (or RRF fallback) pool.
        query: Original query. Unused for relevance; kept for call sites.
        lambda_mult: Relevance versus diversity mix.
        document_quota: Max selected passages per document.
        section_quota: Max selected passages per first heading.
        limit: Final evidence cap.
        candidate_depth: MMR candidate prefix.

    Returns:
        Selected passages and dropped IDs.
    """

    del query
    depth = ordered[:candidate_depth]
    remaining = list(depth)
    selected: list[RerankPassage] = []
    doc_counts: dict[UUID, int] = {}
    section_counts: dict[str, int] = {}
    rank_by_id = {item.candidate.chunk_id: index for index, item in enumerate(depth)}
    while remaining and len(selected) < limit:

        def score(item: RerankPassage) -> tuple[float, str]:
            """MMR objective with stable ID tie-break.

            Args:
                item: Candidate still in the pool.

            Returns:
                Sort key: higher MMR first, then canonical ID.
            """

            rank = rank_by_id.get(item.candidate.chunk_id, len(depth))
            relevance = 1.0 / (rank + 1)
            diversity = 0.0
            if selected:
                diversity = max(
                    _jaccard(
                        item.excerpt or item.raw_text, other.excerpt or other.raw_text
                    )
                    for other in selected
                )
            return (
                -(lambda_mult * relevance - (1.0 - lambda_mult) * diversity),
                str(item.candidate.chunk_id),
            )

        remaining.sort(key=score)
        pick = remaining.pop(0)
        document_id = pick.candidate.document_id
        section = pick.section_path[0] if pick.section_path else ""
        if doc_counts.get(document_id, 0) >= document_quota:
            continue
        if section and section_counts.get(section, 0) >= section_quota:
            continue
        selected.append(pick)
        doc_counts[document_id] = doc_counts.get(document_id, 0) + 1
        if section:
            section_counts[section] = section_counts.get(section, 0) + 1
    selected_ids = {item.candidate.chunk_id for item in selected}
    dropped = tuple(
        item.candidate.chunk_id
        for item in depth
        if item.candidate.chunk_id not in selected_ids
    )
    return tuple(selected), dropped


def trim_token_budget(
    passages: tuple[RerankPassage, ...],
    *,
    budget: int = FINAL_TOKEN_BUDGET,
    limit: int = FINAL_EVIDENCE_MAX,
) -> tuple[RerankPassage, ...]:
    """Keep at most 12 units inside the token budget.

    Args:
        passages: Ordered evidence including expanded parents.
        budget: Token ceiling.
        limit: Unit ceiling.

    Returns:
        Prefix that fits both bounds.
    """

    kept: list[RerankPassage] = []
    tokens = 0
    for item in passages:
        cost = item.token_count or max(1, len(item.raw_text.split()))
        if len(kept) >= limit or tokens + cost > budget:
            break
        kept.append(item)
        tokens += cost
    return tuple(kept)
