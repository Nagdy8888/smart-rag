"""Repair clearly misplaced prose citations before normal semantic verification."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult

_STOP = frozenset(
    "the agent agents system component information can and of to in for on with is are it its that this including allowing from through own as by which be or an between does when used using more than has have into their them same some other one".split()
)


def _unique_phrase_window(
    claim: str, fusion: FusionResult, *, current: float
) -> tuple[float, str, str] | None:
    """Find one unique long verbatim anchor before the unchanged semantic verifier.

    Lexical coverage alone cannot repair a paraphrase. This fallback additionally
    requires a five-word literal with three content words in exactly one fitted
    prose passage. It never changes the claim or authorizes an absent source.
    """
    words = _terms(claim)
    tokens = re.findall(r"[A-Za-z]+", claim)
    choices: dict[str, tuple[float, str, str]] = {}
    examined: set[str] = set()
    for offset in range(len(tokens) - 4):
        phrase = tokens[offset : offset + 5]
        if len(_terms(" ".join(phrase))) < 3:
            continue
        key = " ".join(phrase).casefold()
        if key in examined:
            continue
        if len(examined) >= 32:
            break
        examined.add(key)
        pattern = re.compile(
            r"\b" + r"\s+".join(re.escape(x) for x in phrase) + r"\b", re.IGNORECASE
        )
        holders = [
            (source, match)
            for source in fusion.evidence
            if source.content_kind is None
            and (match := pattern.search(source.citation_text)) is not None
        ]
        if len(holders) != 1:
            continue
        source, match = holders[0]
        score = len(words & _terms(source.citation_text)) / max(1, len(words))
        if score < 0.5 or score < current + 0.25:
            continue
        # Keep the literal and its surrounding statement, as an exact slice.
        start = max(0, match.start() - 350)
        span = source.citation_text[start : start + 1000].strip()
        choices[source.chunk_id] = (score, source.chunk_id, span)
    if len(choices) != 1:
        return None
    return next(iter(choices.values()))


def _terms(text: str) -> frozenset[str]:
    """Use content words only; identifiers and very short claims keep existing binding."""
    return frozenset(
        word for word in re.findall(r"[a-z]{3,}", text.casefold()) if word not in _STOP
    )


def rebind_high_coverage_prose(
    payload: AnswerPayload, fusion: FusionResult
) -> AnswerPayload:
    """Move a low-overlap citation only to a much stronger exact canonical window.

    Text and support votes stay unchanged. The ordinary verifier must still
    reject reversed predicates, invented facts, and misleading paraphrases.
    """
    by_id = {source.chunk_id: source for source in fusion.evidence}
    links = list(payload.atomic_links)
    citations = list(payload.citations)
    changed = False
    for index, link in enumerate(links):
        words = _terms(link.claim)
        if (
            link.kind != "fact"
            or len(words) < 6
            or "```" in link.claim
            or re.search(r"(?m)^\s*(?:def |class |\|)", link.claim)
        ):
            continue
        current = max(
            (
                len(words & _terms(by_id[ident].citation_text)) / len(words)
                for ident in link.chunk_ids
                if ident in by_id
            ),
            default=0.0,
        )
        if current >= 0.5:
            continue
        best: tuple[float, str, str] | None = None
        for source in fusion.evidence:
            if source.content_kind in {"code", "table", "figure"}:
                continue
            text = source.citation_text
            starts = [
                0,
                *(match.end() for match in re.finditer(r"(?<=[.!?])\s+|\n\s*\n", text)),
            ]
            for start in starts:
                span = text[start : start + 1000].strip()
                score = len(words & _terms(span)) / len(words)
                if (
                    score >= 0.75
                    and score >= current + 0.30
                    and (best is None or score > best[0])
                ):
                    best = (score, source.chunk_id, span)
        if best is None:
            best = _unique_phrase_window(link.claim, fusion, current=current)
        if best is None:
            continue
        _, chunk_id, span = best
        paragraph_index = next(
            (
                p.paragraph_index
                for p in payload.paragraphs
                if link.link_id in p.link_ids
            ),
            0,
        )
        retained = [c for c in citations if c.atomic_link_id != link.link_id]
        if len(retained) >= 12:
            continue
        citations = [
            *retained,
            AnswerCitation(
                chunk_id=chunk_id,
                span=span,
                atomic_link_id=link.link_id,
                paragraph_index=paragraph_index,
            ),
        ]
        links[index] = link.model_copy(update={"chunk_ids": (chunk_id,)})
        changed = True
    return (
        payload.model_copy(
            update={"atomic_links": tuple(links), "citations": tuple(citations)}
        )
        if changed
        else payload
    )
