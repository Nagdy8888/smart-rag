"""Select requested or actually cited native artifacts from canonical evidence."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.retrieval.rerank import named_code_definition_ids

_LABEL = re.compile(
    r"(?i)(figure|fig\.?|table|شكل|الشكل|جدول|الجدول)\s*(\d+)\s*[-\u2013]\s*(\d+)"
)
_CAPTION = re.compile(r"(?im)^\s*(figure|table)\s+(\d+)\s*[-\u2013]\s*(\d+)\.")


def requested_artifact_labels(query: str, kind: str) -> frozenset[tuple[str, str]]:
    """Extract exact numbered table/figure requests, including Arabic labels.

    Args:
        query: Original user question.
        kind: ``table`` or ``figure``.

    Returns:
        Normalized chapter/item number pairs.
    """
    table_words = {"table", "جدول", "الجدول"}
    return frozenset(
        (str(int(match[2])), str(int(match[3])))
        for match in _LABEL.finditer(query)
        if (match[1].casefold() in table_words) == (kind == "table")
    )


def relevant_native_fusion(
    payload: AnswerPayload, fusion: FusionResult, query: str
) -> FusionResult:
    """Keep exact requested artifacts or native chunks used by checked claims.

    A caption-only source may identify a native table on the same or next PDF
    page in the same canonical version. Similar section words alone are not a
    match. Named code is handled by definition extraction, never a whole unrelated
    listing appended after checking.

    Args:
        payload: Checked claims and citation ownership.
        fusion: Authorized fitted canonical sources.
        query: Original question.

    Returns:
        A filtered copy; no source text, rank, or authorization is changed.
    """
    used = {citation.chunk_id for citation in payload.citations}
    used.update(chunk for link in payload.atomic_links for chunk in link.chunk_ids)
    named_code = named_code_definition_ids(query)
    labels = {
        kind: requested_artifact_labels(query, kind) for kind in ("table", "figure")
    }
    # A response can introduce a numbered diagram even when the user did not
    # explicitly request one. Resolve that exact label against canonical assets;
    # a broad topical overlap never selects an image. Explicit requests retain
    # their existing priority over other retrieved figures.
    answer_figures = requested_artifact_labels(payload.answer_text, "figure")

    def requested(item: ScoredPassage) -> bool:
        """Use a caption at the artifact, or a bounded preceding table caption."""
        kind = item.content_kind or ""
        targets = labels.get(kind, frozenset())
        if kind == "figure" and not targets:
            targets = answer_figures
        own = {
            (str(int(m[2])), str(int(m[3])))
            for m in _CAPTION.finditer(item.citation_text)
            if m[1].casefold() == kind
        }
        if own:
            return bool(own & targets)
        if kind != "table" or item.page_number is None:
            return False
        for source in fusion.evidence:
            if (
                source.version_id != item.version_id
                or source.page_number is None
                or not 0 <= item.page_number - source.page_number <= 1
            ):
                continue
            source_labels = {
                (str(int(m[2])), str(int(m[3])))
                for m in _CAPTION.finditer(source.citation_text)
                if m[1].casefold() == kind
            }
            if source_labels & targets:
                return True
        return False

    selected: list[ScoredPassage] = []
    for item in fusion.evidence:
        kind = item.content_kind
        if kind not in {"code", "table", "figure"}:
            selected.append(item)
        elif kind == "figure" and not labels["figure"] and answer_figures:
            if requested(item):
                selected.append(item)
        elif (labels["table"] or labels["figure"]) and not labels.get(kind or ""):
            continue
        elif kind == "code" and named_code:
            continue
        elif labels.get(kind or ""):
            if requested(item):
                selected.append(item)
        elif item.chunk_id in used:
            selected.append(item)
    return fusion.model_copy(update={"evidence": tuple(selected)})
