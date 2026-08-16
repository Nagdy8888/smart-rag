"""Approved entity-rule validation. Suggestions never merge until approved.

Canonical keys are ``{TYPE}::{normalized_name}``. Ambiguous and do-not-merge
names stay separate. Hybrid ``search_aliases`` are never written here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from smart_rag_core.ingestion.chunking.normalize import normalize_for_dedup
from smart_rag_core.jobs.extraction_policy import DEFAULT_ALLOWED_ENTITY_TYPES
from smart_rag_core.retrieval.graph_mapping import EntityRuleView
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

EntityRuleStatus = Literal["suggested", "approved", "revoked"]
EntityRuleSource = Literal["admin", "feedback", "model"]
RelationLabelPolicy = Literal["directed", "symmetric"]
TYPED_KEY_SEPARATOR = "::"
MAX_ALIASES_PER_RULE = 32
MAX_ENTITY_NAME_LENGTH = 256


class EntityRuleRejectedError(ValueError):
    """Raised when an entity-rule payload fails closed.

    Attributes:
        reason: Stable machine-readable reason code.
    """

    def __init__(self, reason: str) -> None:
        """Store a reason code without private alias text.

        Args:
            reason: Short code such as ``alias_cycle`` or ``forbidden``.
        """

        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class EntityRuleDraft:
    """One curated or suggested entity rule before persistence.

    Attributes:
        entity_type: Application type such as ``PROJECT`` or ``PRODUCT``.
        canonical_name: Display/canonical name inside the type.
        aliases: Names that map to ``canonical_name`` after approval.
        do_not_merge: Names that must remain distinct.
        display_label: Optional UI label.
        languages: Empty means every allowed extraction language.
        alias_scope: ``company`` or ``synthetic_eval``.
        relation_label_policy: Directed or symmetric statement identity.
        reason: Owner/admin or suggestion rationale (no corpus text).
        source: ``admin``, ``feedback``, or ``model``.
        confidence: Optional model/feedback confidence in ``[0, 1]``.
        status: Lifecycle. Suggestions start inactive.
    """

    entity_type: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    do_not_merge: tuple[str, ...] = ()
    display_label: str | None = None
    languages: tuple[str, ...] = ()
    alias_scope: str = "company"
    relation_label_policy: RelationLabelPolicy = "directed"
    reason: str = ""
    source: EntityRuleSource = "admin"
    confidence: float | None = None
    status: EntityRuleStatus = "suggested"


def normalize_entity_type(entity_type: str) -> str:
    """Return the uppercase application entity type token.

    Args:
        entity_type: Raw type from a rule or vendor node.

    Returns:
        Uppercase NFKC type with spaces collapsed to underscores.
    """

    collapsed = normalize_for_dedup(entity_type).replace(" ", "_")
    return collapsed.upper()


def normalize_entity_name(name: str) -> str:
    """Return the search-form entity name used for alias matching.

    Args:
        name: Display or vendor name.

    Returns:
        ``arabic_norm_v1`` form so multilingual variants collide correctly.
    """

    return normalize_arabic_v1(name)


def _typed_prefix(entity_type: str) -> str:
    """Return the ``TYPE::`` prefix for typed-key detection.

    Args:
        entity_type: Normalized type.

    Returns:
        Prefix including the separator.
    """

    return f"{normalize_entity_type(entity_type)}{TYPED_KEY_SEPARATOR}"


def validate_entity_rule_draft(
    draft: EntityRuleDraft,
    *,
    existing: Sequence[EntityRuleView] = (),
    allowed_entity_types: Sequence[str] = DEFAULT_ALLOWED_ENTITY_TYPES,
    ignore_rule_type: str | None = None,
    ignore_canonical: str | None = None,
) -> None:
    """Reject cycles, duplicates, cross-type aliases, and silent merges.

    Args:
        draft: Proposed rule.
        existing: Currently approved views that affect graph results.
        allowed_entity_types: Extraction-policy allow-list.
        ignore_rule_type: When updating, skip the prior type of this row.
        ignore_canonical: When updating, skip the prior canonical of this row.

    Raises:
        EntityRuleRejectedError: If the draft cannot become an active rule.
    """

    entity_type = normalize_entity_type(draft.entity_type)
    if not entity_type or entity_type not in {
        normalize_entity_type(item) for item in allowed_entity_types
    }:
        raise EntityRuleRejectedError("unknown_entity_type")
    canonical = draft.canonical_name.strip()
    if not canonical or len(canonical) > MAX_ENTITY_NAME_LENGTH:
        raise EntityRuleRejectedError("canonical_name_required")
    if draft.alias_scope not in {"company", "synthetic_eval"}:
        raise EntityRuleRejectedError("invalid_alias_scope")
    if len(draft.aliases) > MAX_ALIASES_PER_RULE:
        raise EntityRuleRejectedError("alias_limit")
    if draft.source in {"feedback", "model"} and draft.status == "approved":
        raise EntityRuleRejectedError("auto_approval_forbidden")
    if draft.confidence is not None and (
        draft.confidence < 0.0 or draft.confidence > 1.0
    ):
        raise EntityRuleRejectedError("confidence_out_of_range")

    canonical_norm = normalize_entity_name(canonical)
    alias_norms = tuple(
        normalize_entity_name(item) for item in draft.aliases if item.strip()
    )
    blocked_norms = {
        normalize_entity_name(item) for item in draft.do_not_merge if item.strip()
    }
    if len(set(alias_norms)) != len(alias_norms):
        raise EntityRuleRejectedError("duplicate_alias")
    if canonical_norm in blocked_norms:
        raise EntityRuleRejectedError("do_not_merge_conflict")
    if blocked_norms.intersection(alias_norms):
        raise EntityRuleRejectedError("do_not_merge_conflict")

    prefix = _typed_prefix(entity_type)
    for raw in (canonical, *draft.aliases, *draft.do_not_merge):
        stripped = raw.strip()
        if TYPED_KEY_SEPARATOR not in stripped:
            continue
        other_type, _, _rest = stripped.partition(TYPED_KEY_SEPARATOR)
        if other_type and normalize_entity_type(other_type) != entity_type:
            raise EntityRuleRejectedError("cross_type_alias")
        if (
            stripped.upper().startswith(prefix) is False
            and TYPED_KEY_SEPARATOR in stripped
        ):
            raise EntityRuleRejectedError("cross_type_alias")

    ignore_type_norm = (
        normalize_entity_type(ignore_rule_type) if ignore_rule_type else None
    )
    ignore_canonical_norm = (
        normalize_entity_name(ignore_canonical) if ignore_canonical else None
    )
    edges: dict[str, str] = {}
    for rule in existing:
        if rule.status and rule.status != "approved":
            continue
        rule_type = normalize_entity_type(rule.entity_type)
        if rule_type != entity_type:
            continue
        rule_canonical = normalize_entity_name(rule.canonical_name or "")
        if (
            ignore_type_norm == rule_type
            and ignore_canonical_norm == rule_canonical
            and rule_canonical
        ):
            continue
        names = {normalize_entity_name(item) for item in rule.aliases if item}
        if rule_canonical:
            names.add(rule_canonical)
        for name in names:
            if name in edges and edges[name] != rule_canonical:
                raise EntityRuleRejectedError("alias_conflict")
            edges[name] = rule_canonical
        blocked = {normalize_entity_name(item) for item in rule.do_not_merge if item}
        if canonical_norm in blocked or blocked.intersection(alias_norms):
            raise EntityRuleRejectedError("do_not_merge_conflict")

    proposed_names = {canonical_norm, *alias_norms}
    for name in proposed_names:
        prior = edges.get(name)
        if prior is not None and prior != canonical_norm:
            raise EntityRuleRejectedError("alias_conflict")
        edges[name] = canonical_norm

    if _has_alias_cycle(edges):
        raise EntityRuleRejectedError("alias_cycle")


def _has_alias_cycle(edges: dict[str, str]) -> bool:
    """Return whether alias-to-canonical edges contain a cycle.

    Args:
        edges: Normalized alias/canonical to canonical mapping.

    Returns:
        ``True`` when a walk longer than one hop returns to a seen node.
    """

    for start in edges:
        seen: set[str] = set()
        current = start
        depth = 0
        while current in edges and depth <= 32:
            nxt = edges[current]
            if nxt == current:
                break
            if nxt in seen:
                return True
            seen.add(current)
            current = nxt
            depth += 1
        if depth > 32:
            return True
    return False


def draft_matches_do_not_merge(name: str, views: Sequence[EntityRuleView]) -> bool:
    """Return whether ``name`` is blocked from merging under approved rules.

    Args:
        name: Vendor or alias name.
        views: Approved rule views.

    Returns:
        ``True`` when any matching-type do-not-merge list contains the name.
    """

    normalized = normalize_entity_name(name)
    return any(
        normalize_entity_name(item) == normalized
        for view in views
        for item in view.do_not_merge
    )


__all__ = [
    "MAX_ALIASES_PER_RULE",
    "MAX_ENTITY_NAME_LENGTH",
    "TYPED_KEY_SEPARATOR",
    "EntityRuleDraft",
    "EntityRuleRejectedError",
    "draft_matches_do_not_merge",
    "normalize_entity_name",
    "normalize_entity_type",
    "validate_entity_rule_draft",
]
