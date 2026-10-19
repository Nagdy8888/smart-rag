"""Rewrite a verified multi-part company answer into one titled piece."""

from __future__ import annotations

import re
from typing import cast

from pydantic import ValidationError
from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerParagraph, AnswerPayload
from smart_rag_core.query_answer.native_blocks import insert_useful_figures
from smart_rag_core.query_answer.release import company_release_applies
from smart_rag_core.query_fusion.models import FusionResult

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.organize import gateway_organize
from smart_rag_agents.query.nodes.shared import runtime_from_state, skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState

_SENTENCE_SPLIT = re.compile(r"(?<=[A-Za-z0-9]{3}[.!?])\s+(?=[A-Z])")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9']*")
_FUNCTION_WORDS = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "they",
        "them",
        "then",
        "than",
        "into",
        "over",
        "also",
        "only",
        "when",
        "where",
        "which",
        "while",
        "have",
        "been",
        "were",
        "each",
        "such",
        "these",
        "those",
        "their",
        "there",
        "about",
        "after",
        "before",
        "under",
        "between",
        "through",
        "does",
        "following",
        "without",
        "during",
        "within",
        "using",
        "based",
        "across",
        "because",
        "still",
        "just",
        "even",
        "more",
        "most",
        "some",
        "many",
        "other",
        "same",
        "both",
    }
)
_TITLE_LINE = re.compile(r"(?m)^\s*\*\*[^*]+\*\*\s*$")
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_DEF_LISTING = re.compile(r"(?m)^\s*(?:async\s+)?def\s+\w+\s*\(")
_FIGURE_MARK = re.compile(r"\[\[figure:[0-9a-fA-F-]{1,64}\]\]")
_MAX_PARAGRAPHS = 6


