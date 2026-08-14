"""Pure glossary validation: cycles, conflicts, duplicates, and unsafe rules."""

from __future__ import annotations

from collections import defaultdict

from smart_rag_core.evaluation.identifier_rules import (
    CollisionRisk,
    assess_collision_risk,
)
from smart_rag_core.glossary.models import GlossaryBatch, GlossaryEntryType
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


class GlossaryValidationError(ValueError):
    """Raised when a glossary batch is rejected. Messages are reason codes only."""

    def __init__(self, reason: str) -> None:
        """Initialize with a machine-readable reason and no private terms.

        Args:
            reason: Stable reason code such as ``alias_cycle``.
        """

        super().__init__(reason)
        self.reason = reason


def validate_glossary_batch(batch: GlossaryBatch) -> None:
    """Reject cycles, conflicts, duplicates, missing targets, and unsafe rules.

    Args:
        batch: Proposed import payload.

    Raises:
        GlossaryValidationError: If the batch cannot be approved. The exception
            message is a reason code and never contains alias or canonical text.
    """

    entry_keys: set[str] = set()
    canonical_by_norm: dict[str, str] = {}
    alias_edges: dict[str, str] = {}
    alias_scopes: dict[str, str] = {}
    for entry in batch.entries:
        if entry.entry_key in entry_keys:
            raise GlossaryValidationError("duplicate_entry_key")
        entry_keys.add(entry.entry_key)
        canonical_norm = normalize_arabic_v1(entry.canonical_term)
        if canonical_norm == "":
            raise GlossaryValidationError("empty_canonical")
        if (
            canonical_norm in canonical_by_norm
            and canonical_by_norm[canonical_norm] != entry.entry_key
        ):
            raise GlossaryValidationError("duplicate_canonical")
        canonical_by_norm[canonical_norm] = entry.entry_key
        if entry.entry_type is GlossaryEntryType.IDENTIFIER_RULE:
            if entry.identifier_pattern is None:
                raise GlossaryValidationError("missing_identifier_pattern")
            risk, _reason = assess_collision_risk(entry.identifier_pattern)
            if risk is CollisionRisk.HIGH:
                raise GlossaryValidationError("high_collision_rule")
        for alias in entry.aliases:
            alias_norm = normalize_arabic_v1(alias.alias)
            if alias_norm == "":
                raise GlossaryValidationError("empty_alias")
            if alias_norm == canonical_norm:
                raise GlossaryValidationError("alias_equals_canonical")
            scope = entry.effective_scope.value
            prior_target = alias_edges.get(alias_norm)
            prior_scope = alias_scopes.get(alias_norm)
            if prior_target is not None and prior_target != canonical_norm:
                if prior_scope == scope:
                    raise GlossaryValidationError("alias_conflict")
                raise GlossaryValidationError("cross_scope_conflict")
            if prior_target == canonical_norm and prior_scope == scope:
                raise GlossaryValidationError("duplicate_alias")
            alias_edges[alias_norm] = canonical_norm
            alias_scopes[alias_norm] = scope
    if _has_cycle(alias_edges):
        raise GlossaryValidationError("alias_cycle")
    for alias_norm, canonical_norm in alias_edges.items():
        if alias_norm in canonical_by_norm and canonical_by_norm[
            alias_norm
        ] != canonical_by_norm.get(canonical_norm, ""):
            # Alias surface is also a different canonical entry; allowed as an
            # edge, cycle detection covers mutual aliases.
            continue


def _has_cycle(edges: dict[str, str]) -> bool:
    """Return whether alias-to-canonical edges contain a cycle.

    Args:
        edges: Mapping of normalized alias to normalized canonical term.

    Returns:
        ``True`` when following edges revisits a node.
    """

    graph: dict[str, set[str]] = defaultdict(set)
    for source, target in edges.items():
        graph[source].add(target)
        graph.setdefault(target, set())
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        """DFS cycle visit.

        Args:
            node: Current graph node.

        Returns:
            ``True`` if a cycle is found from this node.
        """

        if node in visited:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        for nxt in graph[node]:
            if visit(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
