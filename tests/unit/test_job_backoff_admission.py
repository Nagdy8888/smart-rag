"""Unit tests for job backoff and admission helpers."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.jobs.backoff import compute_retry_delay_seconds
from smart_rag_core.jobs.exceptions import JobAdmissionError
from smart_rag_core.jobs.limits import (
    MAX_ESTIMATED_JOB_SIZE_BYTES,
    MAX_PENDING_INGESTION_JOBS,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_MAX_SECONDS,
)


def test_backoff_grows_and_caps() -> None:
    """Retry delay increases exponentially and respects the hard ceiling."""

    first = compute_retry_delay_seconds(1, jitter_fraction=0.0)
    second = compute_retry_delay_seconds(2, jitter_fraction=0.0)
    capped = compute_retry_delay_seconds(20, jitter_fraction=0.0)

    assert first == RETRY_BACKOFF_BASE_SECONDS
    assert second == RETRY_BACKOFF_BASE_SECONDS * 2
    assert capped == RETRY_BACKOFF_MAX_SECONDS


def test_backoff_jitter_stays_within_fraction() -> None:
    """Jitter keeps delays near the base exponential value."""

    delay = compute_retry_delay_seconds(3, jitter_fraction=0.25)
    base = min(RETRY_BACKOFF_BASE_SECONDS * 4, RETRY_BACKOFF_MAX_SECONDS)
    assert delay >= int(base * 0.75)
    assert delay <= int(base * 1.25) + 1


def test_admission_rejects_pending_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pending-cap backpressure raises ``JobAdmissionError``."""

    connection = MagicMock()
    service = JobAdmissionService(connection)
    monkeypatch.setattr(
        service, "_count_pending_ingestion_jobs", lambda: MAX_PENDING_INGESTION_JOBS
    )

    with pytest.raises(JobAdmissionError) as caught:
        service.assert_can_enqueue_ingestion(
            estimated_size_bytes=1024,
            estimated_cost_usd=Decimal("0.01"),
        )

    assert caught.value.reason == "pending_cap"


def test_admission_rejects_oversize_job() -> None:
    """Estimated size above the hard cap is rejected."""

    connection = MagicMock()
    service = JobAdmissionService(connection)

    with pytest.raises(JobAdmissionError) as caught:
        service.assert_can_enqueue_ingestion(
            estimated_size_bytes=MAX_ESTIMATED_JOB_SIZE_BYTES + 1,
            estimated_cost_usd=Decimal("0.01"),
        )

    assert caught.value.reason == "estimated_size_exceeds_cap"


def test_admission_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Daily budget reservation failure surfaces ``budget_exhausted``."""

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [(Decimal("20"),), (Decimal("20"),)]
    service = JobAdmissionService(connection)
    monkeypatch.setattr(service, "_count_pending_ingestion_jobs", lambda: 0)

    with pytest.raises(JobAdmissionError) as caught:
        service.assert_can_enqueue_ingestion(
            estimated_size_bytes=0,
            estimated_cost_usd=Decimal("0.01"),
        )

    assert caught.value.reason == "budget_exhausted"


def test_graph_index_budget_ignores_ingestion_daily() -> None:
    """Graph index reservations must not share the Hybrid ingestion cap."""

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [
        (Decimal("20"),),
        (Decimal("0"),),
    ]
    service = JobAdmissionService(connection)
    reservation_id = service.create_graph_budget_reservation(
        reservation_kind="graph_index",
        estimated_cost_usd=Decimal("0.50"),
    )
    assert reservation_id is not None
    inserted = cursor.execute.call_args.args[1]
    assert inserted[1] == "graph_index"
    assert inserted[1] != "ingestion_daily"


def test_graph_index_budget_ignores_exhausted_ingestion_daily() -> None:
    """Graph index admission must not read leftover ``ingestion_daily`` spend."""

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [
        (Decimal("20"),),
        (Decimal("0"),),
    ]
    service = JobAdmissionService(connection)
    reservation_id = service.create_graph_budget_reservation(
        reservation_kind="graph_index",
        estimated_cost_usd=Decimal("0.50"),
    )
    assert reservation_id is not None
    kind_filters = [
        str(call.args[0]) for call in cursor.execute.call_args_list if call.args
    ]
    assert any("graph_index" in sql for sql in kind_filters)
    assert not any("ingestion_daily" in sql for sql in kind_filters)


def test_graph_maintenance_kind_rejected_as_index() -> None:
    """Unknown graph reservation kinds fail closed."""

    service = JobAdmissionService(MagicMock())
    with pytest.raises(JobAdmissionError) as caught:
        service.create_graph_budget_reservation(
            reservation_kind="ingestion_daily",
            estimated_cost_usd=Decimal("0.50"),
        )
    assert caught.value.reason == "invalid_graph_reservation_kind"
