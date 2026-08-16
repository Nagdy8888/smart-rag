"""Prose passage splitting with bounded overlap."""

from __future__ import annotations

from dataclasses import dataclass

from smart_rag_core.ingestion.chunking import tokenizer
from smart_rag_core.ingestion.chunking.limits import (
    PASSAGE_HARD_MAX_TOKENS,
    PASSAGE_OVERLAP_MAX_TOKENS,
    PASSAGE_OVERLAP_MIN_TOKENS,
    PASSAGE_TARGET_MAX_TOKENS,
)
from smart_rag_core.ingestion.parser.types import TypedElement


@dataclass(frozen=True, slots=True)
class ProseSegment:
    """One unsplit prose segment with source elements."""

    text: str
    element_ids: tuple[str, ...]
    locators: tuple[dict[str, object], ...]


def split_prose_segments(
    segments: list[ProseSegment],
    *,
    overlap_tokens: int = 50,
) -> list[ProseSegment]:
    """Split prose segments into bounded passages with adjacent overlap.

    Args:
        segments: Ordered prose segments from one section.
        overlap_tokens: Target overlap between adjacent sibling passages.

    Returns:
        Passage segments respecting hard caps and overlap bounds.
    """

    if not segments:
        return []
    merged_text = "\n\n".join(segment.text for segment in segments)
    merged_ids = tuple(
        element_id for segment in segments for element_id in segment.element_ids
    )
    merged_locators = tuple(
        locator for segment in segments for locator in segment.locators
    )
    token_count = tokenizer.count_tokens(merged_text)
    if token_count <= PASSAGE_TARGET_MAX_TOKENS:
        return [
            ProseSegment(
                text=merged_text,
                element_ids=merged_ids,
                locators=merged_locators,
            )
        ]
    if token_count <= PASSAGE_HARD_MAX_TOKENS:
        return [
            ProseSegment(
                text=merged_text,
                element_ids=merged_ids,
                locators=merged_locators,
            )
        ]

    passages: list[ProseSegment] = []
    current_parts: list[str] = []
    current_ids: list[str] = []
    current_locators: list[dict[str, object]] = []

    def flush() -> None:
        """Append the current token-bounded passage and leave buffers to the caller."""

        if not current_parts:
            return
        passages.append(
            ProseSegment(
                text="\n\n".join(current_parts),
                element_ids=tuple(current_ids),
                locators=tuple(current_locators),
            )
        )

    for segment in segments:
        candidate_parts = [*current_parts, segment.text]
        candidate_text = "\n\n".join(candidate_parts)
        if (
            current_parts
            and tokenizer.count_tokens(candidate_text) > PASSAGE_TARGET_MAX_TOKENS
        ):
            flush()
            current_parts = []
            current_ids = []
            current_locators = []
        current_parts.append(segment.text)
        current_ids.extend(segment.element_ids)
        current_locators.extend(segment.locators)

    flush()

    if len(passages) <= 1:
        return passages

    overlap = max(
        PASSAGE_OVERLAP_MIN_TOKENS,
        min(PASSAGE_OVERLAP_MAX_TOKENS, overlap_tokens),
    )
    overlapped: list[ProseSegment] = []
    previous_text = ""
    for index, passage in enumerate(passages):
        text = passage.text
        if index > 0 and overlap > 0:
            prefix = tokenizer.tail_tokens(previous_text, overlap)
            if prefix:
                text = f"{prefix}\n\n{text}"
        overlapped.append(
            ProseSegment(
                text=text,
                element_ids=passage.element_ids,
                locators=passage.locators,
            )
        )
        previous_text = passage.text
    return overlapped


def split_oversized_atomic(
    text: str, *, hard_max: int = PASSAGE_HARD_MAX_TOKENS
) -> list[str]:
    """Split one oversized atomic element into reconstructable fragments.

    Args:
        text: Atomic element text.
        hard_max: Hard token ceiling per fragment.

    Returns:
        Ordered fragments preserving sentence boundaries where possible.
    """

    if tokenizer.count_tokens(text) <= hard_max:
        return [text]
    lines = text.splitlines() or [text]
    fragments: list[str] = []
    current: list[str] = []
    for line in lines:
        candidate = "\n".join([*current, line]) if current else line
        if current and tokenizer.count_tokens(candidate) > hard_max:
            fragments.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        joined = "\n".join(current)
        if tokenizer.count_tokens(joined) > hard_max:
            fragments.extend(_split_by_tokens(joined, hard_max))
        else:
            fragments.append(joined)
    return fragments or [tokenizer.truncate_to_tokens(text, hard_max)]


def _split_by_tokens(text: str, hard_max: int) -> list[str]:
    """Split text by token windows when line boundaries are insufficient."""

    tokens = text.split()
    parts: list[str] = []
    current: list[str] = []
    for token in tokens:
        candidate = " ".join([*current, token])
        if current and tokenizer.count_tokens(candidate) > hard_max:
            parts.append(" ".join(current))
            current = [token]
        else:
            current.append(token)
    if current:
        parts.append(" ".join(current))
    return parts


def is_ordinary_prose(element: TypedElement) -> bool:
    """Return whether an element contributes to ordinary prose sizing metrics."""

    return element.kind.value in {"paragraph", "heading", "link"}
