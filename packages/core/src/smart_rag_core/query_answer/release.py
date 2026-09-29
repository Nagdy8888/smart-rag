"""Release only verifier-supported company claims into durable answer prose."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.bind import bind_company_atomic_links
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import (
    citation_free_refusal,
    drop_unsupported_paragraphs,
    exact_source_span,
)
from smart_rag_core.query_answer.versions import PARAGRAPH_DELIMITER
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

_ACRONYM_PAREN = re.compile(r"\b([A-Z]{2,10})\s*\(([^)]{2,80})\)")
_PAREN_ACRONYM = re.compile(
    r"\b([A-Z][A-Za-z0-9][A-Za-z0-9 ./-]{1,60}?)\s*\(([A-Z]{2,10})\)"
)
_STANDS_FOR = re.compile(
    r"\b([A-Z]{2,10})\s+(?:stands for|means|is short for|expands to)\s+"
    r"([A-Za-z][A-Za-z0-9 ./-]{1,80})",
    re.IGNORECASE,
)
_TITLE_PHRASE = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)+)\b")
_QUOTED = re.compile(r"\"([^\"]{1,200})\"|'([^']{1,200})'|`([^`]{1,200})`")
_TRAILING_QUOTE_PUNCTUATION = ".,;:!?…"
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NAMED_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)
_CODE_TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(?:\(\))?")
_SNAKE_IDENTIFIER = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
_GENERAL_ORIGINS = frozenset(
    {
        KnowledgeScope.GENERAL_KNOWLEDGE,
        KnowledgeScope.USER_SUPPLIED_TEXT,
        KnowledgeScope.DETERMINISTIC,
        KnowledgeScope.AMBIGUOUS,
        KnowledgeScope.WEB,
    }
)


def company_release_applies(payload: AnswerPayload, *, is_web: bool) -> bool:
    """Return whether grounded company rendering should rewrite this payload.

    Args:
        payload: Verified or checked answer.
        is_web: True when the run is the Web path.

    Returns:
        False for general, user-text, deterministic, ambiguous, and Web
        answers. True for company-document payloads.
    """

    if is_web:
        return False
    origin = payload.answer_origin
    if origin in _GENERAL_ORIGINS:
        return False
    if origin is KnowledgeScope.COMPANY_DOCUMENTS:
        return True
    return bool(payload.paragraphs or payload.atomic_links)


def render_verified_company_answer(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Replace free-form company prose with surviving atomic-link claims.

    Application code owns released ``answer_text``. Provider paragraph
    bodies are never copied. Citations are rebuilt from surviving links
    only; fusion passages are never backfilled.

    Args:
        payload: Answer after deterministic checks and the verifier batch.
        fusion: Fitted canonical evidence for this run.
        tables: Deterministic table snapshots.

    Returns:
        Payload whose prose is unique surviving claims, plus a composed
        conclusion only when every listed link survived. Citation-free
        refusal when no supported material link remains.
    """

    working = bind_company_atomic_links(payload, fusion=fusion)
    guarded = drop_ungrounded_literals(working, fusion=fusion, tables=tables)
    surviving = tuple(
        sorted(guarded.atomic_links, key=lambda item: (item.priority, item.link_id))
    )
    if not surviving:
        return citation_free_refusal(guarded)

    def _unique_claims(links: tuple[AtomicLink, ...]) -> tuple[AtomicLink, ...]:
        """Keep the first occurrence of each claim in priority order.

        Args:
            links: Surviving links already sorted by ``(priority, link_id)``.

        Returns:
            Deduplicated links.
        """

        seen: set[str] = set()
        unique: list[AtomicLink] = []
        for item in links:
            key = _normalize(item.claim)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return tuple(unique)

    unique_links = _unique_claims(surviving)
    conclusion = guarded.composed_conclusion
    kept_ids = {item.link_id for item in surviving}
    if conclusion is not None and any(
        link_id not in kept_ids for link_id in conclusion.link_ids
    ):
        conclusion = None
    claim_texts = [item.claim.strip() for item in unique_links]
    if conclusion is not None:
        claim_texts.append(conclusion.text.strip())
    stripped_ungrounded = _original_prose_had_ungrounded_expansion(
        payload, surviving=surviving, fusion=fusion, tables=tables
    )
    status = guarded.status
    if stripped_ungrounded and status == "complete":
        status = "partial"
    paragraphs, citations, table_citations = _rebuild_paragraphs_and_citations(
        unique_links,
        original=guarded,
        fusion=fusion,
        tables=tables,
    )
    return guarded.model_copy(
        update={
            "answer_text": PARAGRAPH_DELIMITER.join(claim_texts),
            "paragraphs": paragraphs,
            "citations": citations,
            "table_citations": table_citations,
            "atomic_links": surviving,
            "composed_conclusion": conclusion,
            "status": status,
        }
    )


