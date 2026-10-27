"""Conservative conflicts for explicit scoped numeric policy fields only."""

from __future__ import annotations

import re
from decimal import Decimal

from smart_rag_core.knowledge import AuthorityStatus, DocumentGovernance
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

_SCOPE = re.compile(
    r"^(?:scope|applicability|النطاق)\s*:\s*([^\n]{1,120})$", re.M | re.I
)
_FIELD = re.compile(
    r"^([^\n:]{3,80}):\s*(\d+(?:\.\d+)?)\s+(days?|hours?|USD|EUR|EGP|أيام|يوم|ساعة|ساعات)\.?\s*$",
    re.M | re.I,
)


def explicit_policy_conflict(
    fusion: FusionResult, records: dict[str, DocumentGovernance]
) -> AnswerPayload | None:
    """Quote disagreements only when approval, area, scope, field, and unit match.

    This is deliberately not a general contradiction detector. Missing scope,
    different audiences, prose implications, and different units do not qualify.
    """
    seen: dict[tuple[str, str, str, str], tuple[str, str, Decimal, str]] = {}
    for passage in fusion.evidence:
        record = records.get(passage.document_id)
        if (
            record is None
            or record.authority_status is not AuthorityStatus.APPROVED
            or not record.knowledge_area
        ):
            continue
        scope = _SCOPE.search(passage.citation_text)
        if scope is None:
            continue
        for field in _FIELD.finditer(passage.citation_text):
            key = (
                record.knowledge_area.casefold(),
                scope[1].strip().casefold(),
                field[1].strip().casefold(),
                field[3].casefold(),
            )
            value = Decimal(field[2])
            previous = seen.get(key)
            if previous and previous[0] != passage.document_id and previous[2] != value:
                sources = (
                    (previous[1], previous[3]),
                    (passage.chunk_id, field[0].strip()),
                )
                links = tuple(
                    AtomicLink(
                        link_id=f"policy-conflict-{i}", claim=text, chunk_ids=(chunk,)
                    )
                    for i, (chunk, text) in enumerate(sources)
                )
                return AnswerPayload(
                    answer_text="\n\n".join(text for _, text in sources),
                    answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
                    paragraphs=tuple(
                        AnswerParagraph(
                            paragraph_index=i, text=text, link_ids=(links[i].link_id,)
                        )
                        for i, (_, text) in enumerate(sources)
                    ),
                    atomic_links=links,
                    citations=tuple(
                        AnswerCitation(
                            chunk_id=chunk,
                            span=text,
                            atomic_link_id=links[i].link_id,
                            paragraph_index=i,
                        )
                        for i, (chunk, text) in enumerate(sources)
                    ),
                )
            seen[key] = (passage.document_id, passage.chunk_id, value, field[0].strip())
    return None
