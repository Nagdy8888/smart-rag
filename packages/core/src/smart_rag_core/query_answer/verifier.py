"""One batched small-model verifier covering at most six material links."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.paragraphs import drop_unsupported_paragraphs
from smart_rag_core.query_answer.versions import MAX_VERIFIER_CALLS, MAX_VERIFIER_LINKS

VerifierCaller = Callable[[tuple[AtomicLink, ...]], VerifierPayload]

VERBATIM_MIN_CHARS = 12


def select_material_links(
    links: tuple[AtomicLink, ...],
    *,
    limit: int = MAX_VERIFIER_LINKS,
) -> tuple[tuple[AtomicLink, ...], tuple[str, ...]]:
    """Take at most six material links. Never queue a second verifier call.

    Inference links outrank ordinary facts. Remaining links are omitted.

    Args:
        links: Candidate atomic links after deterministic filtering.
        limit: Frozen batch cap of 6.

    Returns:
        Selected links and omitted link IDs.
    """

    ordered = sorted(
        links,
        key=lambda item: (
            0 if item.kind == "inference_link" else 1,
            item.priority,
            item.link_id,
        ),
    )
    selected = tuple(ordered[:limit])
    omitted = tuple(item.link_id for item in ordered[limit:])
    return selected, omitted


def apply_verifier_payload(
    payload: AnswerPayload,
    verdicts: VerifierPayload,
) -> AnswerPayload:
    """Remove unsupported links and any paragraph that depends on them.

    Args:
        payload: Answer after deterministic checks.
        verdicts: One structured verifier batch.

    Returns:
        Answer with unsupported links omitted. Paragraphs that named a
        rejected link are dropped and ``answer_text`` is rebuilt. When
        no paragraph survives, the original prose is replaced by a
        citation-free refusal.
    """

    unsupported = {
        item.link_id for item in verdicts.link_verdicts if not item.supported
    }
    return drop_unsupported_paragraphs(payload, frozenset(unsupported))


def run_verifier_batch(
    payload: AnswerPayload,
    *,
    caller: VerifierCaller | None,
    already_called: int,
) -> tuple[AnswerPayload, int, tuple[str, ...]]:
    """Issue at most one verifier call for up to six links.

    Args:
        payload: Deterministically checked answer.
        caller: Structured verifier adapter. None skips the model call.
        already_called: Existing verifier call count. A second call fails.

    Returns:
        Updated answer, resulting call count (0 or 1), and omitted link IDs.

    Raises:
        AnswerError: If a second verifier call is requested.
    """

    if already_called >= MAX_VERIFIER_CALLS:
        raise AnswerError("verifier_loop")
    selected, omitted = select_material_links(payload.atomic_links)
    if not selected or caller is None:
        skipped = payload
        if payload.paragraphs:
            skipped = drop_unsupported_paragraphs(payload, frozenset(omitted))
        return _force_partial_if_omitted(skipped, omitted), 0, omitted
    verdicts = caller(selected)
    if len(verdicts.link_verdicts) > MAX_VERIFIER_LINKS:
        raise AnswerError("verifier_batch_cap")
    updated = apply_verifier_payload(payload, verdicts)
    if updated.paragraphs:
        updated = drop_unsupported_paragraphs(updated, frozenset(omitted))
    return _force_partial_if_omitted(updated, omitted), 1, omitted


def _force_partial_if_omitted(
    payload: AnswerPayload, omitted: tuple[str, ...]
) -> AnswerPayload:
    """Force answer status ``partial`` when verifier omitted material links.

    Args:
        payload: Answer after deterministic checks and optional verdicts.
        omitted: Link IDs excluded from the six-link batch.

    Returns:
        Payload whose ``complete`` status becomes ``partial`` when omitted
        IDs exist. Already partial/refused statuses are unchanged.
    """

    if omitted and payload.status == "complete":
        return payload.model_copy(update={"status": "partial"})
    return payload


def mock_verifier_payload(links: tuple[AtomicLink, ...]) -> VerifierPayload:
    """Return identity-support verdicts for tests and mock mode.

    Args:
        links: Batch of at most six links.

    Returns:
        Verdicts marking a link supported when it cites at least one ID.
    """

    capped = links[:MAX_VERIFIER_LINKS]
    verdicts = tuple(
        VerifierLinkVerdict(
            link_id=item.link_id,
            supported=bool(item.chunk_ids)
            or bool(item.table_id and item.source_ranges),
            reason="supported"
            if (item.chunk_ids or item.table_id)
            else "unsupported_link",
        )
        for item in capped
    )
    return VerifierPayload(link_verdicts=verdicts)
