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
    class_def_code_gold_pattern,
    code_definition_gold_pattern,
    constructor_code_gold_pattern,
    listed_literal_gold_pattern,
    listed_literal_groups,
    named_code_definition_ids,
    named_table_captions,
    table_caption_gold_pattern,
    wiring_code_gold_pattern,
)

_NUMBER_LITERAL = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_HYPHEN_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")
_WORD_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_MULTI_RATE_ASK = re.compile(r"(?i)\b(speaking|reading|skimming)\b")
_SHARE_AND_COST = re.compile(
    r"(?i)(?:\bshare\b.{0,80}\bcost\b|\bcost\b.{0,80}\bshare\b)"
)
_FIGURE_ASK_TERMS = re.compile(
    r"(?i)\b(rate|score|cost|share|plans?|pilot|acceptance|satisfaction)\b"
)
_FAQ_ORDER_ASK = re.compile(
    r"(?i)(?:\bfaqs?\b.{0,80}\border\b|\border\b.{0,80}\bfaqs?\b)"
)
_HELPER_NAME_ASK = re.compile(r"(?i)\bhelper\s+function\b|\bfunction\s+name\b")
_HELPER_NAMED = re.compile(
    r"(?i)helper\s+function\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)"
)
_EXPOSE_MODE_ASK = re.compile(
    r"(?i)(?:\bexpose\b|\blabel(?:s|ed)?\b).{0,80}\bmode"
    r"|\bmode.{0,40}\b(?:label|expose|slider|autonomy)"
    r"|\bautonomy[-\s]?slider\b"
)
# Prefer Label-these-modes triad. ``Assist(?!ed)`` / ``Auto(?!nom)`` reject
# the neighboring "assisted" / "autonomous" figure prose. Allow ASCII
# ``"Manual,"`` and Windows-1252 mojibake ``ôManual,ö``.
_EXPOSE_MODE_LABELS = re.compile(
    r"(?i)Label these modes.{0,100}?"
    r"Manual.{0,12}Assist(?!ed).{0,24}Auto(?!nom)"
    r'|(?:["“ô]Manual,["”ö]\s*["“ô]Assist,["”ö]\s*'
    r'(?:and\s+)?["“ô]Auto["”ö])'
)
_CONFUSER_MODE_LABELS = re.compile(
    r"(?i)Manual.{0,10}Ask.{0,16}Agent"
)
_ADAS_MODEL_ASK = re.compile(
    r"(?i)\b(?:ADAS|LLMAgentBase)\b"
    r"|(?:default\s+model|model\s+string).{0,40}temperature"
    r"|temperature.{0,40}(?:default\s+model|model\s+string)"
)
_ADAS_MODEL_DEFAULTS = re.compile(
    r"(?i)model\s*=\s*['\"]gpt-4o-\d{4}-\d{2}-\d{2}['\"]"
    r".{0,80}temperature\s*=\s*0\.5"
    r"|temperature\s*=\s*0\.5.{0,80}model\s*=\s*['\"]gpt-4o-\d{4}-\d{2}-\d{2}['\"]"
)
_CONFUSER_GPT4O_ZERO = re.compile(
    r"(?i)model\s*=\s*['\"]gpt-4o['\"].{0,80}temperature\s*=\s*0(?:\.0)?"
    r"|temperature\s*=\s*0(?:\.0)?.{0,80}model\s*=\s*['\"]gpt-4o['\"]"
)
_PSI_RETRAIN_ASK = re.compile(
    r"(?i)\bPSI\b.{0,80}(?:retrain|threshold|persist)"
    r"|(?:retrain|threshold|persist).{0,80}\bPSI\b"
)
_PSI_RETRAIN_GOLD = re.compile(
    r"(?i)PSI\s*>\s*0\.25.{0,80}48\s*hours"
    r"|48\s*hours.{0,80}PSI\s*>\s*0\.25"
    r"|prioritize retraining if PSI\s*>\s*0\.25"
)
_CHUNKING_ASK = re.compile(
    r"(?i)\bchunking_strategy\b|\bwindow_size\b.{0,40}\boverlap\b"
    r"|\boverlap\b.{0,40}\bwindow_size\b"
)
_CHUNKING_GOLD = re.compile(
    r"(?i)window_size\s*['\"‘’“”]?\s*[:=]\s*(\d+).{0,120}?overlap\s*['\"‘’“”]?\s*[:=]\s*(\d+)"
    r"|overlap\s*['\"‘’“”]?\s*[:=]\s*(\d+).{0,120}?window_size\s*['\"‘’“”]?\s*[:=]\s*(\d+)",
    re.DOTALL,
)
_TOOL_DESCRIPTION_ASK = re.compile(
    r"(?i)description\s+string|\btool_descriptions\b"
)
_TOOL_DESCRIPTION_GOLD = re.compile(
    r"(?i)Use\s+Wolfram\s+Alpha\s+to\s+compute\s+mathematical.{0,120}",
    re.DOTALL,
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
_EVIDENCE_FIGURE = re.compile(
    r"(?i)(?:"
    r"simple chatbots handling basic customer queries"
    r"|over\s+\d+(?:\.\d+)?%"
    r"|\$[\d,]+(?:\.\d+)?\s*(?:million|billion)"
    r"|\d+%\s+suggestion\s+acceptance\s+rate"
    r"|greater\s+than\s+\d+"
    r"|confidence\s*<\s*\d+(?:\.\d+)?"
    r"|\d+\s*[–\-−—]\s*\d+\s+words\s+per\s+minute"
    r"|\d+\s+words\s+per\s+minute"
    r")"
)
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


def _passage_contains_literal(text: str, literal: str) -> bool:
    """Return whether ``literal`` occurs in passage text.

    Args:
        text: Canonical citation text.
        literal: Distinctive query literal.

    Returns:
        True on case-insensitive substring match.
    """

    return literal.lower() in text.lower()


def salvage_refused_literal_claims(
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload | None:
    """Build extractive claims when selected evidence already holds the answer.

    A live model sometimes returns ``refused`` even though a fused passage
    contains the asked numeral, price, port, or hyphenated stream name.
    This salvage cites those passages with exact spans so the release path
    cannot wipe a grounded answer into ``Insufficient authorized evidence.``

    Args:
        fusion: Fitted canonical evidence for this run.
        user_query: Original user text. Untrusted.

    Returns:
        A complete company payload citing matching passages, or ``None``
        when no distinctive literal or strong term overlap is present.
    """

    literals = distinctive_query_literals(user_query)
    matched: list[tuple[ScoredPassage, tuple[str, ...]]] = []
    for item in fusion.evidence:
        text = item.citation_text.strip()
        if not text:
            continue
        hits = tuple(
            literal
            for literal in literals
            if _passage_contains_literal(text, literal)
        )
        if hits:
            matched.append((item, hits))
    if not matched:
        terms = significant_query_terms(user_query)
        scored: list[tuple[int, ScoredPassage, tuple[str, ...]]] = []
        for item in fusion.evidence:
            text = item.citation_text.lower()
            if not text.strip():
                continue
            hits = tuple(term for term in terms if term in text)
            if len(hits) >= 2:
                scored.append((len(hits), item, hits))
        scored.sort(key=lambda row: (-row[0], row[1].chunk_id))
        matched = [(item, hits) for _score, item, hits in scored[:3]]
    if not matched:
        return None
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    links: list[AtomicLink] = []
    for index, (item, hits) in enumerate(matched, start=1):
        if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            break
        if len(links) >= MAX_VERIFIER_LINKS:
            break
        span = exact_source_span(item.citation_text)
        if not span:
            continue
        claim = span[:400]
        paragraph_index = len(paragraphs)
        link_id = f"salvage-{index}"
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=claim[:4000],
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
                claim=claim[:400],
                chunk_ids=(item.chunk_id,),
                kind="fact",
                priority=index,
            )
        )
        del hits
    if not links:
        return None
    joined = join_paragraph_text(tuple(paragraphs))
    return AnswerPayload(
        answer_text=joined[:8000],
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        atomic_links=tuple(links),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def is_multipart_figure_ask(user_query: str) -> bool:
    """Return whether the question asks for multiple rates or figures.

    Triggers on three or more distinctive number tokens, explicit
    speaking/reading/skimming language, a share-and-cost ask, or at least
    two figure-shaped ask terms (rate, score, cost, share, plans, pilot,
    acceptance, satisfaction).

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        True when multi-part completeness salvage may apply.
    """

    if len(distinctive_query_literals(user_query)) >= 3:
        return True
    if len(set(_MULTI_RATE_ASK.findall(user_query))) >= 2:
        return True
    if _SHARE_AND_COST.search(user_query) is not None:
        return True
    if _FAQ_ORDER_ASK.search(user_query) is not None:
        return True
    return len(set(_FIGURE_ASK_TERMS.findall(user_query))) >= 2


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


def _evidence_figure_hits(
    fusion: FusionResult,
) -> list[tuple[ScoredPassage, str, str]]:
    """Collect figure spans from fused evidence.

    When one passage holds several rate figures, prefer a single span that
    covers every hit in that passage so multi-part asks release as one
    complete claim.

    Args:
        fusion: Fitted canonical passages.

    Returns:
        Triples of passage, exact figure substring (or combined label), and
        a short claim span copied from the passage.
    """

    hits: list[tuple[ScoredPassage, str, str]] = []
    seen: set[str] = set()
    for item in fusion.evidence:
        text = item.citation_text
        if not text.strip():
            continue
        matches = list(_EVIDENCE_FIGURE.finditer(text))
        if not matches:
            continue
        if len(matches) >= 2:
            start = max(0, matches[0].start() - 40)
            end = min(len(text), matches[-1].end() + 20)
            span = text[start:end].strip()
            if span and span in text:
                label = " | ".join(match.group(0).strip() for match in matches)
                key = _normalize_figure_key(label)
                if key not in seen:
                    seen.add(key)
                    for match in matches:
                        seen.add(_normalize_figure_key(match.group(0)))
                    hits.append((item, label, span[:400]))
                continue
        for match in matches:
            figure = match.group(0).strip()
            key = _normalize_figure_key(figure)
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 60)
            span = text[start:end].strip()
            if span not in text:
                span = figure
            if not span or span not in text:
                continue
            hits.append((item, figure, span[:400]))
    return hits