def organize_answer_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Rewrite verified company prose after citation checks have finished.

    State inputs:
        ``answer``, ``status``, ``user_query``, ``remaining_model_calls``,
        token totals.

    State outputs:
        ``answer`` with rewritten ``answer_text`` when the rewrite is
        grounded. Otherwise the verified answer is unchanged.
        ``remaining_model_calls`` decrements only when a call starts.

    Persistence writes:
        None. Citations were stored by ``verify_answer``.

    External/model calls:
        Zero, or one organize call. An answer that is only code, only a
        table, one sentence, general, web, or a refusal makes no call.
        A figure the question or the answer uses is attached without a call.

    Budget/deadline behavior:
        A missing gateway, exhausted call count, or provider failure
        keeps the verified text.

    Failure/fallback route:
        A rejected rewrite is replaced by a local title and bullet list
        of the verified sentences. Exact tables, code, and figures stay.
        A fence line is not used as that title.
        Any other exception keeps that local layout and does not abort.

    Args:
        state: State after verification.
        deps: Gateway and organize prompt.

    Returns:
        State whose visible answer is the rewrite or the verified text.
    """

    if skip_closed_nodes(state):
        return state
    raw_answer = state.get("answer")
    if not isinstance(raw_answer, dict):
        return state
    try:
        payload = AnswerPayload.model_validate(raw_answer)
    except ValidationError:
        return state
    status = str(state.get("status") or "")
    query = str(state.get("user_query") or "")
    prose, exact_blocks = _split_exact_blocks(payload.answer_text)
    updated: AnswerPayload | None = None
    prompt_tokens = 0
    completion_tokens = 0
    remaining = int(state.get("remaining_model_calls") or 0)
    spent = False
    if _should_organize(payload, status, prose) and deps.model_gateway is not None:
        if deps.organize_prompt_text:
            try:
                remaining = assert_call_available(remaining)
            except QueryCeilingError:
                remaining = int(state.get("remaining_model_calls") or 0)
            else:
                spent = True
                try:
                    rewritten, prompt_tokens, completion_tokens = gateway_organize(
                        deps,
                        query=query,
                        verified_text=prose,
                        context=runtime_from_state(state),
                    )
                    updated = _apply_rewrite(payload, rewritten, prose, exact_blocks)
                except (
                    AnswerError,
                    QueryCeilingError,
                    ValidationError,
                    ValueError,
                    TimeoutError,
                ):
                    updated = None
                    prompt_tokens = 0
                    completion_tokens = 0
                except Exception:
                    updated = None
                    prompt_tokens = 0
                    completion_tokens = 0
    released = updated if updated is not None else payload
    if updated is None and _should_organize(payload, status, prose):
        local = _format_verified_layout(payload, prose, exact_blocks)
        if local is not None:
            released = local
    released = _attach_figures(released, state, query)
    if not spent and released is payload:
        return state
    answer_dump = released.model_dump(mode="json")
    return cast(
        QueryGraphState,
        {
            **state,
            "answer": answer_dump,
            "remaining_model_calls": remaining,
            "prompt_tokens": int(state.get("prompt_tokens") or 0) + prompt_tokens,
            "completion_tokens": int(state.get("completion_tokens") or 0)
            + completion_tokens,
        },
    )


def _should_organize(payload: AnswerPayload, status: str, prose: str) -> bool:
    """Return whether the prose part of this answer should be rewritten.

    Args:
        payload: Verified answer.
        status: Graph status after verification.
        prose: Verified text with code fences, pipe tables, and figure
            marks removed.

    Returns:
        True for multi-part company prose that is verified or partial.
        An answer that is only a table or only code stays exact.
    """

    if status not in {"verified", "verified_partial"}:
        return False
    if not company_release_applies(payload, is_web=False):
        return False
    text = prose.strip()
    if not text or _is_pipe_table(text):
        return False
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    if len(parts) > 1:
        return True
    return len(_SENTENCE_SPLIT.split(text)) >= 2


def _split_exact_blocks(text: str) -> tuple[str, tuple[str, ...]]:
    """Separate prose from fences, pipe tables, and figure marks.

    Args:
        text: Verified answer text.

    Returns:
        Prose sent to the rewrite, and the exact blocks in encounter order.
    """

    blocks: list[str] = []

    def _keep_fence(match: re.Match[str]) -> str:
        blocks.append(match.group(0).strip())
        return "\n"

    without_fences = _FENCE.sub(_keep_fence, text)
    lines = without_fences.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if _table_row(lines[index]):
            start = index
            while index < len(lines) and _table_row(lines[index]):
                index += 1
            block = "\n".join(lines[start:index]).strip()
            if _is_pipe_table(block):
                blocks.append(block)
            else:
                kept.extend(lines[start:index])
            continue
        kept.append(lines[index])
        index += 1
    prose = "\n".join(kept)

    def _keep_figure(match: re.Match[str]) -> str:
        blocks.append(match.group(0))
        return ""

    prose = _FIGURE_MARK.sub(_keep_figure, prose)
    prose = _peel_unclosed_fence(prose, blocks)
    prose = re.sub(r"\n{2,}", "\n", prose).strip()
    return prose, tuple(blocks)


def _peel_unclosed_fence(prose: str, blocks: list[str]) -> str:
    """Move a trailing fence that never closes into the exact blocks.

    Args:
        prose: Text after closed fences, tables, and figure marks are gone.
        blocks: Exact blocks collected so far. A trailing fence is appended.

    Returns:
        Prose before the first remaining fence marker.
    """

    marker = prose.find("```")
    if marker < 0:
        return prose
    fence = prose[marker:].strip()
    if fence:
        blocks.append(fence)
    return prose[:marker].strip()


def _table_row(line: str) -> bool:
    """Return whether a line belongs to a markdown pipe row.

    Args:
        line: One source line.

    Returns:
        True when the line contains a pipe and is not a prose sentence.
    """

    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_pipe_table(text: str) -> bool:
    """Return whether the answer is a Markdown pipe table.

    Args:
        text: Verified answer text.

    Returns:
        True when a separator row of dashes sits between pipe rows.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return any(line.startswith("|") and set(line) <= set("|-: ") for line in lines)


def _apply_rewrite(
    payload: AnswerPayload,
    rewritten: str,
    verified: str,
    exact_blocks: tuple[str, ...],
) -> AnswerPayload:
    """Replace visible prose when the rewrite stays inside the verified words.

    Code fences, pipe tables, and figure marks from the verified answer
    are appended unchanged after the rewritten prose.

    Args:
        payload: Verified payload.
        rewritten: Model text, which may contain single newlines.
        verified: Prose that was sent to the model, without exact blocks.
        exact_blocks: Fences, tables, and figure marks to keep.

    Returns:
        Payload whose first paragraph is the organized prose.

    Raises:
        ValueError: When the rewrite adds a name or a number, or has no title.
    """

    prose, _ignored = _split_exact_blocks(rewritten)
    normalized = re.sub(r"\n{2,}", "\n", prose).strip()
    if not normalized or len(normalized) > 4000:
        raise ValueError("organize_rejected")
    if _TITLE_LINE.search(normalized) is None:
        raise ValueError("organize_rejected")
    if not _words_are_grounded(normalized, verified):
        raise ValueError("organize_rejected")
    link_ids: list[str] = []
    for paragraph in payload.paragraphs:
        for link_id in paragraph.link_ids:
            if link_id not in link_ids:
                link_ids.append(link_id)
    if not link_ids:
        raise ValueError("organize_rejected")
    return _pack_paragraphs(payload, [normalized, *exact_blocks], link_ids)


