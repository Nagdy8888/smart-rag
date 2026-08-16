"""Rewrite intent and entity fidelity against the original query."""

from __future__ import annotations

import re

from smart_rag_core.query_profile.extract import DeterministicExtract
from smart_rag_core.query_profile.variants import (
    VariantFidelityError,
    assert_variant_fidelity,
)

_TOKEN = re.compile(r"[A-Za-z0-9_\u0600-\u06FF]+")
_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "on",
        "is",
        "are",
        "what",
        "which",
        "please",
    }
)


def _tokens(text: str) -> set[str]:
    """Return content tokens for Jaccard intent scoring.

    Args:
        text: Query or rewrite.

    Returns:
        Lowercased tokens with a small English stoplist removed.
    """

    found = {match.group(0).lower() for match in _TOKEN.finditer(text)}
    return {item for item in found if item not in _STOP and len(item) > 1}


def score_rewrite_fidelity(
    original: str,
    rewrite: str | None,
    extract: DeterministicExtract,
) -> tuple[float, float, str | None]:
    """Score rewrite intent/entity fidelity and drop unsafe rewrites.

    Args:
        original: Unmodified user query.
        rewrite: Optional model rewrite.
        extract: Deterministic extract of the original.

    Returns:
        ``(intent_fidelity, entity_fidelity, accepted_rewrite)``. When rewrite
        is None or fails entity guards, the accepted rewrite is None and the
        original remains the fallback variant.
    """

    if rewrite is None or rewrite.strip() == "" or rewrite.strip() == original.strip():
        return 1.0, 1.0, None
    intent_tokens_original = _tokens(original)
    intent_tokens_rewrite = _tokens(rewrite)
    if not intent_tokens_original:
        intent = 1.0
    else:
        overlap = intent_tokens_original & intent_tokens_rewrite
        union = intent_tokens_original | intent_tokens_rewrite
        intent = (len(overlap) / len(union)) if union else 0.0
    try:
        assert_variant_fidelity(original, rewrite, extract)
        entity = 1.0
        accepted: str | None = rewrite
    except VariantFidelityError:
        entity = 0.0
        accepted = None
        intent = min(intent, 0.49)
    entities = tuple(
        item for item in (*extract.codes, *extract.aliases) if item.strip()
    )
    if entities:
        present = sum(1 for item in entities if item.lower() in rewrite.lower())
        entity = min(entity, present / len(entities))
        if entity < 1.0:
            accepted = None
    return intent, entity, accepted
