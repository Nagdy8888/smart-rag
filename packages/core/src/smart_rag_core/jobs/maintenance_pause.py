"""Bounded maintenance pause under database CPU, memory, IO, or Hybrid p95.

HNSW reindex, LightRAG clean rebuild, and BM25 subset rebuild consult this
controller before starting work. The 70% trigger is fail-closed: a sample at
or above the signed user-load threshold must pause, and missing or invalid
telemetry cannot be treated as below threshold.

Live Packet 4 8-doc load is not QT-CAP-001/002 proof. Inject fixtures rather
than melting the host Docker VM to reach 70%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from smart_rag_core.jobs.limits import (
    HYBRID_P95_PAUSE_GATE_MS,
    USER_LOAD_PAUSE_PERCENT,
)

PAUSE_REASON_TELEMETRY_MISSING = "telemetry_missing"
PAUSE_REASON_TELEMETRY_INVALID = "telemetry_invalid"
PAUSE_REASON_CPU = "cpu_at_or_above_70pct"
PAUSE_REASON_IO = "io_at_or_above_70pct"
PAUSE_REASON_MEMORY = "memory_at_or_above_70pct"
PAUSE_REASON_HYBRID_P95 = "hybrid_p95_breach"
PAUSE_REASON_SAMPLER_ERROR = "sampler_error"


@dataclass(frozen=True, slots=True)
class DatabasePressureSample:
    """One injected or scraped database pressure snapshot.

    Attributes:
        cpu_percent: Database or container CPU percent, or None when unknown.
        io_percent: Database or container IO percent, or None when unknown.
        memory_percent: Database or container memory percent, or None.
        hybrid_p95_ms: Hybrid first-evidence p95 in milliseconds, or None.
    """

    cpu_percent: float | None = None
    io_percent: float | None = None
    memory_percent: float | None = None
    hybrid_p95_ms: float | None = None


@dataclass(frozen=True, slots=True)
class MaintenancePauseDecision:
    """Whether maintenance must pause under the signed user-load gates.

    Attributes:
        paused: True when HNSW, LightRAG rebuild, or BM25 rebuild must not
            start.
        trigger_70_percent_fired: True when CPU, IO, or memory is at or
            above ``USER_LOAD_PAUSE_PERCENT``.
        hybrid_p95_breach: True when Hybrid p95 exceeds QT-LAT-001.
        fail_closed: True when telemetry is missing or invalid.
        reasons: Stable machine-readable pause reasons.
        sample: Sample that produced this decision, or None.
    """

    paused: bool
    trigger_70_percent_fired: bool
    hybrid_p95_breach: bool
    fail_closed: bool
    reasons: tuple[str, ...]
    sample: DatabasePressureSample | None


class PressureSampler(Protocol):
    """Supplies the latest database pressure sample for maintenance gates."""

    def sample(self) -> DatabasePressureSample | None:
        """Return the current sample, or None when telemetry is unavailable.

        Returns:
            Injected or scraped pressure, or None when the scrape is missing.
        """


class FailClosedPressureSampler:
    """Sampler that always reports missing telemetry."""

    def sample(self) -> DatabasePressureSample | None:
        """Return None so evaluate pauses fail-closed.

        Returns:
            Always ``None``.
        """

        return None


class StaticPressureSampler:
    """Sampler that returns one injected fixture sample.

    Attributes:
        _sample: Frozen pressure snapshot used for tests or a scrape.
    """

    def __init__(self, sample: DatabasePressureSample) -> None:
        """Capture one injected sample.

        Args:
            sample: Fixture or scrape used on every ``sample()`` call.
        """

        self._sample = sample

    def sample(self) -> DatabasePressureSample | None:
        """Return the captured sample.

        Returns:
            The injected ``DatabasePressureSample``.
        """

        return self._sample


class UnmeasuredPressureSampler:
    """Sampler that returns an empty sample so unmeasured load may proceed.

    Worker rebuilds use this until ops injects docker or cloud telemetry.
    HNSW reindex and fixture tests must not use this sampler.
    """

    def sample(self) -> DatabasePressureSample | None:
        """Return an empty sample for ``require_telemetry=False``.

        Returns:
            A sample with every metric unset.
        """

        return DatabasePressureSample()


def _finite_non_negative(value: float | None) -> float | None:
    """Return a usable metric, or None when the value is unset.

    Args:
        value: Raw percent or millisecond reading.

    Returns:
        ``value`` when it is a finite number greater than or equal to 0.

    Raises:
        ValueError: If the value is NaN, infinite, or negative.
    """

    if value is None:
        return None
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("invalid_metric")
    return value


def evaluate_maintenance_pause(
    sample: DatabasePressureSample | None,
    *,
    require_telemetry: bool = True,
) -> MaintenancePauseDecision:
    """Decide whether maintenance must pause.

    Args:
        sample: Injected CPU, IO, memory, and optional Hybrid p95. ``None``
            is missing telemetry.
        require_telemetry: When true, missing CPU/IO/memory pauses. When
            false, unmeasured samples allow work unless a present metric
            fires.

    Returns:
        Pause decision. ``paused`` is true at 70% CPU/IO/memory, on Hybrid
        p95 breach, or when required telemetry is missing or invalid.

    Side Effects:
        None. Callers skip REINDEX, rebuild isolation, or BM25 rebuild.
    """

    if sample is None:
        return MaintenancePauseDecision(
            paused=True,
            trigger_70_percent_fired=False,
            hybrid_p95_breach=False,
            fail_closed=True,
            reasons=(PAUSE_REASON_TELEMETRY_MISSING,),
            sample=None,
        )
    try:
        cpu = _finite_non_negative(sample.cpu_percent)
        io_pct = _finite_non_negative(sample.io_percent)
        memory = _finite_non_negative(sample.memory_percent)
        p95 = _finite_non_negative(sample.hybrid_p95_ms)
    except ValueError:
        return MaintenancePauseDecision(
            paused=True,
            trigger_70_percent_fired=False,
            hybrid_p95_breach=False,
            fail_closed=True,
            reasons=(PAUSE_REASON_TELEMETRY_INVALID,),
            sample=sample,
        )
    reasons: list[str] = []
    trigger_70 = False
    if cpu is not None and cpu >= USER_LOAD_PAUSE_PERCENT:
        trigger_70 = True
        reasons.append(PAUSE_REASON_CPU)
    if io_pct is not None and io_pct >= USER_LOAD_PAUSE_PERCENT:
        trigger_70 = True
        reasons.append(PAUSE_REASON_IO)
    if memory is not None and memory >= USER_LOAD_PAUSE_PERCENT:
        trigger_70 = True
        reasons.append(PAUSE_REASON_MEMORY)
    p95_breach = p95 is not None and p95 > HYBRID_P95_PAUSE_GATE_MS
    if p95_breach:
        reasons.append(PAUSE_REASON_HYBRID_P95)
    pressure_present = cpu is not None or io_pct is not None or memory is not None
    fail_closed = require_telemetry and not pressure_present
    if fail_closed:
        reasons.append(PAUSE_REASON_TELEMETRY_MISSING)
    paused = trigger_70 or p95_breach or fail_closed
    return MaintenancePauseDecision(
        paused=paused,
        trigger_70_percent_fired=trigger_70,
        hybrid_p95_breach=p95_breach,
        fail_closed=fail_closed,
        reasons=tuple(reasons),
        sample=sample,
    )


def pause_error_code(decision: MaintenancePauseDecision) -> str:
    """Return a bounded last_error for a paused LightRAG rebuild job.

    Args:
        decision: Pause decision from ``evaluate_maintenance_pause``.

    Returns:
        ``maintenance_paused:{first_reason}`` truncated for job storage.
    """

    reason = decision.reasons[0] if decision.reasons else "paused"
    return f"maintenance_paused:{reason}"[:4000]


class MaintenancePauseController:
    """Evaluates injected pressure before HNSW, LightRAG, or BM25 rebuild.

    Attributes:
        _sampler: Telemetry source. Fixtures inject ``StaticPressureSampler``.
        _require_telemetry: Fail closed when CPU/IO/memory are all missing.
    """

    def __init__(
        self,
        sampler: PressureSampler,
        *,
        require_telemetry: bool = True,
    ) -> None:
        """Bind a sampler and fail-closed policy.

        Args:
            sampler: Pressure source. Tests inject fixtures here.
            require_telemetry: When true, missing CPU/IO/memory pauses.
        """

        self._sampler = sampler
        self._require_telemetry = require_telemetry

    @classmethod
    def fail_closed(cls) -> MaintenancePauseController:
        """Return a controller that pauses when telemetry is missing.

        Returns:
            Controller using ``FailClosedPressureSampler``.
        """

        return cls(FailClosedPressureSampler(), require_telemetry=True)

    @classmethod
    def unmeasured_allows(cls) -> MaintenancePauseController:
        """Return a controller that allows rebuilds until telemetry exists.

        Returns:
            Controller that pauses only on measured 70% or p95 breach.
        """

        return cls(UnmeasuredPressureSampler(), require_telemetry=False)

    @classmethod
    def from_sample(
        cls,
        sample: DatabasePressureSample,
        *,
        require_telemetry: bool = True,
    ) -> MaintenancePauseController:
        """Return a controller bound to one injected sample.

        Args:
            sample: Fixture or scrape.
            require_telemetry: Fail-closed policy for that sample.

        Returns:
            Controller that always reuses ``sample``.
        """

        return cls(StaticPressureSampler(sample), require_telemetry=require_telemetry)

    def decide(self) -> MaintenancePauseDecision:
        """Sample telemetry and evaluate the pause gates.

        Returns:
            Pause decision. Sampler exceptions fail closed.

        Side Effects:
            Calls ``sampler.sample()``. Does not start or cancel SQL.
        """

        try:
            sample = self._sampler.sample()
        except Exception:
            return MaintenancePauseDecision(
                paused=True,
                trigger_70_percent_fired=False,
                hybrid_p95_breach=False,
                fail_closed=True,
                reasons=(PAUSE_REASON_SAMPLER_ERROR,),
                sample=None,
            )
        return evaluate_maintenance_pause(
            sample,
            require_telemetry=self._require_telemetry,
        )
