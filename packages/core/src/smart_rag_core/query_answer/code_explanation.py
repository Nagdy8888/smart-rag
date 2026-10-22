"""Retain cited explanations when replacing a requested source-code block."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_fusion.models import FusionResult


def with_source_code_explanation(
    payload: AnswerPayload, fusion: FusionResult, *, query: str
) -> AnswerPayload:
    """Supply an exact introductory source paragraph when a code explanation is absent."""
    if not re.search(r"(?i)\b(?:explain|describe)\b", query):
        return payload
    if any(not re.search(r"(?m)^\s*(?:def |```)", p.text) for p in payload.paragraphs):
        return payload
    names = re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\b", query)
    if len(names) != 1 or not payload.citations or len(payload.atomic_links) >= 6:
        return payload
    terms = set(names[0].split("_")) - {
        "construct",
        "build",
        "create",
        "get",
        "graph",
        "node",
    }
    if len(terms) < 2:
        return payload
    cited = {c.chunk_id for c in payload.citations}
    versions = {
        (s.document_id, s.version_id) for s in fusion.evidence if s.chunk_id in cited
    }
    signature = re.compile(rf"(?m)^\s*def\s+{re.escape(names[0])}\(")
    for source in fusion.evidence:
        match = signature.search(source.citation_text)
        if match is None or (source.document_id, source.version_id) not in versions:
            continue
        for paragraph in source.citation_text[: match.start()].split("\n\n"):
            paragraph = paragraph.strip()
            if not 100 <= len(paragraph) <= 900 or re.search(
                r"(?m)^\s*(?:def |#|class |\d+\s*\|)", paragraph
            ):
                continue
            words = set(re.findall(r"[a-z]+", paragraph.casefold()))
            if not terms.issubset(words):
                continue
            index = len(payload.paragraphs)
            if index >= 6 or len(payload.citations) >= 12:
                return payload
            link_id = "code-source-explanation"
            if any(link.link_id == link_id for link in payload.atomic_links):
                return payload
            return with_derived_answer_text(
                payload.model_copy(
                    update={
                        "paragraphs": (
                            *payload.paragraphs,
                            AnswerParagraph(
                                paragraph_index=index,
                                text=paragraph,
                                link_ids=(link_id,),
                            ),
                        ),
                        "atomic_links": (
                            *payload.atomic_links,
                            AtomicLink(
                                link_id=link_id,
                                claim=paragraph,
                                chunk_ids=(source.chunk_id,),
                                kind="fact",
                                priority=11,
                            ),
                        ),
                        "citations": (
                            *payload.citations,
                            AnswerCitation(
                                chunk_id=source.chunk_id,
                                span=paragraph,
                                atomic_link_id=link_id,
                                paragraph_index=index,
                            ),
                        ),
                    }
                )
            )
    return payload


def keep_code_explanation(
    original: AnswerPayload, replacement: AnswerPayload, *, query: str
) -> AnswerPayload:
    """Copy bounded existing prose and its ownership, never unchecked new prose.

    The normal binder/verifier still checks a pre-verification replacement.
    After verification, only already surviving paragraphs are available here.
    Source code, citations and explanation text are never rewritten.
    """
    if replacement is original or not re.search(
        r"(?i)\b(?:explain|describe|how|why)\b|اشرح", query
    ):
        return replacement
    paragraphs = list(replacement.paragraphs)
    links = list(replacement.atomic_links)
    citations = list(replacement.citations)
    table_citations = list(replacement.table_citations)
    existing_ids = {link.link_id for link in links}
    omitted = False
    by_id = {link.link_id: link for link in original.atomic_links}
    for paragraph in original.paragraphs:
        prose = re.sub(r"```[^\n]*\n.*?```", "", paragraph.text, flags=re.S).strip()
        mixed = prose != paragraph.text
        if not prose:
            continue
        if re.search(r"(?m)```|^\s*(?:@\w+|(?:async\s+)?def\s|class\s)", prose):
            continue
        ids = set(paragraph.link_ids)
        if not ids.issubset(by_id) or (ids & existing_ids and not mixed):
            continue
        owned = [
            c
            for c in original.citations
            if c.paragraph_index == paragraph.paragraph_index
        ]
        owned_tables = [
            c
            for c in original.table_citations
            if c.paragraph_index == paragraph.paragraph_index
        ]
        if not owned and not owned_tables:
            continue
        if (
            len(paragraphs) >= 6
            or len(links) + len(ids) > 6
            or len(citations) + len(table_citations) + len(owned) + len(owned_tables)
            > 12
            or sum(len(p.text) + 2 for p in paragraphs) + len(paragraph.text) > 8000
        ):
            omitted = True
            continue
        index = len(paragraphs)
        if mixed:
            # A mixed code/prose claim becomes one source-owned prose claim.
            # Multi-link paragraphs are kept fail-closed rather than guessing
            # which old claim supports which outside-fence words.
            if len(ids) != 1:
                continue
            new_id = f"code-prose-{index}"
            if new_id in existing_ids or new_id in by_id:
                continue
            old_id = paragraph.link_ids[0]
            by_id[new_id] = by_id[old_id].model_copy(
                update={"link_id": new_id, "claim": prose}
            )
            paragraph = paragraph.model_copy(
                update={"text": prose, "link_ids": (new_id,)}
            )
            owned = [c.model_copy(update={"atomic_link_id": new_id}) for c in owned]
            owned_tables = [
                c.model_copy(update={"atomic_link_id": new_id}) for c in owned_tables
            ]
            ids = {new_id}
        paragraphs.append(paragraph.model_copy(update={"paragraph_index": index}))
        priority = min(10_000, max((link.priority for link in links), default=0) + 1)
        links.extend(
            by_id[link_id].model_copy(update={"priority": priority})
            for link_id in paragraph.link_ids
        )
        citations.extend(c.model_copy(update={"paragraph_index": index}) for c in owned)
        table_citations.extend(
            c.model_copy(update={"paragraph_index": index}) for c in owned_tables
        )
        existing_ids.update(ids)
    return with_derived_answer_text(
        replacement.model_copy(
            update={
                "paragraphs": tuple(paragraphs),
                "atomic_links": tuple(links),
                "citations": tuple(citations),
                "table_citations": tuple(table_citations),
                "status": "partial" if omitted else replacement.status,
            }
        )
    )
