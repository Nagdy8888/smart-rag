"""Grounded company-document generation and extractive mock answers."""

from __future__ import annotations

import re
from collections.abc import Callable

from smart_rag_core.query_answer.assembly import (
    assemble_source_records,
    company_input_bound_payload,
    fit_source_records,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
)
from smart_rag_core.query_answer.paragraphs import (
    exact_source_span,
    join_paragraph_text,
    with_derived_answer_text,
)
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_answer.sanitize import empty_no_retrieval, filter_invented_ids
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_PARAGRAPHS,
    MAX_CITATION_SPAN_CHARS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.retrieval.rerank import (
    code_definition_gold_pattern,
    named_code_definition_ids,
    named_table_captions,
    table_caption_gold_pattern,
)

_NUMBER_LITERAL = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_HYPHEN_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")
_WORD_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_PROPER_NAME_TOKEN = re.compile(r"\b[A-Z][A-Za-z0-9_+./-]{2,}\b")
_STOP_LITERALS = frozenset(
    {
        "2",
        "4",
        "5",
        "about",
        "agents",
        "and",
        "answer",
        "applications",
        "building",
        "company",
        "document",
        "does",
        "figure",
        "from",
        "give",
        "how",
        "many",
        "name",
        "only",
        "page",
        "section",
        "that",
        "the",
        "use",
        "what",
        "with",
        "wording",
        "words",
    }
)


