"""Focused variant generation with fidelity guards."""

from __future__ import annotations

from smart_rag_core.query_profile.extract import DeterministicExtract
from smart_rag_core.query_profile.versions import MAX_VARIANTS


class VariantFidelityError(ValueError):
    """Raised when a variant would change a protected query constraint."""


def _contains_all(haystack: str, needles: tuple[str, ...]) -> bool:
    """Return whether every needle is present.

    Args:
        haystack: Variant text.
        needles: Required substrings.

    Returns:
        True when every non-empty needle occurs in ``haystack``.
    """

    lowered = haystack.lower()
    return all(item.lower() in lowered for item in needles if item)


def assert_variant_fidelity(
    original: str,
    variant: str,
    extract: DeterministicExtract,
) -> None:
    """Reject variants that change protected constraints.

    Args:
        original: Original query.
        variant: Candidate variant.
        extract: Deterministic extract of the original.

    Raises:
        VariantFidelityError: If codes, quotes, dates, negation, or scope change.
    """

    if not _contains_all(variant, extract.codes):
        raise VariantFidelityError("rewrite_changed_code")
    if not _contains_all(variant, extract.quoted_phrases):
        raise VariantFidelityError("rewrite_changed_quotation")
    if not _contains_all(variant, extract.dates):
        raise VariantFidelityError("rewrite_changed_date")
    if extract.negation_scope != "none" and "not " not in variant.lower():
        raise VariantFidelityError("rewrite_changed_negation")
    if extract.document_scope != "none":
        scope_id = extract.document_scope.removeprefix("document:")
        if scope_id not in variant:
            raise VariantFidelityError("rewrite_changed_scope")
    if original.strip() == variant.strip():
        raise VariantFidelityError("duplicate_variant")


def collapse_variants(variants: tuple[str, ...]) -> tuple[str, ...]:
    """Drop duplicates while preserving order, capped at three.

    Args:
        variants: Candidate variants.

    Returns:
        At most ``MAX_VARIANTS`` unique variants.
    """

    seen: set[str] = set()
    ordered: list[str] = []
    for item in variants:
        key = item.strip()
        if key == "" or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
        if len(ordered) >= MAX_VARIANTS:
            break
    return tuple(ordered)


def generate_focused_variants(
    query: str,
    extract: DeterministicExtract,
    *,
    candidates: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return justified variants that pass fidelity checks.

    Packet 3 does not emit variants unless rewrite is justified and candidates
    are supplied. LLM-invented extras are filtered here.

    Args:
        query: Original query.
        extract: Deterministic extract.
        candidates: Optional model or test-supplied variants.

    Returns:
        At most three unique faithful variants. Duplicate originals collapse.
    """

    if not extract.rewrite_justified or not candidates:
        return ()
    accepted: list[str] = []
    for candidate in candidates:
        try:
            assert_variant_fidelity(query, candidate, extract)
        except VariantFidelityError:
            continue
        accepted.append(candidate)
    return collapse_variants(tuple(accepted))