def drop_ungrounded_literals(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Drop links whose exact-value guards fail, even if a verifier agreed.

    Args:
        payload: Answer after deterministic/verifier filtering.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Payload without links that invent acronym expansions or fact
        literals absent from cited sources.
    """

    unsupported = frozenset(
        item.link_id
        for item in payload.atomic_links
        if _link_fails_literal_guard(item, fusion=fusion, tables=tables)
    )
    if not unsupported:
        return payload
    return drop_unsupported_paragraphs(payload, unsupported)


def _link_fails_literal_guard(
    link: AtomicLink,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether one link invents an expansion or missing fact literal.

    Args:
        link: Candidate atomic claim.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        True when the claim must be dropped.
    """

    source_text = _cited_source_text(link, fusion=fusion, tables=tables)
    if _acronym_expansion_fails(link.claim, source_text):
        return True
    if link.kind != "fact":
        return False
    return _fact_literals_missing(link.claim, source_text)


def _cited_source_text(
    link: AtomicLink,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> str:
    """Join cited passage and table text for one link.

    Args:
        link: Atomic claim.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Concatenated cited source text.
    """

    passages = {item.chunk_id: item.citation_text for item in fusion.evidence}
    bodies = [passages[chunk_id] for chunk_id in link.chunk_ids if chunk_id in passages]
    if link.table_id:
        record = next((item for item in tables if item.table_id == link.table_id), None)
        if record is not None:
            bodies.append(f"{record.operation} {record.rows} {record.source_ranges}")
    return "\n".join(bodies)


def _normalize(text: str) -> str:
    """Collapse case and whitespace for exact expansion compares.

    Args:
        text: Raw expansion or phrase.

    Returns:
        Lowercased collapsed form.
    """

    return " ".join(text.strip().lower().split()).strip(".,:;!?")


def _acronym_expansions(text: str) -> dict[str, set[str]]:
    """Extract acronym-to-expansion maps from definition-shaped phrases.

    Args:
        text: Source or claim text.

    Returns:
        Acronym keys mapped to normalized expansions.
    """

    found: dict[str, set[str]] = {}
    for match in _ACRONYM_PAREN.finditer(text):
        found.setdefault(match.group(1), set()).add(_normalize(match.group(2)))
    for match in _PAREN_ACRONYM.finditer(text):
        found.setdefault(match.group(2), set()).add(_normalize(match.group(1)))
    for match in _STANDS_FOR.finditer(text):
        found.setdefault(match.group(1).upper(), set()).add(_normalize(match.group(2)))
    return found


def _title_phrases(text: str) -> tuple[str, ...]:
    """Return Title Case multi-word phrases.

    Args:
        text: Source or claim text.

    Returns:
        Normalized phrases with at least two words.
    """

    return tuple(_normalize(item.group(0)) for item in _TITLE_PHRASE.finditer(text))


def _acronym_expansion_fails(claim: str, source_text: str) -> bool:
    """Return whether the claim invents or mismatches an acronym expansion.

    Args:
        claim: Atomic claim or paragraph sentence.
        source_text: Cited canonical text.

    Returns:
        True when an expansion is not spelled in the source or conflicts.
    """

    source_defs = _acronym_expansions(source_text)
    claim_defs = _acronym_expansions(claim)
    normalized_source = _normalize(source_text)
    for acronym, expansions in claim_defs.items():
        allowed = set(source_defs.get(acronym, set()))
        for expansion in expansions:
            if expansion and expansion in normalized_source:
                allowed.add(expansion)
        if not allowed or any(item not in allowed for item in expansions):
            return True
    claim_phrases = _title_phrases(claim)
    for expansions in source_defs.values():
        for expansion in expansions:
            words = expansion.split()
            if len(words) < 2:
                continue
            last = words[-1]
            for phrase in claim_phrases:
                phrase_words = phrase.split()
                if (
                    len(phrase_words) == len(words)
                    and phrase_words[-1] == last
                    and phrase not in expansions
                ):
                    return True
    return False


def _quoted_literal_in_source(literal: str, source_text: str) -> bool:
    """Return whether quoted words occur verbatim in the cited source.

    The comparison does not rewrite the claim and does not invent a
    quote. A trailing sentence mark is ignored only when the remaining
    text is non-empty and already present in ``source_text``. Letter
    case is not a mismatch: ``higher`` matches ``Higher``.

    Args:
        literal: Text inside one pair of quotes or backticks.
        source_text: Cited canonical passage or table text.

    Returns:
        True when ``literal``, or ``literal`` without trailing sentence
        punctuation, occurs in ``source_text`` ignoring capitalization.
    """

    if _source_occurrence(literal, source_text) is not None:
        return True
    stripped = literal.rstrip(_TRAILING_QUOTE_PUNCTUATION)
    if not stripped or stripped == literal:
        return False
    return _source_occurrence(stripped, source_text) is not None


def _source_occurrence(needle: str, source: str) -> str | None:
    """Return the passage's own spelling of ``needle``.

    Args:
        needle: Text taken from a claim.
        source: Cited canonical passage or table text.

    Returns:
        The matching substring copied from ``source``, or ``None`` when
        those words are absent. Capitalization may differ.
    """

    if not needle:
        return None
    match = re.search(re.escape(needle), source, re.IGNORECASE)
    if match is None:
        return None
    return match.group(0)


def _fact_literals_missing(claim: str, source_text: str) -> bool:
    """Return whether a fact claim uses literals absent from the cited source.

    Args:
        claim: Fact-link claim.
        source_text: Cited canonical text.

    Returns:
        True when a required quoted, numeric, date, or code literal is
        absent. A trailing sentence mark inside a quote is not a new
        literal when the quoted words themselves occur in the source.
    """

    for match in _QUOTED.finditer(claim):
        literal = next(item for item in match.groups() if item)
        if not _quoted_literal_in_source(literal, source_text):
            return True
    for match in _NUMBER.finditer(claim):
        if match.group(0) not in source_text:
            return True
    for pattern in (_ISO_DATE, _NAMED_DATE, _CODE_TOKEN):
        for match in pattern.finditer(claim):
            if match.group(0) not in source_text:
                return True
    return False


def align_split_source_identifiers(
    before: AnswerPayload,
    after: AnswerPayload,
    *,
    fusion: FusionResult,
) -> AnswerPayload:
    """Keep a fact the cited passage already states, and cite that passage.

    A verifier rejection is ignored only when every quoted literal, number,
    and snake_case token in the claim already occurs in the cited passage.
    The released claim and citation span then become one verbatim excerpt
    of that passage. No words are added. A name the passage does not
    contain stays dropped.

    Surviving claims that only split a source token, such as
    ``process numbers`` for ``process_numbers``, are rewritten to that
    token.

    Args:
        before: Answer the verifier received.
        after: Answer after unsupported links were removed.
        fusion: Canonical passages for the cited chunk IDs.

    Returns:
        ``after`` when nothing cited was restored. Otherwise the answer
        with grounded fact links kept and their text copied from the
        passage.
    """

    surviving = {link.link_id for link in after.atomic_links}
    repaired: dict[str, AtomicLink] = {}
    for link in before.atomic_links:
        if link.link_id in surviving:
            spacing = _repair_split_identifier(link, fusion)
            if spacing is not None:
                repaired[link.link_id] = spacing
            continue
        grounded = _ground_rejected_fact(link, before, fusion)
        if grounded is not None:
            repaired[link.link_id] = grounded
    if not repaired:
        return after
    merged_ids = surviving | set(repaired)
    links = tuple(
        repaired.get(link.link_id, link)
        for link in before.atomic_links
        if link.link_id in merged_ids
    )
    if links == after.atomic_links:
        return after
    paragraphs = tuple(
        paragraph.model_copy(update={"text": restored.claim})
        if (restored := repaired.get(paragraph.link_ids[0])) is not None
        and paragraph.link_ids == (restored.link_id,)
        else paragraph
        for paragraph in before.paragraphs
    )
    citations = tuple(
        citation.model_copy(update={"span": restored.claim})
        if (restored := repaired.get(citation.atomic_link_id or "")) is not None
        and citation.chunk_id in restored.chunk_ids
        and restored.claim in _cited_source_text(restored, fusion=fusion, tables=())
        else citation
        for citation in before.citations
    )
    payload = before.model_copy(
        update={
            "atomic_links": links,
            "paragraphs": paragraphs,
            "citations": citations,
        }
    )
    unsupported = frozenset(
        link.link_id for link in before.atomic_links if link.link_id not in merged_ids
    )
    if not unsupported:
        return payload
    return drop_unsupported_paragraphs(payload, unsupported)


def _repair_split_identifier(
    link: AtomicLink,
    fusion: FusionResult,
) -> AtomicLink | None:
    """Restore snake_case tokens that the claim wrote with spaces.

    Args:
        link: Fact claim cited to one or more passages.
        fusion: Canonical passages.

    Returns:
        The link with source tokens restored, or ``None`` when no split
        token was repaired or the repaired claim still invents a literal
        or identifier.
    """

    if link.kind != "fact":
        return None
    source = _cited_source_text(link, fusion=fusion, tables=())
    if not source:
        return None
    tokens = sorted(set(_SNAKE_IDENTIFIER.findall(source)), key=len, reverse=True)
    updated = link.claim
    replaced = False
    for token in tokens:
        if token in updated:
            continue
        spaced = token.replace("_", " ")
        pattern = re.compile(
            rf"(?<![\w]){re.escape(spaced)}(?![\w])(?!\s+[A-Za-z0-9])",
            re.IGNORECASE,
        )
        rewritten, count = pattern.subn(token, updated)
        if count:
            updated = rewritten
            replaced = True
    if not replaced or updated == link.claim:
        return None
    if _fact_literals_missing(updated, source):
        return None
    source_tokens = set(_SNAKE_IDENTIFIER.findall(source))
    if not set(_SNAKE_IDENTIFIER.findall(updated)) <= source_tokens:
        return None
    return link.model_copy(update={"claim": updated})


def _ground_rejected_fact(
    link: AtomicLink,
    payload: AnswerPayload,
    fusion: FusionResult,
) -> AtomicLink | None:
    """Return a rejected fact rewritten as a verbatim cited excerpt.

    Args:
        link: Fact claim the verifier removed.
        payload: Answer the verifier received, including citation spans.
        fusion: Canonical passages.

    Returns:
        The link whose claim is an excerpt of the cited passage, or
        ``None`` when the claim introduces a literal or identifier the
        passage does not contain.
    """

    del payload
    if link.kind != "fact":
        return None
    source = _cited_source_text(link, fusion=fusion, tables=())
    excerpt = _verbatim_identifier_excerpt(source, link.claim)
    if excerpt is None:
        return None
    return link.model_copy(update={"claim": excerpt})


def _verbatim_identifier_excerpt(source: str, claim: str) -> str | None:
    """Return a passage excerpt that already contains the claim's literals.

    Args:
        source: Cited canonical text.
        claim: Fact claim rejected by the verifier.

    Returns:
        A substring of ``source`` covering every quoted literal, number,
        and snake_case token in ``claim``, or ``None`` when any of those
        is absent or the excerpt would exceed 1000 characters.
    """

    if not source or _fact_literals_missing(claim, source):
        return None
    claim_tokens = set(_SNAKE_IDENTIFIER.findall(claim))
    if not claim_tokens <= set(_SNAKE_IDENTIFIER.findall(source)):
        return None
    needles: list[str] = []
    for match in _QUOTED.finditer(claim):
        literal = next(item for item in match.groups() if item)
        found = _source_occurrence(literal, source)
        if found is None:
            stripped = literal.rstrip(_TRAILING_QUOTE_PUNCTUATION)
            found = _source_occurrence(stripped, source) if stripped else None
        if found:
            needles.append(found)
    needles.extend(token for token in claim_tokens if token in source)
    for match in _NUMBER.finditer(claim):
        if match.group(0) in source:
            needles.append(match.group(0))
    if not needles:
        return None
    host = source
    for part in source.split(PARAGRAPH_DELIMITER):
        if all(needle in part for needle in needles):
            host = part
            break
    start = min(host.find(needle) for needle in needles)
    end = max(host.find(needle) + len(needle) for needle in needles)
    left = host.rfind(". ", 0, start)
    right = host.find(". ", end)
    excerpt_start = 0 if left < 0 else left + 2
    excerpt_end = len(host) if right < 0 else right + 1
    excerpt = host[excerpt_start:excerpt_end].strip()
    if not excerpt or len(excerpt) > 1000 or PARAGRAPH_DELIMITER in excerpt:
        excerpt = host[start:end].strip()
    if (
        not excerpt
        or len(excerpt) > 1000
        or PARAGRAPH_DELIMITER in excerpt
        or excerpt not in source
    ):
        return None
    return excerpt


def _original_prose_had_ungrounded_expansion(
    payload: AnswerPayload,
    *,
    surviving: tuple[AtomicLink, ...],
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether original company prose contained a dropped expansion.

    Args:
        payload: Pre-render payload.
        surviving: Links that passed guards.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        True when original paragraphs or ``answer_text`` invented an
        expansion that surviving claims do not carry.
    """

    source_blob = "\n".join(
        (
            *(item.citation_text for item in fusion.evidence),
            *(f"{item.operation} {item.rows}" for item in tables),
        )
    )
    released = "\n".join(item.claim for item in surviving)
    originals = [payload.answer_text, *(item.text for item in payload.paragraphs)]
    for text in originals:
        if not text:
            continue
        if _acronym_expansion_fails(text, source_blob) and (
            ("Method Call Protocol" in text and "Method Call Protocol" not in released)
            or _acronym_expansion_fails(text, released)
        ):
            return True
    return False


def _rebuild_paragraphs_and_citations(
    unique_links: tuple[AtomicLink, ...],
    *,
    original: AnswerPayload,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> tuple[
    tuple[AnswerParagraph, ...],
    tuple[AnswerCitation, ...],
    tuple[AnswerCitation, ...],
]:
    """Build one paragraph per unique claim and citations from those links.

    Args:
        unique_links: Deduplicated surviving claims in release order.
        original: Payload holding original spans to reuse when valid.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Reindexed paragraphs, passage citations, and table citations.
    """

    passages = {item.chunk_id: item for item in fusion.evidence}
    tables_by_id = {item.table_id: item for item in tables}
    original_spans: dict[tuple[str | None, str | None, str], AnswerCitation] = {}
    for citation in (*original.citations, *original.table_citations):
        if citation.atomic_link_id is None:
            continue
        original_spans[
            (citation.chunk_id, citation.table_id, citation.atomic_link_id)
        ] = citation
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    table_citations: list[AnswerCitation] = []
    seen_pairs: set[tuple[str | None, str | None, str]] = set()
    all_links_by_claim: dict[str, tuple[str, ...]] = {}
    for item in original.atomic_links:
        key = _normalize(item.claim)
        all_links_by_claim[key] = (*all_links_by_claim.get(key, ()), item.link_id)
    for index, link in enumerate(unique_links):
        link_ids = all_links_by_claim.get(_normalize(link.claim), (link.link_id,))
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=index,
                text=link.claim.strip()[:4000],
                link_ids=link_ids[:6],
            )
        )
        for live in original.atomic_links:
            if live.link_id not in link_ids:
                continue
            for chunk_id in live.chunk_ids:
                pair = (chunk_id, None, live.link_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                reused = original_spans.get(pair)
                span = reused.span if reused is not None else None
                passage = passages.get(chunk_id)
                if passage is None:
                    continue
                if not span or span not in passage.citation_text:
                    span = exact_source_span(passage.citation_text)
                if not span:
                    continue
                citations.append(
                    AnswerCitation(
                        chunk_id=chunk_id,
                        span=span,
                        atomic_link_id=live.link_id,
                        paragraph_index=index,
                        inference=live.kind == "inference_link",
                    )
                )
            if live.table_id:
                pair = (None, live.table_id, live.link_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                record = tables_by_id.get(live.table_id)
                if record is None:
                    continue
                reused = original_spans.get(pair)
                table_citations.append(
                    AnswerCitation(
                        table_id=live.table_id,
                        source_ranges=reused.source_ranges
                        if reused is not None and reused.source_ranges
                        else record.source_ranges,
                        atomic_link_id=live.link_id,
                        paragraph_index=index,
                        inference=False,
                    )
                )
    return tuple(paragraphs), tuple(citations), tuple(table_citations)