def _has_usable_company_evidence(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether grounded generation has citable company evidence.

    Fusion rows with empty ``citation_text`` are not usable: the live model
    can invent prose while the Sources tab stays empty.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.

    Returns:
        True when at least one passage has non-empty citation text or a
        table snapshot is present.
    """

    if tables:
        return True
    return any(item.citation_text.strip() for item in fusion.evidence)


def distinctive_query_literals(user_query: str) -> tuple[str, ...]:
    """Extract answer-shaped literals from the user question.

    Numbers, decimals, and hyphenated identifiers are distinctive enough
    to salvage a model refusal when they already appear in selected evidence.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Deduplicated literals in encounter order. Empty when none qualify.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _NUMBER_LITERAL.finditer(user_query):
        token = match.group(0)
        if token.lower() in _STOP_LITERALS:
            continue
        if len(token.replace(".", "").replace(",", "")) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(token)
    for match in _HYPHEN_TOKEN.finditer(user_query):
        token = match.group(0)
        key = token.lower()
        if key in seen or key in _STOP_LITERALS:
            continue
        seen.add(key)
        found.append(token)
    return tuple(found)


def significant_query_terms(user_query: str) -> tuple[str, ...]:
    """Return content tokens from the question for evidence overlap.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Lowercased tokens of length at least three, excluding stop words.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _WORD_TOKEN.finditer(user_query.lower()):
        token = match.group(0)
        if token in _STOP_LITERALS or token in seen:
            continue
        seen.add(token)
        found.append(token)
    return tuple(found)


# Book-title tokens appear in every company Ask prompt for this corpus and
# must never be treated as passage anchors (they match almost any page).
_BOOK_TITLE_NAME_STOP = frozenset(
    {
        "agents",
        "ai",
        "applications",
        "building",
        "designing",
        "implementing",
        "multiagent",
        "systems",
    }
)


def distinctive_query_names(user_query: str) -> tuple[str, ...]:
    """Extract capitalized product/name tokens from the user question.

    Exact-wording asks often name the target entity without numerals. Those
    names are strong passage anchors when they already appear in selected
    evidence. Tokens in ``_BOOK_TITLE_NAME_STOP`` are excluded.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Deduplicated proper-name tokens in encounter order.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _PROPER_NAME_TOKEN.finditer(user_query):
        token = match.group(0)
        key = token.casefold()
        if key in _STOP_LITERALS or key in _BOOK_TITLE_NAME_STOP or key in seen:
            continue
        # Skip title-case sentence starters that are ordinary English.
        if key in {
            "give",
            "in",
            "table",
            "the",
            "use",
            "what",
            "when",
            "which",
            "with",
        }:
            continue
        seen.add(key)
        found.append(token)
    return tuple(found)


def _is_empty_refusal(payload: AnswerPayload) -> bool:
    """Return whether the model produced no releasable company claims.

    Args:
        payload: Structured answer after invented-ID filtering.

    Returns:
        True when there are no atomic links and no paragraphs to release.
    """

    if payload.atomic_links or payload.paragraphs:
        return False
    return payload.status == "refused" or not payload.answer_text.strip()


def _normalize_figure_key(figure: str) -> str:
    """Collapse dash spacing so nearby figure spellings compare equal.

    Args:
        figure: Extracted figure substring.

    Returns:
        Lowercased key with spaces around dashes removed.
    """

    return re.sub(r"\s*([–\-−—])\s*", r"\1", figure.lower())


def _claim_text_corpus(payload: AnswerPayload) -> str:
    """Join claim and paragraph text for missing-figure checks.

    Args:
        payload: Current company answer.

    Returns:
        Lowercased corpus of answer, claims, and paragraphs with dash
        spacing normalized.
    """

    parts = [payload.answer_text]
    parts.extend(link.claim for link in payload.atomic_links)
    parts.extend(paragraph.text for paragraph in payload.paragraphs)
    return _normalize_figure_key("\n".join(parts))


_NEXT_CODE_DEF = re.compile(
    r"(?<![A-Za-z0-9_])(?:@tool\b|(?:async\s+)?def\s+\w+|class\s+\w+)"
)
_CODE_SECTION_BREAK = re.compile(r"#\s*--\s*\d+")


_LLM_ASSIGN_LOOKBACK = re.compile(r"(?i)(?:llm\s*=\s*)?ChatOpenAI\s*\([^)]*\)\s*")


def _extract_code_definition_block(text: str, match: re.Match[str]) -> str:
    """Copy a bounded ``def`` / ``@tool`` block from ``text``.

    Continues through blank lines inside the body so docstring-separated
    assignments (for example ``YOUR_*`` placeholders) stay in the span.
    Stops before a sibling ``def`` / ``@tool`` / ``class`` even when OCR
    flattened the page onto one line, and before book section markers
    like ``# -- 2)``. When the definition is ``call_model``, includes a
    preceding ``ChatOpenAI(...)`` assignment in the lookback window.
    ``_replace_with_extractive_block`` collapses blank lines for the
    paragraph contract while keeping this exact span for citations.

    Args:
        text: Passage citation text.
        match: Match for the definition line inside ``text``.

    Returns:
        Exact substring of ``text``, capped at ``MAX_CITATION_SPAN_CHARS``.
    """

    start = match.start()
    lookback = text[max(0, start - 40) : start]
    tool_at = lookback.rfind("@tool")
    if tool_at >= 0:
        start = max(0, start - 40) + tool_at
    # Include preceding ChatOpenAI assignment for call_model nodes.
    if re.search(r"(?i)def\s+call_model\s*\(", match.group(0)):
        prefix = text[max(0, start - 220) : start]
        llm = None
        for candidate in _LLM_ASSIGN_LOOKBACK.finditer(prefix):
            llm = candidate
        if llm is not None:
            start = max(0, start - 220) + llm.start()
    rest = text[match.end() :]
    end = match.end() + len(rest)
    next_def = _NEXT_CODE_DEF.search(rest)
    if next_def is not None:
        end = min(end, match.end() + next_def.start())
    section = _CODE_SECTION_BREAK.search(rest)
    if section is not None:
        end = min(end, match.end() + section.start())
    block = text[start:end].strip()
    if not block or block not in text:
        block = match.group(0).strip()
    if not block or block not in text:
        return ""
    return block[:MAX_CITATION_SPAN_CHARS]


def _best_code_definition_match(
    fusion: FusionResult,
    pattern: re.Pattern[str],
    *,
    user_query: str | None = None,
) -> tuple[ScoredPassage, re.Match[str], str] | None:
    """Return the best definition hit and its extractable block.

    Prefers an earlier ``def`` offset in the passage (primary definition
    over a reprint), then ``YOUR_*`` placeholders, better hybrid rank,
    and longer bodies.

    Args:
        fusion: Fitted canonical evidence.
        pattern: Compiled ``def`` / ``@tool def`` pattern.
        user_query: Original user text for overlap ranking. Untrusted.

    Returns:
        Passage, match, and exact block, or ``None``.
    """

    ranked: list[tuple[int, int, int, int, ScoredPassage, re.Match[str], str]] = []
    for item in fusion.evidence:
        text = item.citation_text or ""
        match = pattern.search(text)
        if match is None:
            continue
        span = _extract_code_definition_block(text, match)
        if not span:
            continue
        overlap = _passage_query_overlap(user_query, text) if user_query else 0
        ranked.append(
            (
                match.start(),
                1 if "YOUR_" in span else 0,
                item.hybrid_rank or 10_000,
                len(span),
                item,
                match,
                span,
            )
        )
    if not ranked:
        return None
    ranked.sort(
        key=lambda row: (
            row[0],
            -row[1],
            row[2],
            -row[3],
            row[4].chunk_id,
        )
    )
    _offset, _your, _rank, _length, item, match, span = ranked[0]
    return item, match, span


_TABLE_CAPTION_ANY = re.compile(r"(?i)Table\s+(\d+)-(\d+)")
_CHAPTER_FOOTER = re.compile(
    r"(?m)(?:^|\n)\s*\d+\s*\|\s*Chapter\s+\d+",
)
_TABLE_PROSE_INTRO = re.compile(
    r"(?i)\b(?:a small selection|are shown along|at a glance|you can adapt|"
    r"as you.?ll see in|see in table|shown in table|refer to table)\b",
)


def _passage_has_titled_caption(text: str, captions: tuple[str, ...]) -> bool:
    """Return whether ``text`` holds a titled ``Table N-M.`` for ``captions``.

    Args:
        text: Passage citation text.
        captions: Query captions such as ``Table 2-1``.

    Returns:
        True when a caption appears with a trailing period title form.
    """

    if not text or not captions:
        return False
    lowered = text.casefold()
    return any(f"{caption.casefold()}." in lowered for caption in captions)


def _table_body_score(text: str, captions: tuple[str, ...]) -> int:
    """Score how strongly ``text`` looks like a table body, not a prose intro.

    Args:
        text: Passage citation text.
        captions: Query captions such as ``Table 2-1``.

    Returns:
        Higher is better. Prose intros score low even when they name the table.
        Titled ``Table N-M.`` captions outrank denser continuation pages that
        only back-reference the table in prose.
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
    digits = _NUMBER_LITERAL.findall(text)
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
    if _TABLE_PROSE_INTRO.search(text):
        score -= 8
    if not titled and _TABLE_PROSE_INTRO.search(text):
        # Continuation pages that say "as you'll see in Table N-M" while
        # holding later rows must not beat the titled caption page.
        score -= 20
    # Dense digit rows beat long prose with a single table mention.
    alpha = sum(1 for ch in text if ch.isalpha())
    if alpha > 0 and len(digits) >= 4 and len(digits) / max(1, alpha / 40) > 0.8:
        score += 6
    return score


def _extract_table_block(text: str, match: re.Match[str]) -> str:
    """Copy a bounded table caption plus following row text from ``text``.

    Prefers the titled caption form ``Table N-M.`` over prose that only
    mentions the table, searching the full passage so a later title is not
    missed when the gold regex hit the intro sentence. Stops before chapter
    footers and the next different table.

    Args:
        text: Passage citation text.
        match: Match for the caption/rows pattern inside ``text``.

    Returns:
        Exact substring of ``text``, capped at ``MAX_CITATION_SPAN_CHARS``.
    """

    cap = _TABLE_CAPTION_ANY.search(match.group(0))
    if cap is None:
        cap = _TABLE_CAPTION_ANY.search(text[match.start() : match.start() + 40])
    major = cap.group(1) if cap is not None else ""
    minor = cap.group(2) if cap is not None else ""
    start = match.start()
    if major and minor:
        titled = re.search(
            rf"(?i)Table\s+{re.escape(major)}-{re.escape(minor)}\.",
            text,
        )
        if titled is not None:
            start = titled.start()
        else:
            any_cap = re.search(
                rf"(?i)Table\s+{re.escape(major)}-{re.escape(minor)}\b",
                text[match.start() :],
            )
            if any_cap is not None:
                start = match.start() + any_cap.start()
    end = min(len(text), start + MAX_CITATION_SPAN_CHARS)
    rest = text[start:end]
    footer = _CHAPTER_FOOTER.search(rest)
    if footer is not None and footer.start() > 40:
        end = start + footer.start()
        rest = text[start:end]
    if major and minor:
        next_table = re.search(
            rf"(?i)Table\s+(?!{re.escape(major)}-{re.escape(minor)}\b)\d+-\d+",
            rest[20:],
        )
        if next_table is not None:
            end = start + 20 + next_table.start()
            rest = text[start:end]
    # Do not cut on capitalized single lines: OCR table rows start with a
    # capitalized name and would match a heading heuristic, dropping later
    # rows. Stop only before long narrative prose that follows the body.
    prose_after = re.search(
        r"(?m)^(?=.{140,})(?:While |However |In contrast |For our |"
        r"With a |These |This competition |Conversely )",
        rest[60:] if len(rest) > 60 else "",
    )
    if prose_after is not None:
        end = start + 60 + prose_after.start()
        rest = text[start:end]
    block = text[start:end].strip()
    if not block or block not in text:
        block = match.group(0).strip()
    if not block or block not in text:
        return ""
    return block[:MAX_CITATION_SPAN_CHARS]


def _replace_with_extractive_block(
    payload: AnswerPayload,
    *,
    chunk_id: str,
    span: str,
    link_id: str,
) -> AnswerPayload:
    """Rebuild the answer as one longer extractive block citing ``chunk_id``.

    Keeps up to ``MAX_CITATION_SPAN_CHARS`` so multi-literal code and table
    bodies fit.
    Citation ``span`` stays an exact evidence substring; paragraph and
    answer text collapse blank lines because ``AnswerParagraph`` forbids
    the ``\\n\\n`` delimiter.

    Args:
        payload: Prior company answer.
        chunk_id: Fusion chunk that holds ``span``.
        span: Exact citation span from evidence.
        link_id: Stable salvage link id.

    Returns:
        Complete payload with one fact claim.
    """

    # Citation span must remain an exact evidence substring.
    exact = span.strip()[:MAX_CITATION_SPAN_CHARS]
    if not exact:
        return payload
    # Keep newlines for table/code readability, but never emit the
    # paragraph join delimiter inside AnswerParagraph.text or claims.
    display = re.sub(
        r"\n{2,}",
        "\n",
        exact.replace("\r\n", "\n").replace("\r", "\n"),
    ).strip()
    if not display:
        return payload
    paragraph = AnswerParagraph(
        paragraph_index=0,
        text=display[:4000],
        link_ids=(link_id,),
    )
    citation = AnswerCitation(
        chunk_id=chunk_id,
        span=exact,
        atomic_link_id=link_id,
        paragraph_index=0,
    )
    link = AtomicLink(
        link_id=link_id,
        claim=display[:2000],
        chunk_ids=(chunk_id,),
        kind="fact",
        priority=10,
    )
    return payload.model_copy(
        update={
            "answer_text": display[:8000],
            "paragraphs": (paragraph,),
            "citations": (citation,),
            "atomic_links": (link,),
            "composed_conclusion": None,
            "status": "complete",
            "refused_links": (),
        }
    )


def _extractive_block_already_released(
    payload: AnswerPayload,
    span: str,
) -> bool:
    """Return True when the answer already covers the gold extractive block.

    A bare ``def name(`` match is not enough: wrong-neighbor answers often
    keep the signature while swapping the body. Require the leading slice
    and a mid-body slice after whitespace normalization.

    Args:
        payload: Current company answer.
        span: Exact gold block from evidence.

    Returns:
        True when salvage should leave the answer unchanged.
    """

    corpus = re.sub(r"\s+", " ", _claim_text_corpus(payload)).casefold()
    compact = re.sub(r"\s+", " ", span).casefold().strip()
    if not compact:
        return True
    if len(compact) <= 80:
        covered = compact in corpus
    else:
        head = compact[: min(120, len(compact))]
        if head not in corpus:
            return False
        mid_start = len(compact) // 3
        mid = compact[mid_start : mid_start + 100]
        covered = bool(mid) and mid in corpus
        # Signature / heading-only answers are much shorter than the gold
        # block. Even when a mid slice coincidentally appears, force salvage.
        if covered and len(corpus.strip()) < max(60, len(compact) // 4):
            return False
    if not covered:
        return False
    # Table bodies: require most gold digit literals so a prose intro that
    # names "Table N-M" cannot block salvage of the real rows.
    gold_digits = _NUMBER_LITERAL.findall(span)
    if len(gold_digits) >= 3:
        covered_digits = sum(1 for digit in gold_digits if digit in corpus)
        if covered_digits < max(3, (len(gold_digits) + 1) // 2):
            return False
    # Code bodies: a matching def that still trails sibling defs / section
    # markers must be re-salvaged so the UI does not show neighbor junk.
    payload_text = _claim_text_corpus(payload)
    if _CODE_SECTION_BREAK.search(payload_text) and not _CODE_SECTION_BREAK.search(
        span
    ):
        return False
    if _NEXT_CODE_DEF.search(payload_text):
        gold_defs = list(_NEXT_CODE_DEF.finditer(span))
        payload_defs = list(_NEXT_CODE_DEF.finditer(payload_text))
        if len(payload_defs) > max(1, len(gold_defs)):
            return False
    return True


def salvage_named_code_definition(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace a wrong snippet with the ``def`` block the query names.

    Applies only when the query asks to reproduce code and names a function
    identifier, and canonical evidence holds ``def <name>(``. After an empty
    refusal the matching block is always released.

    Args:
        payload: Company answer after binding.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the definition block, or unchanged when unmatched.
    """

    pattern = code_definition_gold_pattern(named_code_definition_ids(user_query))
    if pattern is None:
        return payload
    gold = _best_code_definition_match(fusion, pattern, user_query=user_query)
    if gold is None:
        return payload
    item, _match, span = gold
    if not _is_empty_refusal(payload) and _extractive_block_already_released(
        payload, span
    ):
        return payload
    return _replace_with_extractive_block(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="code-def-1",
    )


def salvage_named_table_block(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace prose/header-only table answers with caption plus row text.

    Triggers when the query names ``Table N-M`` (or asks to reproduce a
    table) and fused evidence holds the caption with nearby row content.
    Prefers titled caption+rows passages over prose intros that only
    mention the table.

    Args:
        payload: Company answer after code-definition salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the table block, or unchanged when unmatched.
    """

    captions = named_table_captions(user_query)
    gold_pattern = table_caption_gold_pattern(captions)
    if gold_pattern is None:
        return payload
    gold = _best_table_match(
        fusion, gold_pattern, captions=captions, user_query=user_query
    )
    if gold is None:
        return payload
    item, match = gold
    span = _extract_table_block(item.citation_text, match)
    if not span:
        return payload
    if _extractive_block_already_released(payload, span):
        return payload
    return _replace_with_extractive_block(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="table-block-1",
    )


def _best_table_match(
    fusion: FusionResult,
    pattern: re.Pattern[str],
    *,
    captions: tuple[str, ...],
    user_query: str | None = None,
) -> tuple[ScoredPassage, re.Match[str]] | None:
    """Return the best table-body passage for a named caption ask.

    Args:
        fusion: Fitted canonical evidence.
        pattern: Caption+nearby-token gold pattern.
        captions: Query captions such as ``Table 2-1``.
        user_query: Original user text for overlap ranking. Untrusted.

    Returns:
        Passage and match, or ``None``.
    """

    hits: list[tuple[ScoredPassage, re.Match[str]]] = []
    for item in fusion.evidence:
        text = item.citation_text or ""
        match = pattern.search(text)
        if match is not None:
            hits.append((item, match))
    if not hits:
        return None
    titled = [
        row
        for row in hits
        if _passage_has_titled_caption(row[0].citation_text or "", captions)
    ]
    if titled:
        hits = titled
    hits.sort(
        key=lambda row: (
            -_table_body_score(row[0].citation_text or "", captions),
            -(
                _passage_query_overlap(user_query, row[0].citation_text)
                if user_query
                else 0
            ),
            row[0].hybrid_rank or 10_000,
            row[0].chunk_id,
        )
    )
    return hits[0]


def _passage_query_overlap(query: str, text: str) -> int:
    """Count distinctive query tokens (length ≥4) present in ``text``.

    Args:
        query: Original user query. Untrusted.
        text: Passage citation text.

    Returns:
        Non-negative overlap count.
    """

    if not query or not text:
        return 0
    lowered = text.lower()
    seen: set[str] = set()
    score = 0
    for match in _WORD_TOKEN.finditer(query.lower()):
        token = match.group(0)
        if len(token) < 4 or token in _STOP_LITERALS or token in seen:
            continue
        seen.add(token)
        if token in lowered:
            score += 1
    return score


AnswerCaller = Callable[
    [str, FusionResult, tuple[TableEvidenceRecord, ...]], AnswerPayload
]


def generate_grounded_answer(
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    user_query: str,
    caller: AnswerCaller | None,
) -> AnswerPayload:
    """Generate one company-document answer from canonical evidence.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text. Untrusted.
        caller: Structured RAG answer adapter. None uses the extractive mock.

    Returns:
        Structured answer citing only supplied IDs.

    Raises:
        None. Empty evidence, or fusion rows with empty citation text and
        no tables, is a typed company refusal.
    """

    if not _has_usable_company_evidence(fusion, tables):
        return empty_no_retrieval(
            "Insufficient authorized evidence.",
            status="refused",
            origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
    fit = fit_source_records(
        user_query=user_query,
        fusion=fusion,
        tables=tables,
        max_input_chars=32_768,
        route=fusion.effective_route,
    )
    if fit.trim_reason == "input_bound_exceeded":
        return company_input_bound_payload()
    fusion = fit.fusion
    tables = fit.tables
    records = assemble_source_records(fusion, tables)
    if caller is None:
        payload = mock_answer_payload(fusion, tables, user_query=user_query)
    else:
        payload = caller(records, fusion, tables)
    filtered = bind_company_atomic_links(
        filter_invented_ids(payload, fusion, tables),
        fusion=fusion,
        user_query=user_query,
    )
    derived = with_derived_answer_text(filtered)
    for salvage_fn in (salvage_named_code_definition, salvage_named_table_block):
        salvaged = salvage_fn(derived, fusion, user_query=user_query)
        if salvaged is derived:
            continue
        filtered = bind_company_atomic_links(
            filter_invented_ids(salvaged, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    return derived.model_copy(
        update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
    )


def mock_answer_payload(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    *,
    user_query: str,
) -> AnswerPayload:
    """Build a deterministic fixture answer that cites supplied evidence IDs.

    This is mock-mode output, not a live company-knowledge claim. Table
    values are copied, never recalculated from prose. Each paragraph maps
    to exact spans copied from canonical ``citation_text``.

    Args:
        fusion: Canonical evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text.

    Returns:
        Structured answer citing at most six passages/tables with
        paragraph mappings.
    """

    del user_query
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    table_citations: list[AnswerCitation] = []
    links: list[AtomicLink] = []
    for index, item in enumerate(fusion.evidence, start=1):
        if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            break
        if len(links) >= MAX_VERIFIER_LINKS:
            break
        span = exact_source_span(item.citation_text)
        if not span:
            continue
        paragraph_index = len(paragraphs)
        link_id = f"link-{index}"
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=span[:4000],
                link_ids=(link_id,),
            )
        )
        citations.append(
            AnswerCitation(
                chunk_id=item.chunk_id,
                span=span,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=span[:400] or f"Canonical passage {item.chunk_id}",
                chunk_ids=(item.chunk_id,),
                kind="inference_link" if item.statement_ids else "fact",
                priority=index,
            )
        )
    for index, item in enumerate(tables, start=1):
        if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            break
        if len(links) >= MAX_VERIFIER_LINKS:
            break
        paragraph_index = len(paragraphs)
        link_id = f"table-{index}"
        body = (
            exact_source_span(f"{item.operation} {item.source_ranges} {item.rows}")
            or item.operation[:4000]
        )
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=body or item.operation,
                link_ids=(link_id,),
            )
        )
        table_citations.append(
            AnswerCitation(
                table_id=item.table_id,
                source_ranges=item.source_ranges,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=item.operation,
                table_id=item.table_id,
                source_ranges=item.source_ranges,
                kind="fact",
                priority=100 + index,
            )
        )
    conclusion = None
    inference_ids = tuple(
        item.link_id for item in links if item.kind == "inference_link"
    )
    if len(inference_ids) >= 2:
        conclusion = ComposedConclusion(
            text="Composed multi-hop inference from the cited atomic links.",
            kind="inference",
            link_ids=inference_ids,
        )
    joined = join_paragraph_text(tuple(paragraphs))
    status: str = "complete" if joined else "partial"
    return AnswerPayload(
        answer_text=joined[:8000] or "Insufficient authorized evidence.",
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        atomic_links=tuple(links),
        composed_conclusion=conclusion,
        table_citations=tuple(table_citations),
        status="complete" if status == "complete" else "partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