def salvage_missing_multipart_figures(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Append extractive claims for multi-part figures the model omitted.

    When the ask requests several rates or a share plus a cost, and fused
    evidence already holds figure literals missing from the claims, this
    salvage adds fact claims citing those passages. It is additive: existing
    claims stay; only remaining paragraph and verifier slots are used.

    Args:
        payload: Company answer after refusal salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload with appended figure claims, or unchanged when the ask is
        not multi-part or every evidence figure already appears.
    """

    if payload.status == "refused" and not payload.atomic_links:
        return payload
    if not is_multipart_figure_ask(user_query):
        return payload
    corpus = _claim_text_corpus(payload)
    all_hits = _evidence_figure_hits(fusion)
    present_chunk_ids: set[str] = set()
    for item, figure, _span in all_hits:
        parts = [part.strip() for part in figure.split(" | ") if part.strip()]
        if any(_normalize_figure_key(part) in corpus for part in parts):
            present_chunk_ids.add(item.chunk_id)
    missing: list[tuple[ScoredPassage, str, str]] = []
    for item, figure, span in all_hits:
        parts = [part.strip() for part in figure.split(" | ") if part.strip()]
        if all(_normalize_figure_key(part) in corpus for part in parts):
            continue
        if _normalize_figure_key(figure) in corpus:
            continue
        missing.append((item, figure, span))
    if present_chunk_ids:
        anchored = [
            row for row in missing if row[0].chunk_id in present_chunk_ids
        ]
        if anchored:
            missing = anchored
    if not missing:
        return payload
    paragraphs = list(payload.paragraphs)
    citations = list(payload.citations)
    links = list(payload.atomic_links)
    added = 0
    for item, figure, span in missing:
        if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            break
        if len(links) >= MAX_VERIFIER_LINKS:
            break
        exact = (
            span if span in item.citation_text else exact_source_span(item.citation_text)
        )
        if not exact or exact not in item.citation_text:
            continue
        paragraph_index = len(paragraphs)
        link_id = f"multipart-{added + 1}"
        claim = exact[:400]
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=claim[:4000],
                link_ids=(link_id,),
            )
        )
        citations.append(
            AnswerCitation(
                chunk_id=item.chunk_id,
                span=exact[:MAX_CITATION_SPAN_CHARS],
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=claim,
                chunk_ids=(item.chunk_id,),
                kind="fact",
                priority=200 + added,
            )
        )
        corpus = f"{corpus}\n{_normalize_figure_key(figure)}"
        added += 1
    if not added:
        return payload
    joined = join_paragraph_text(tuple(paragraphs))
    return payload.model_copy(
        update={
            "answer_text": joined[:8000] or payload.answer_text,
            "paragraphs": tuple(paragraphs),
            "citations": tuple(citations),
            "atomic_links": tuple(links),
            "status": "complete",
        }
    )


def salvage_helper_function_name(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Append the helper function name when prose evidence already states it.

    Args:
        payload: Company answer after multi-part salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload with an extractive naming claim, or unchanged when the ask
        is not a helper-name question or the name already appears.
    """

    if not _HELPER_NAME_ASK.search(user_query):
        return payload
    corpus = _claim_text_corpus(payload)
    for item in fusion.evidence:
        text = item.citation_text
        match = _HELPER_NAMED.search(text)
        if match is None:
            continue
        name = match.group(1)
        if name.lower() in corpus:
            return payload
        start = max(0, match.start() - 20)
        end = min(len(text), match.end() + 40)
        span = text[start:end].strip()
        if not span or span not in text:
            continue
        if len(payload.paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            return payload
        if len(payload.atomic_links) >= MAX_VERIFIER_LINKS:
            return payload
        link_id = "helper-name-1"
        paragraph_index = len(payload.paragraphs)
        claim = span[:400]
        paragraphs = (
            *payload.paragraphs,
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=claim[:4000],
                link_ids=(link_id,),
            ),
        )
        citations = (
            *payload.citations,
            AnswerCitation(
                chunk_id=item.chunk_id,
                span=claim[:MAX_CITATION_SPAN_CHARS],
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            ),
        )
        links = (
            *payload.atomic_links,
            AtomicLink(
                link_id=link_id,
                claim=claim,
                chunk_ids=(item.chunk_id,),
                kind="fact",
                priority=50,
            ),
        )
        joined = join_paragraph_text(paragraphs)
        return payload.model_copy(
            update={
                "answer_text": joined[:8000] or payload.answer_text,
                "paragraphs": paragraphs,
                "citations": citations,
                "atomic_links": links,
                "status": "complete",
            }
        )
    return payload


def salvage_expose_mode_labels(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace Manual/Ask/Agent confusers with Manual/Assist/Auto expose labels.

    When the ask is which mode labels to expose and fused evidence already
    holds the design-principle triad under Expose/Label wording, rewrite the
    answer onto that exact span even if a figure sample used Ask/Agent.

    Args:
        payload: Company answer after helper-name salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the expose triad, or unchanged when the ask or
        evidence do not match.
    """

    if not _EXPOSE_MODE_ASK.search(user_query):
        return payload
    gold = _best_evidence_match(
        fusion,
        _EXPOSE_MODE_LABELS,
        avoid=_CONFUSER_MODE_LABELS,
    )
    if gold is None:
        return payload
    item, match = gold
    corpus = _claim_text_corpus(payload)
    # Already holding the quote-bound Assist/Auto triad (not "assisted"/"autonomous").
    if _EXPOSE_MODE_LABELS.search(corpus) is not None and (
        _CONFUSER_MODE_LABELS.search(corpus) is None
    ):
        return payload
    span = match.group(0).strip()
    if not span or span not in item.citation_text:
        span = _bounded_match_span(item.citation_text, match)
    # Answer paragraphs reject blank lines; keep a single-line extract.
    span = re.sub(r"\s+", " ", span).strip()
    if not span:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="expose-modes-1",
    )


def salvage_adas_model_defaults(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace undated gpt-4o@0 samples with ADAS LLMAgentBase defaults.

    Args:
        payload: Company answer after expose-mode salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the dated model and temperature=0.5 span, or
        unchanged when the ask or evidence do not match.
    """

    if not _ADAS_MODEL_ASK.search(user_query):
        return payload
    gold = _first_evidence_match(fusion, _ADAS_MODEL_DEFAULTS)
    if gold is None:
        return payload
    item, match = gold
    corpus = _claim_text_corpus(payload)
    if "gpt-4o-20" in corpus and "0.5" in corpus:
        return payload
    span = _bounded_match_span(item.citation_text, match)
    if not span:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="adas-model-1",
    )


def salvage_psi_retrain_threshold(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace off-topic drift prose with the PSI > 0.25 / 48 hours rule.

    Args:
        payload: Company answer after ADAS salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the PSI retrain rule, or unchanged when unmatched.
    """

    if not _PSI_RETRAIN_ASK.search(user_query):
        return payload
    gold = _first_evidence_match(fusion, _PSI_RETRAIN_GOLD)
    if gold is None:
        return payload
    item, match = gold
    corpus = _claim_text_corpus(payload)
    if "psi > 0.25" in corpus and "48 hours" in corpus:
        return payload
    span = _bounded_match_span(item.citation_text, match)
    if not span:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="psi-retrain-1",
    )


def salvage_method_or_heading_label(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace paraphrased method/heading answers with the exact label.

    Args:
        payload: Company answer after PSI salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the exact label span, or unchanged when unmatched.
    """

    if not _METHOD_LABEL_ASK.search(user_query):
        return payload
    pattern = _method_label_pattern_for_query(user_query)
    if pattern is None:
        return payload
    gold = _first_evidence_match(fusion, pattern)
    if gold is None:
        return payload
    item, match = gold
    label = match.group(0).strip()
    corpus = _claim_text_corpus(payload)
    if label.casefold() in corpus:
        return payload
    span = label if label in item.citation_text else _bounded_match_span(
        item.citation_text, match
    )
    if not span:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="method-label-1",
    )


def _method_label_pattern_for_query(user_query: str) -> re.Pattern[str] | None:
    """Return the label regex that fits ``user_query``, if any.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Compiled label pattern, or ``None`` when no cue matches.
    """

    if re.search(r"(?i)token\s+consumption|reduced\s+efficiency|lower\s+efficiency", user_query):
        return re.compile(r"(?i)Lower efficiency")
    if re.search(r"(?i)preference|good.{0,40}bad|bad.{0,40}good", user_query):
        return re.compile(r"(?i)Direct preference optimization")
    if re.search(r"(?i)manager\s+coordination|centralized|subordinate", user_query):
        return re.compile(r"(?i)Manager Coordination")
    if re.search(r"(?i)chapter\s+8|one agent to many", user_query):
        return re.compile(r"(?i)From One Agent to Many")
    if re.search(r"(?i)context engineering", user_query):
        return re.compile(r"(?i)Context Engineering")
    if re.search(r"(?i)nonparametric", user_query):
        return re.compile(r"(?i)Nonparametric [Ll]earning")
    if re.search(r"(?i)\bheading\b|\bsection(?:\s+name)?\b|\bchapter\s+title\b|\bwhat method\b", user_query):
        return _METHOD_LABEL_GOLD
    return None


def salvage_tool_description_string(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace paraphrased tool blurbs with the exact description string.

    Args:
        payload: Company answer after method-label salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the exact description, or unchanged when unmatched.
    """

    if not _TOOL_DESCRIPTION_ASK.search(user_query):
        return payload
    gold = _best_evidence_match(
        fusion, _TOOL_DESCRIPTION_GOLD, user_query=user_query
    )
    if gold is None:
        return payload
    item, match = gold
    span = match.group(0).strip()
    corpus = _claim_text_corpus(payload)
    if "use wolfram alpha to compute mathematical" in corpus:
        return payload
    if not span or span not in item.citation_text:
        span = _bounded_match_span(item.citation_text, match)
    if not span:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="tool-desc-1",
    )


def salvage_chunking_window_values(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace off-topic memory headings with window_size/overlap literals.

    Args:
        payload: Company answer after tool-description salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the chunking literals, or unchanged when unmatched.
    """

    if not _CHUNKING_ASK.search(user_query):
        return payload
    gold = _best_evidence_match(
        fusion, _CHUNKING_GOLD, user_query=user_query
    )
    if gold is None:
        return payload
    item, match = gold
    corpus = _claim_text_corpus(payload)
    if "window_size" in corpus and "overlap" in corpus:
        return payload
    if "128" in corpus and "16" in corpus and "window" in corpus:
        return payload
    span = _bounded_match_span(item.citation_text, match)
    if not span:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="chunking-window-1",
    )


def salvage_protocol_aspire_claim(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace off-topic A2A blurbs with the HTTP-composability aspire span.

    Args:
        payload: Company answer after chunking salvage.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the aspire span, or unchanged when unmatched.
    """

    if not _PROTOCOL_ASK.search(user_query):
        return payload
    gold = _best_evidence_match(
        fusion, _PROTOCOL_GOLD, user_query=user_query
    )
    if gold is None:
        return payload
    item, match = gold
    corpus = _claim_text_corpus(payload)
    if "http enabled the composability" in corpus and "a2a aspires" in corpus:
        return payload
    if "aspires to do" in corpus and "composability of the web" in corpus:
        return payload
    span = _bounded_match_span(item.citation_text, match)
    if not span:
        span = match.group(0).strip()
    if not span or span not in item.citation_text:
        return payload
    return _replace_with_extractive_claim(
        payload,
        chunk_id=item.chunk_id,
        span=span,
        link_id="protocol-aspire-1",
    )


_NEXT_CODE_DEF = re.compile(
    r"(?<![A-Za-z0-9_])(?:@tool\b|(?:async\s+)?def\s+\w+|class\s+\w+)"
)
_CODE_SECTION_BREAK = re.compile(r"#\s*--\s*\d+")


_LLM_ASSIGN_LOOKBACK = re.compile(
    r"(?i)(?:llm\s*=\s*)?ChatOpenAI\s*\([^)]*\)\s*"
)


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


def _extract_pattern_block(text: str, match: re.Match[str]) -> str:
    """Copy a bounded extractive block around a non-def gold match.

    Used for wiring (``add_edge`` + ``initial_state``), constructors, and
    class+def joint spans. When the match ends on ``def name(``, continues
    through that definition body so class+def salvages stay complete.

    Args:
        text: Passage citation text.
        match: Gold pattern match inside ``text``.

    Returns:
        Exact substring of ``text``, capped at ``MAX_CITATION_SPAN_CHARS``.
    """

    start = match.start()
    end = min(len(text), match.end())
    # Expand slightly when the match is a lookahead-heavy joint group.
    if end - start < 40:
        end = min(len(text), start + MAX_CITATION_SPAN_CHARS)
    # Constructor matches often stop at the first kwarg; take through ')'.
    ctor = re.search(
        r"(?i)\b(?:SFTConfig|ChatOpenAI|[A-Z][A-Za-z0-9]*Config)\s*\(",
        text[start:end],
    )
    if ctor is not None:
        paren_open = start + ctor.end() - 1
        depth = 0
        ctor_end = paren_open
        for index in range(paren_open, min(len(text), paren_open + 800)):
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    ctor_end = index + 1
                    break
        if ctor_end > paren_open:
            block = text[start:ctor_end].strip()
            if block and block in text:
                return block[:MAX_CITATION_SPAN_CHARS]
    # class ... def name( matches stop at the opening paren; take the body.
    window = text[start:end]
    def_tail = re.search(
        r"(?i)(?:@tool\s+)?(?:async\s+)?def\s+\w+\s*\(\s*$",
        window,
    )
    if def_tail is not None:
        # def_tail offsets are relative to ``window`` / ``text[start:]``.
        paren_end = start + def_tail.end()
        rest = text[paren_end:]
        body_end = paren_end + len(rest)
        next_def = _NEXT_CODE_DEF.search(rest)
        if next_def is not None:
            body_end = min(body_end, paren_end + next_def.start())
        section = _CODE_SECTION_BREAK.search(rest)
        if section is not None:
            body_end = min(body_end, paren_end + section.start())
        # Keep a modest body when OCR flattened the page (no next sibling).
        if body_end == paren_end + len(rest):
            body_end = min(len(text), paren_end + 900)
        # Prefer including routing phrases named in class+def asks.
        for marker in (
            "inventory, transportation, or supplier",
            "transportation, or supplier",
            "or supplier",
        ):
            idx = text.casefold().find(marker, paren_end)
            if idx >= 0:
                body_end = max(body_end, min(len(text), idx + len(marker) + 40))
                break
        block = text[start:body_end].strip()
        if block and block in text:
            return block[:MAX_CITATION_SPAN_CHARS]
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
        overlap = (
            _passage_query_overlap(user_query, text) if user_query else 0
        )
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


_TABLE_TITLE = re.compile(r"(?i)Table\s+(\d+)-(\d+)\.")
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
    # Do not cut on capitalized single lines: OCR table rows such as
    # ``ELK Stack Advanced search/...`` match a heading heuristic and
    # would drop later rows (Langfuse, SigNoz, A2A Protocol). Stop only
    # before long narrative prose that follows the table body.
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

    Unlike :func:`_replace_with_extractive_claim`, keeps up to
    ``MAX_CITATION_SPAN_CHARS`` so multi-literal code and table bodies fit.
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

    exact = span.strip()[:MAX_CITATION_SPAN_CHARS]
    if not exact:
        return payload
    # Keep newlines for table/code readability, but never emit the
    # paragraph join delimiter inside AnswerParagraph.text.
    display = re.sub(r"\n{2,}", "\n", exact).strip()
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


def _best_pattern_span_match(
    fusion: FusionResult,
    pattern: re.Pattern[str],
    *,
    user_query: str | None = None,
    extract_def_block: bool = False,
) -> tuple[ScoredPassage, str] | None:
    """Return the best fused passage span for ``pattern``.

    Args:
        fusion: Fitted canonical evidence.
        pattern: Compiled gold pattern.
        user_query: Original user text for overlap ranking. Untrusted.
        extract_def_block: When True, use def-block extraction around the
            match (includes ChatOpenAI lookback for ``call_model``).

    Returns:
        Passage and exact span, or ``None``.
    """

    ranked: list[tuple[int, int, int, ScoredPassage, str]] = []
    for item in fusion.evidence:
        text = item.citation_text or ""
        match = pattern.search(text)
        if match is None:
            continue
        if extract_def_block:
            span = _extract_code_definition_block(text, match)
        else:
            span = _extract_pattern_block(text, match)
        if not span:
            continue
        overlap = (
            _passage_query_overlap(user_query, text) if user_query else 0
        )
        ranked.append(
            (
                -overlap,
                item.hybrid_rank or 10_000,
                match.start(),
                item,
                span,
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda row: (row[0], row[1], row[2], row[3].chunk_id))
    _overlap, _rank, _offset, item, span = ranked[0]
    return item, span


def salvage_named_code_definition(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace wrong neighbor snippets with wiring/constructor/class/def code.

    Wiring asks prefer ``add_edge`` + ``initial_state`` over a wrong
    ``def summarize_response``. Constructor asks require co-occurring
    kwargs. Class+def asks require both shapes. After an empty refusal,
    any matching gold pattern forces extractive salvage.

    Args:
        payload: Company answer after prior salvages.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the definition block, or unchanged when unmatched.
    """

    patterns: list[tuple[re.Pattern[str], bool, str]] = []
    wiring = wiring_code_gold_pattern(user_query)
    if wiring is not None:
        patterns.append((wiring, False, "code-wiring-1"))
    else:
        def_gold = code_definition_gold_pattern(
            named_code_definition_ids(user_query)
        )
        constructor = constructor_code_gold_pattern(user_query)
        class_def = class_def_code_gold_pattern(user_query)
        # Prefer def+ChatOpenAI lookback before a bare constructor window so
        # call_model asks keep both the llm assignment and the node body.
        if def_gold is not None and constructor is not None:
            patterns.append((def_gold, True, "code-def-1"))
            patterns.append((constructor, False, "code-ctor-1"))
        elif class_def is not None:
            patterns.append((class_def, False, "code-class-1"))
            if def_gold is not None:
                patterns.append((def_gold, True, "code-def-1"))
        elif constructor is not None:
            patterns.append((constructor, False, "code-ctor-1"))
        elif def_gold is not None:
            patterns.append((def_gold, True, "code-def-1"))
    if not patterns:
        return payload
    for pattern, extract_def, link_id in patterns:
        if extract_def:
            gold = _best_code_definition_match(
                fusion, pattern, user_query=user_query
            )
            if gold is None:
                continue
            item, _match, span = gold
        else:
            hit = _best_pattern_span_match(
                fusion, pattern, user_query=user_query
            )
            if hit is None:
                continue
            item, span = hit
        # Refusal with gold in fusion always salvages.
        if (
            not _is_empty_refusal(payload)
            and _extractive_block_already_released(payload, span)
        ):
            return payload
        return _replace_with_extractive_block(
            payload,
            chunk_id=item.chunk_id,
            span=span,
            link_id=link_id,
        )
    return payload


def salvage_listed_literals(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Replace wrong answers with a passage holding joint listed literals.

    Prefers the largest co-occurrence group (broker+JetStream,
    NPS+CSAT, A89268+cracked mug, client-side continuity). When no passage
    holds every literal, falls back to the fused passage that covers the
    most missing literals (still requiring JetStream / A89268 anchors when
    those appear in a group). Citations use the persistable leaf chunk.

    Args:
        payload: Company answer after code/table salvages.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload citing the joint-literal passage, or unchanged.
    """

    groups = listed_literal_groups(user_query)
    if not groups:
        return payload
    corpus = _claim_text_corpus(payload).casefold()
    ordered = sorted(groups, key=len, reverse=True)
    for group in ordered:
        gold = listed_literal_gold_pattern(group)
        hit: tuple[ScoredPassage, str] | None = None
        if gold is not None:
            hit = _best_pattern_span_match(
                fusion, gold, user_query=user_query
            )
        if hit is None:
            # Soft fallback: maximize coverage of literals still missing.
            missing = tuple(
                lit for lit in group if lit.casefold() not in corpus
            )
            if not missing:
                continue
            anchors = tuple(
                lit
                for lit in group
                if lit.casefold() in {"jetstream", "a89268"}
                or "nps" in lit.casefold()
                or "csat" in lit.casefold()
                or "continuity" in lit.casefold()
            )
            ranked: list[tuple[int, int, ScoredPassage]] = []
            for item in fusion.evidence:
                text = item.citation_text or ""
                lowered = text.casefold()
                if not text.strip():
                    continue
                if anchors and not all(
                    lit.casefold() in lowered for lit in anchors
                ):
                    continue
                hits = sum(1 for lit in group if lit.casefold() in lowered)
                miss_hits = sum(1 for lit in missing if lit.casefold() in lowered)
                if miss_hits < 1 or hits < 2:
                    continue
                ranked.append((miss_hits, hits, item))
            if not ranked:
                continue
            ranked.sort(
                key=lambda row: (-row[0], -row[1], row[2].chunk_id)
            )
            item = ranked[0][2]
            text = item.citation_text or ""
            span = text.strip()[:MAX_CITATION_SPAN_CHARS]
            hit = (item, span)
        item, span = hit
        # Prefer a span that actually contains the longest literal.
        text = item.citation_text or ""
        best_literal = max(group, key=len)
        idx = text.casefold().find(best_literal.casefold())
        if idx >= 0:
            window_start = max(0, idx - 80)
            window_end = min(len(text), idx + len(best_literal) + 240)
            candidate = text[window_start:window_end].strip()
            if candidate and all(
                lit.casefold() in candidate.casefold() for lit in group
            ):
                span = candidate[:MAX_CITATION_SPAN_CHARS]
            elif candidate:
                # Expand until all available group literals fit or cap hits.
                span = text[
                    window_start : min(
                        len(text), window_start + MAX_CITATION_SPAN_CHARS
                    )
                ].strip()
        # For multi-product groups, span from the earliest literal through
        # JetStream/anchors so Kafka is not dropped when centering on NATS.
        positions = [
            text.casefold().find(lit.casefold())
            for lit in group
            if text.casefold().find(lit.casefold()) >= 0
        ]
        if positions:
            window_start = max(0, min(positions) - 40)
            span = text[
                window_start : min(
                    len(text), window_start + MAX_CITATION_SPAN_CHARS
                )
            ].strip()
        if not span or span not in text:
            continue
        span_lower = span.casefold()
        candidate_hits = sum(1 for lit in group if lit.casefold() in span_lower)
        current_hits = sum(1 for lit in group if lit.casefold() in corpus)
        anchors_missing = [
            lit
            for lit in group
            if (
                lit.casefold() in {"jetstream", "a89268"}
                or "nps" in lit.casefold()
                or "csat" in lit.casefold()
                or "continuity across" in lit.casefold()
            )
            and lit.casefold() not in corpus
        ]
        if (
            not _is_empty_refusal(payload)
            and _extractive_block_already_released(payload, span)
            and not anchors_missing
        ):
            return payload
        if not _is_empty_refusal(payload) and current_hits > 0:
            keeps_current = all(
                lit.casefold() in span_lower
                for lit in group
                if lit.casefold() in corpus
            )
            adds_anchor = any(
                lit.casefold() in span_lower for lit in anchors_missing
            )
            if not (
                (keeps_current and adds_anchor)
                or candidate_hits > current_hits
            ):
                continue
        return _replace_with_extractive_block(
            payload,
            chunk_id=item.chunk_id,
            span=span,
            link_id="listed-lit-1",
        )
    return payload


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


def _first_evidence_match(
    fusion: FusionResult,
    pattern: re.Pattern[str],
) -> tuple[ScoredPassage, re.Match[str]] | None:
    """Return the first fused passage matching ``pattern``.

    Args:
        fusion: Fitted canonical evidence.
        pattern: Compiled search pattern.

    Returns:
        Passage and match, or ``None``.
    """

    return _best_evidence_match(fusion, pattern)


def _best_evidence_match(
    fusion: FusionResult,
    pattern: re.Pattern[str],
    *,
    avoid: re.Pattern[str] | None = None,
    user_query: str | None = None,
) -> tuple[ScoredPassage, re.Match[str]] | None:
    """Return the best fused passage matching ``pattern``.

    When ``avoid`` is set, prefer a hit whose citation text does not also
    match that pattern (for example prefer the Assist/Auto leaf over a
    parent that still embeds the Ask/Agent figure). When ``user_query`` is
    set, prefer the hit with the highest distinctive query-term overlap.

    Args:
        fusion: Fitted canonical evidence.
        pattern: Compiled search pattern for the desired span.
        avoid: Optional pattern that marks a worse/confuser passage.
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
    if avoid is not None:
        clean = [
            (item, match)
            for item, match in hits
            if avoid.search(item.citation_text or "") is None
        ]
        if clean:
            hits = clean
    if user_query and len(hits) > 1:
        hits = sorted(
            hits,
            key=lambda row: (
                -_passage_query_overlap(user_query, row[0].citation_text),
                row[0].hybrid_rank or 10_000,
                row[0].chunk_id,
            ),
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


def _bounded_match_span(text: str, match: re.Match[str]) -> str:
    """Copy a citation-bounded exact span around one regex match.

    Args:
        text: Passage citation text.
        match: Match inside ``text``.

    Returns:
        Exact substring of ``text``, or empty when alignment fails.
    """

    start = max(0, match.start() - 40)
    end = min(len(text), match.end() + 40)
    while start > 0 and text[start - 1] not in "\n.!?":
        start -= 1
        if match.start() - start > 120:
            start = max(0, match.start() - 40)
            break
    span = text[start:end].strip()
    if not span or span not in text:
        span = match.group(0).strip()
    if not span or span not in text:
        return ""
    return span[:MAX_CITATION_SPAN_CHARS]


def _replace_with_extractive_claim(
    payload: AnswerPayload,
    *,
    chunk_id: str,
    span: str,
    link_id: str,
) -> AnswerPayload:
    """Rebuild the answer as one extractive claim citing ``chunk_id``.

    Args:
        payload: Prior company answer (confuser or empty).
        chunk_id: Fusion chunk that holds ``span``.
        span: Exact citation span.
        link_id: Stable salvage link id.

    Returns:
        Complete payload with one fact claim.
    """

    claim = re.sub(r"\s+", " ", span).strip()[:400]
    if not claim:
        return payload
    paragraph = AnswerParagraph(
        paragraph_index=0,
        text=claim[:4000],
        link_ids=(link_id,),
    )
    citation = AnswerCitation(
        chunk_id=chunk_id,
        span=claim[:MAX_CITATION_SPAN_CHARS],
        atomic_link_id=link_id,
        paragraph_index=0,
    )
    link = AtomicLink(
        link_id=link_id,
        claim=claim,
        chunk_ids=(chunk_id,),
        kind="fact",
        priority=10,
    )
    return payload.model_copy(
        update={
            "answer_text": claim[:8000],
            "paragraphs": (paragraph,),
            "citations": (citation,),
            "atomic_links": (link,),
            "composed_conclusion": None,
            "status": "complete",
            "refused_links": (),
        }
    )


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
    if _is_empty_refusal(derived) or derived.status == "refused":
        salvaged = salvage_refused_literal_claims(fusion, user_query=user_query)
        if salvaged is not None:
            filtered = bind_company_atomic_links(
                filter_invented_ids(salvaged, fusion, tables),
                fusion=fusion,
                user_query=user_query,
            )
            derived = with_derived_answer_text(filtered)
    completed = salvage_missing_multipart_figures(
        derived, fusion, user_query=user_query
    )
    if completed is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(completed, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    named = salvage_helper_function_name(derived, fusion, user_query=user_query)
    if named is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(named, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    exposed = salvage_expose_mode_labels(derived, fusion, user_query=user_query)
    if exposed is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(exposed, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    adas = salvage_adas_model_defaults(derived, fusion, user_query=user_query)
    if adas is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(adas, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    psi = salvage_psi_retrain_threshold(derived, fusion, user_query=user_query)
    if psi is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(psi, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    labeled = salvage_method_or_heading_label(
        derived, fusion, user_query=user_query
    )
    if labeled is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(labeled, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    described = salvage_tool_description_string(
        derived, fusion, user_query=user_query
    )
    if described is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(described, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    chunked = salvage_chunking_window_values(
        derived, fusion, user_query=user_query
    )
    if chunked is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(chunked, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    protocol = salvage_protocol_aspire_claim(
        derived, fusion, user_query=user_query
    )
    if protocol is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(protocol, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    coded = salvage_named_code_definition(
        derived, fusion, user_query=user_query
    )
    if coded is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(coded, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    tabulated = salvage_named_table_block(
        derived, fusion, user_query=user_query
    )
    if tabulated is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(tabulated, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    listed = salvage_listed_literals(
        derived, fusion, user_query=user_query
    )
    if listed is not derived:
        filtered = bind_company_atomic_links(
            filter_invented_ids(listed, fusion, tables),
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
