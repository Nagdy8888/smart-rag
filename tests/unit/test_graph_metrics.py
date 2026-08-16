"""Unit tests for graph backlog ETA derived from durable rows."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from smart_rag_core.jobs.graph_metrics import GraphMetricsService


def test_eta_is_insufficient_sample_when_mapping_verified_is_zero() -> None:
    """Packet 3 must not invent documents-per-hour before Packet 4 maps."""

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [
        (3, 1, 120.0),
        (0,),
        (Decimal("1.25"), Decimal("0.50")),
        (None, None, None),
    ]
    metrics = GraphMetricsService(connection).collect()
    assert metrics.mapping_verified_count == 0
    assert metrics.documents_per_hour is None
    assert metrics.eta_seconds is None
    assert metrics.eta_confidence == "insufficient-sample"
    assert metrics.pending_index_count == 3
    assert metrics.pending_maintenance_count == 1
    assert metrics.oldest_pending_age_seconds == 120.0
    assert metrics.attempted_cost_usd == Decimal("1.25")
    assert metrics.settled_cost_usd == Decimal("0.50")
    assert metrics.bulk_window_active is False