def _format_verified_layout(
    payload: AnswerPayload,
    prose: str,
    exact_blocks: tuple[str, ...],
) -> AnswerPayload | None:
    """Turn pasted multi-sentence prose into a title and a bullet list.

    Uses only words already in the verified prose. No model call.

    Args:
        payload: Verified payload.
        prose: Verified prose with exact blocks removed.
        exact_blocks: Fences, tables, and figure marks to keep.

    Returns:
        Organized payload, or ``None`` when the prose is a single sentence,
        a fence or function listing, or has no supporting link.
    """

    if _prose_is_code(prose):
        return None
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(prose) if part.strip()]
    if len(sentences) < 2:
        return None
    title = _local_title(prose, sentences[0])
    if not title:
        return None
    bullets = "\n".join(f"- {sentence}" for sentence in sentences)
    body = f"**{title}**\n{bullets}"
    if len(body) > 4000:
        return None
    link_ids: list[str] = []
    for paragraph in payload.paragraphs:
        for link_id in paragraph.link_ids:
            if link_id not in link_ids:
                link_ids.append(link_id)
    if not link_ids:
        return None
    return _pack_paragraphs(payload, [body, *exact_blocks], link_ids)


def _prose_is_code(prose: str) -> bool:
    """Return whether leftover prose is a fence or a function listing.

    Args:
        prose: Verified text after exact blocks were removed.

    Returns:
        True when a line is a fence marker or a ``def`` listing, so the
        local title step must leave it unchanged.
    """

    for line in prose.splitlines():
        if line.strip().startswith("```"):
            return True
    return _DEF_LISTING.search(prose) is not None


def _local_title(prose: str, first_sentence: str) -> str:
    """Return a short title made from words already in the prose.

    Args:
        prose: Verified prose.
        first_sentence: First sentence of that prose.

    Returns:
        A heading line without the surrounding asterisks.
    """

    for line in prose.splitlines():
        stripped = line.strip().strip("*").strip()
        if stripped.startswith("```"):
            continue
        words = stripped.split()
        if (
            stripped
            and 1 <= len(words) <= 8
            and len(stripped) <= 80
            and not re.search(r"[.!?]$", stripped)
        ):
            return stripped
        if stripped:
            break
    words = _WORD.findall(first_sentence)
    return " ".join(words[:4])


def _pack_paragraphs(
    payload: AnswerPayload,
    bodies: list[str],
    link_ids: list[str],
) -> AnswerPayload:
    """Store prose plus exact blocks as answer paragraphs.

    Args:
        payload: Verified payload.
        bodies: Paragraph texts, prose first.
        link_ids: Supporting link ids copied onto each paragraph.

    Returns:
        Payload whose visible text is those paragraphs.
    """

    kept = [body for body in bodies if body.strip()][:_MAX_PARAGRAPHS]
    paragraphs = tuple(
        AnswerParagraph(
            paragraph_index=index,
            text=body,
            link_ids=tuple(link_ids[:6]),
        )
        for index, body in enumerate(kept)
    )
    citations = tuple(
        item.model_copy(update={"paragraph_index": 0})
        if item.paragraph_index is not None
        else item
        for item in payload.citations
    )
    answer_text = "\n\n".join(item.text for item in paragraphs)
    return payload.model_copy(
        update={
            "answer_text": answer_text,
            "paragraphs": paragraphs,
            "citations": citations,
            "composed_conclusion": None,
        }
    )


def _attach_figures(
    payload: AnswerPayload, state: QueryGraphState, query: str
) -> AnswerPayload:
    """Insert figure marks the question or the answer uses.

    Args:
        payload: Verified or rewritten answer.
        state: Graph state that may hold fusion evidence.
        query: Original user text.

    Returns:
        Payload with useful figures appended, or the same payload.
    """

    raw = state.get("fusion")
    if not isinstance(raw, dict):
        return payload
    try:
        fusion = FusionResult.model_validate(raw)
    except ValidationError:
        return payload
    return insert_useful_figures(payload, fusion, query)


def _words_are_grounded(rewritten: str, verified: str) -> bool:
    """Return whether the rewrite adds a name or a number.

    Lowercase rewording is allowed so the answer can be one voice.
    A capitalized word or a digit must already appear in the verified text,
    including when punctuation between those letters is dropped.

    Args:
        rewritten: Candidate organized answer.
        verified: Verified claim text.

    Returns:
        True when every name and number is already in the verified text.
    """

    folded = "".join(char for char in verified.casefold() if char.isalnum())
    source = {word.casefold() for word in _WORD.findall(verified)}
    for word in _WORD.findall(rewritten):
        token = word.casefold()
        if token in _FUNCTION_WORDS or token in source:
            continue
        letters = "".join(char for char in token if char.isalnum())
        if letters and letters in folded:
            continue
        if any(char.isupper() or char.isdigit() for char in word):
            return False
    return True
