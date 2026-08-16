"""Comparative fixture: catalog discovery versus deterministic mapping."""

from __future__ import annotations

import time

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.budgets import count_tokens
from smart_rag_core.tools.catalog import default_registry
from smart_rag_core.tools.constants import (
    MAX_DISCOVERY_TOKEN_RATIO,
    MIN_DISCOVERY_ACCURACY_GAIN_PP,
)
from smart_rag_core.tools.disclosure import assemble_optional_prompt, load_manifests
from smart_rag_core.tools.discovery import run_catalog_search, select_from_cards
from smart_rag_core.tools.intents import detect_optional_intent
from smart_rag_core.tools.mapping import map_optional_intent
from smart_rag_core.tools.models import (
    ComparisonMetrics,
    OptionalIntent,
    SelectionPolicy,
)
from smart_rag_core.tools.permissions import visible_tools

COMPARISON_CASES: tuple[tuple[str, str | None, UserRole], ...] = (
    ("export the table as csv", "export_csv", UserRole.MEMBER),
    ("download these rows as xlsx", "export_xlsx", UserRole.MEMBER),
    ("export this table", "export_csv", UserRole.MEMBER),
    ("export the results to excel", "export_xlsx", UserRole.MEMBER),
    ("What is the status of INV-SR-1001?", None, UserRole.MEMBER),
    ("sum the amount column on sheet 1", None, UserRole.MEMBER),
    ("invite user a@b.test", None, UserRole.MEMBER),
    ("invite user a@b.test", "admin_user_invite", UserRole.ADMIN),
    ("export csv", None, UserRole.VIEWER),
    ("download parquet export", "export_parquet", UserRole.MEMBER),
)


def evaluate_discovery_justification(metrics: ComparisonMetrics) -> SelectionPolicy:
    """Return the runtime policy implied by comparison metrics.

    Discovery is retained only when it improves accuracy by at least
    ``MIN_DISCOVERY_ACCURACY_GAIN_PP`` and stays within
    ``MAX_DISCOVERY_TOKEN_RATIO`` of deterministic tokens.

    Args:
        metrics: Measured comparison.

    Returns:
        ``DETERMINISTIC_MAPPING`` or ``CATALOG_DISCOVERY``.
    """

    token_ratio = (
        float("inf")
        if metrics.deterministic_tokens == 0 and metrics.discovery_tokens > 0
        else (
            0.0
            if metrics.deterministic_tokens == 0
            else metrics.discovery_tokens / metrics.deterministic_tokens
        )
    )
    if (
        metrics.accuracy_gain_pp >= MIN_DISCOVERY_ACCURACY_GAIN_PP
        and token_ratio <= MAX_DISCOVERY_TOKEN_RATIO
    ):
        return SelectionPolicy.CATALOG_DISCOVERY
    return SelectionPolicy.DETERMINISTIC_MAPPING


def compare_discovery_vs_mapping() -> ComparisonMetrics:
    """Score the ≥20-tool catalog on explicit, ambiguous, and core queries.

    Returns:
        Metrics plus the frozen policy decision.
    """

    registry = default_registry()
    det_hits = 0
    disc_hits = 0
    det_tokens = 0
    disc_tokens = 0
    det_ms = 0.0
    disc_ms = 0.0
    for query, gold, role in COMPARISON_CASES:
        start = time.perf_counter()
        intent = detect_optional_intent(query)
        mapped = map_optional_intent(intent)
        if role is UserRole.VIEWER and mapped is not None:
            mapped_visible = visible_tools(registry, role=role)
            if mapped not in {item.tool_key for item in mapped_visible}:
                mapped = None
        det_ms += (time.perf_counter() - start) * 1000.0
        det_tokens += count_tokens(mapped or "")
        if mapped == gold:
            det_hits += 1
        start = time.perf_counter()
        _level0, cards, _remaining, _searched = run_catalog_search(
            query,
            role=role,
            remaining_discovery_rounds=1,
            registry=registry,
        )
        selected = select_from_cards(query, cards, limit=1)
        intent = detect_optional_intent(query)
        if intent is OptionalIntent.NONE:
            chosen = None
        else:
            chosen = selected[0] if selected else None
        prompt = assemble_optional_prompt(level0=_level0, level1=cards)
        if chosen is not None and chosen in {card.tool_key for card in cards.cards}:
            manifests, _left = load_manifests(
                (chosen,),
                role=role,
                remaining_manifests=3,
                registry=registry,
            )
            prompt = assemble_optional_prompt(
                level0=_level0,
                level1=cards,
                manifests=manifests,
            )
        disc_ms += (time.perf_counter() - start) * 1000.0
        disc_tokens += count_tokens(prompt)
        if chosen == gold:
            disc_hits += 1
    case_count = len(COMPARISON_CASES)
    det_acc = det_hits / case_count
    disc_acc = disc_hits / case_count
    gain_pp = (disc_acc - det_acc) * 100.0
    selected = evaluate_discovery_justification(
        ComparisonMetrics(
            tool_count=len(registry),
            case_count=case_count,
            deterministic_accuracy=det_acc,
            discovery_accuracy=disc_acc,
            accuracy_gain_pp=gain_pp,
            deterministic_latency_ms=det_ms,
            discovery_latency_ms=disc_ms,
            deterministic_tokens=det_tokens,
            discovery_tokens=disc_tokens,
            selected_policy=SelectionPolicy.DETERMINISTIC_MAPPING,
            justification="placeholder",
        )
    )
    if selected is SelectionPolicy.CATALOG_DISCOVERY:
        justification = (
            "Discovery improved selection enough to justify latency and tokens."
        )
    else:
        justification = (
            "Discovery did not improve selection enough to justify latency or "
            "token cost; runtime uses deterministic mapping."
        )
    return ComparisonMetrics(
        tool_count=len(registry),
        case_count=case_count,
        deterministic_accuracy=det_acc,
        discovery_accuracy=disc_acc,
        accuracy_gain_pp=gain_pp,
        deterministic_latency_ms=det_ms,
        discovery_latency_ms=disc_ms,
        deterministic_tokens=det_tokens,
        discovery_tokens=disc_tokens,
        selected_policy=selected,
        justification=justification,
    )


RUNTIME_SELECTION_POLICY = SelectionPolicy.DETERMINISTIC_MAPPING
"""Frozen after ``compare_discovery_vs_mapping``. Unjustified discovery is not retained."""
