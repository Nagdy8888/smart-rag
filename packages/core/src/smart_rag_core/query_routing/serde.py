"""JSON round-trip helpers for graph state. Frozen ProfileField is strict."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar, cast

from pydantic import BaseModel

from smart_rag_core.evaluation.schema import (
    ExpectedProfile,
    FieldProvenance,
    ProfileField,
)
from smart_rag_core.query_routing.models import (
    BranchResult,
    CorrectionDecision,
    MemoryRecord,
    QueryPreparation,
    RetrievalPlan,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


def preparation_from_state(raw: object) -> QueryPreparation:
    """Rebuild ``QueryPreparation`` from a graph-state mapping or instance.

    Frozen Phase 4 ``ProfileField`` is ``strict=True``, so JSON enum strings
    must be coerced to ``FieldProvenance`` before validation. Packet 2 does
    not retune the Phase 4 schema.

    Args:
        raw: Pydantic instance or JSON-compatible mapping.

    Returns:
        Typed preparation.

    Raises:
        ValueError: When the payload cannot be validated.
    """

    if isinstance(raw, QueryPreparation):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("invalid_preparation")
    payload = dict(cast(Mapping[str, object], raw))
    profile = payload.get("profile")
    if isinstance(profile, ExpectedProfile):
        payload["profile"] = profile
    elif isinstance(profile, Mapping):
        payload["profile"] = expected_profile_from_mapping(
            cast(Mapping[str, object], profile)
        )
    return QueryPreparation.model_validate(payload)


def expected_profile_from_mapping(raw: Mapping[str, object]) -> ExpectedProfile:
    """Coerce a dumped ``ExpectedProfile`` mapping, including strict fields.

    Args:
        raw: JSON-compatible profile mapping.

    Returns:
        Frozen expected profile.

    Raises:
        ValueError: When a nested field cannot be coerced.
    """

    payload: dict[str, object] = {}
    for key, value in raw.items():
        if isinstance(value, ProfileField):
            payload[key] = value
        elif isinstance(value, Mapping) and "provenance" in value:
            payload[key] = profile_field_from_mapping(cast(Mapping[str, object], value))
        else:
            payload[key] = value
    return ExpectedProfile.model_validate(payload)


def profile_field_from_mapping(raw: Mapping[str, object]) -> ProfileField:
    """Coerce one strict ``ProfileField`` from JSON.

    Args:
        raw: Mapping with ``value``, ``confidence``, and ``provenance``.

    Returns:
        Frozen profile field.

    Raises:
        ValueError: When provenance is not a known ``FieldProvenance``.
    """

    payload = dict(raw)
    provenance = payload.get("provenance")
    if isinstance(provenance, str):
        payload["provenance"] = FieldProvenance(provenance)
    return ProfileField.model_validate(payload)


def plan_from_state(raw: object) -> RetrievalPlan:
    """Rebuild a retrieval plan from graph state.

    Args:
        raw: Plan instance or mapping.

    Returns:
        Typed plan.

    Raises:
        ValueError: When validation fails.
    """

    return _model_from_state(RetrievalPlan, raw, "invalid_retrieval_plan")


def branch_results_from_state(raw: object) -> tuple[BranchResult, ...]:
    """Rebuild branch results from graph state.

    Args:
        raw: Sequence of results or mappings.

    Returns:
        Typed branch results.
    """

    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("invalid_branch_results")
    items = cast(Sequence[object], raw)
    return tuple(
        _model_from_state(BranchResult, item, "invalid_branch_result") for item in items
    )


def correction_from_state(raw: object) -> CorrectionDecision:
    """Rebuild a correction decision from graph state.

    Args:
        raw: Decision instance or mapping.

    Returns:
        Typed correction decision.

    Raises:
        ValueError: When validation fails.
    """

    return _model_from_state(CorrectionDecision, raw, "invalid_correction")


def memory_from_state(raw: object) -> tuple[MemoryRecord, ...]:
    """Rebuild memory records from graph state.

    Args:
        raw: Sequence of records or mappings.

    Returns:
        Typed memory records.
    """

    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("invalid_memory_records")
    items = cast(Sequence[object], raw)
    return tuple(
        _model_from_state(MemoryRecord, item, "invalid_memory_record") for item in items
    )


def _model_from_state(model_type: type[ModelT], raw: object, reason: str) -> ModelT:
    """Validate one Pydantic model from an instance or mapping.

    Args:
        model_type: Target model class.
        raw: Instance or mapping.
        reason: Error string when the payload is the wrong type.

    Returns:
        Validated model.

    Raises:
        ValueError: When ``raw`` is neither an instance nor a mapping.
    """

    if isinstance(raw, model_type):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError(reason)
    return model_type.model_validate(raw)
