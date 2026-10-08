"""ID-free measured run timings carried in ``QueryGraphState.run_timings``.

Run-event ``created_at`` values come from a background writer and lag the
work by seconds, so they cannot time a stage. These helpers record wall
times where the work happens. The checkpoint stores them, and
``scripts/eval_ask_stage_export.py`` copies them into the private stage
export. Values are integers, safe reason codes, or short lists; never
query, passage, or answer text.

Keys:
    ``remaining_ms_at_start``: Milliseconds left to the run deadline when
        the API built the graph input.
    ``attach_delay_ms``: Admission to graph start, derived as the route
        family's deadline minus ``remaining_ms_at_start``. Assumes the API
        and database clocks agree to within normal NTP skew.
    ``answer_attempts``: Up to ``MAX_RECORDED_ATTEMPTS`` entries of
        ``{"duration_ms", "outcome", "reason"}`` in call order.
    ``verifier_ms`` / ``verifier_outcome``: The verifier batch wall time and
        ``ok`` or ``skipped``; ``verifier_reason`` names a skip.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, cast

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.envelopes import FAMILY_DEADLINE_SECONDS

AttemptOutcome = Literal["ok", "timeout_after_send", "deadline_exhausted", "error"]
"""Allowed ``answer_attempts[].outcome`` values."""

MAX_RECORDED_ATTEMPTS = 4
"""Upper bound on recorded answer attempts per run."""

MAX_REASON_CHARS = 64
"""Reason codes are truncated to this length."""


def start_run_timings(
    context: AuthorizedRuntimeContext,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Return the timings known when the API builds the graph input.

    Args:
        context: Server-derived runtime context with the admitted deadline.
        now: Clock override for tests. Defaults to UTC now.

    Returns:
        ``remaining_ms_at_start`` and ``attach_delay_ms``, both clamped at
        zero. ``attach_delay_ms`` is omitted for an unknown route family.
    """

    current = now if now is not None else datetime.now(UTC)
    remaining_ms = max(0, int((context.deadline_at - current).total_seconds() * 1000))
    timings: dict[str, object] = {"remaining_ms_at_start": remaining_ms}
    family_seconds = FAMILY_DEADLINE_SECONDS.get(context.route_family)
    if family_seconds is not None:
        timings["attach_delay_ms"] = max(0, family_seconds * 1000 - remaining_ms)
    return timings


def with_answer_attempt(
    state: Mapping[str, object],
    *,
    duration_ms: int,
    outcome: AttemptOutcome,
    reason: str = "",
) -> dict[str, object]:
    """Return a ``run_timings`` update with one more answer attempt.

    Args:
        state: Current graph state. Only ``run_timings`` is read.
        duration_ms: Attempt wall time in milliseconds. Negative becomes 0.
        outcome: Attempt outcome code.
        reason: Safe failure reason code, empty on success.

    Returns:
        ``{"run_timings": merged}``. Attempts past
        ``MAX_RECORDED_ATTEMPTS`` are dropped.
    """

    merged = _current(state)
    attempts = list(cast(list[object], merged.get("answer_attempts") or []))
    if len(attempts) < MAX_RECORDED_ATTEMPTS:
        attempts.append(
            {
                "duration_ms": max(0, int(duration_ms)),
                "outcome": outcome,
                "reason": reason[:MAX_REASON_CHARS],
            }
        )
    merged["answer_attempts"] = attempts
    return {"run_timings": merged}


def with_verifier_timing(
    state: Mapping[str, object],
    *,
    duration_ms: int,
    skipped_reason: str | None,
) -> dict[str, object]:
    """Return a ``run_timings`` update with the verifier batch timing.

    Args:
        state: Current graph state. Only ``run_timings`` is read.
        duration_ms: Verifier batch wall time in milliseconds.
        skipped_reason: Reason code when the verifier was skipped, else
            ``None``.

    Returns:
        ``{"run_timings": merged}`` with ``verifier_ms`` and
        ``verifier_outcome``, plus ``verifier_reason`` on a skip.
    """

    merged = _current(state)
    merged["verifier_ms"] = max(0, int(duration_ms))
    merged["verifier_outcome"] = "ok" if skipped_reason is None else "skipped"
    if skipped_reason is not None:
        merged["verifier_reason"] = skipped_reason[:MAX_REASON_CHARS]
    return {"run_timings": merged}


def _current(state: Mapping[str, object]) -> dict[str, object]:
    """Copy the state's ``run_timings`` mapping, or start an empty one.

    Args:
        state: Current graph state.

    Returns:
        A new dict the caller may mutate.
    """

    raw = state.get("run_timings")
    if isinstance(raw, Mapping):
        return dict(cast(Mapping[str, object], raw))
    return {}
