"""ID-free run timing records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from smart_rag_agents.query.run_timings import (
    MAX_RECORDED_ATTEMPTS,
    start_run_timings,
    with_answer_attempt,
)
from smart_rag_core.query_admission.envelopes import FAMILY_DEADLINE_SECONDS
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


def test_attach_delay_uses_the_family_deadline_and_a_fixed_clock() -> None:
    """Attach delay is the family budget minus time left at graph start."""

    now = datetime(2026, 10, 8, tzinfo=UTC)
    context = SimpleNamespace(
        deadline_at=now + timedelta(seconds=10),
        route_family=Phase6RouteFamily.HYBRID,
    )
    timings = start_run_timings(context, now=now)
    family_ms = FAMILY_DEADLINE_SECONDS[Phase6RouteFamily.HYBRID] * 1000
    assert timings["remaining_ms_at_start"] == 10_000
    assert timings["attach_delay_ms"] == family_ms - 10_000


def test_unknown_family_omits_attach_delay() -> None:
    """An unrecognized family still records time left."""

    now = datetime(2026, 10, 8, tzinfo=UTC)
    context = SimpleNamespace(deadline_at=now, route_family="not-a-family")
    timings = start_run_timings(context, now=now)
    assert timings == {"remaining_ms_at_start": 0}
    assert "attach_delay_ms" not in timings


def test_answer_attempts_keep_four_and_cut_reasons() -> None:
    """Later attempts and long reason codes are not stored."""

    state: dict[str, object] = {}
    for _index in range(MAX_RECORDED_ATTEMPTS + 1):
        state.update(
            with_answer_attempt(
                state,
                duration_ms=12,
                outcome="error",
                reason="x" * 80,
            )
        )
    timings = state["run_timings"]
    assert isinstance(timings, dict)
    attempts = timings["answer_attempts"]
    assert isinstance(attempts, list)
    assert len(attempts) == MAX_RECORDED_ATTEMPTS
    assert len(attempts[0]["reason"]) == 64


def test_unknown_attempt_outcome_is_rejected() -> None:
    """Only the four outcome codes may be recorded."""

    with pytest.raises(ValueError, match="attempt_outcome_invalid"):
        with_answer_attempt({}, duration_ms=1, outcome="retried")  # type: ignore[arg-type]
