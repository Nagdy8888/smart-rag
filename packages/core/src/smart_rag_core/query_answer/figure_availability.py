"""Reject image-unavailable claims contradicted by authorized figure metadata."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult

_UNAVAILABLE = re.compile(
    r"(?i)\b(?:i|we)\s+(?:cannot|can['\u2019]t|am unable to|are unable to)\s+"
    r"(?:include|show|provide|display)\b[^.!?\n]{0,100}\b(?:image|figure|diagram)\b"
    r"|لا\s+(?:أستطيع|يمكنني|يمكننا)\s+[^.!؟\n]{0,100}(?:الصورة|الشكل)"
)


def unavailable_figure_links(
    payload: AnswerPayload, fusion: FusionResult
) -> frozenset[str]:
    """Return claims denying an image that their own authorized citation provides.

    Unrelated figures, prose-only evidence and missing figure IDs cannot trigger
    this check. It removes claims before verification and never rewrites prose.
    """
    available = {
        item.chunk_id
        for item in fusion.evidence
        if item.content_kind == "figure" and item.figure_id
    }
    return frozenset(
        link.link_id
        for link in payload.atomic_links
        if available.intersection(link.chunk_ids) and _UNAVAILABLE.search(link.claim)
    )
