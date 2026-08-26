"""Development-case selection and graph-state conversion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from smart_rag_core.evaluation.agent_eval.schema import (
    AGENT_EVAL_DATASET_PREFIX,
    AGENT_EVAL_SCHEMA_VERSION,
    AgentEvalError,
    AgentEvalInput,
    AgentEvalOutput,
    AgentEvalReference,
    AgentEvalSelectedEvidence,
    AgentEvalSelection,
)
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.hashes import (
    canonical_dumps,
    case_content_hash,
    sha256_text,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.loader import load_development_cases
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_MOCK_DEFAULT,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
    DatasetSplit,
    EvaluationCase,
)


def select_development_cases(
    *,
    limit: int,
    case_ids: Sequence[str] = (),
    query_classes: Sequence[str] = (),
    holdout_access: HoldoutAccess | None = None,
) -> AgentEvalSelection:
    """Load and bound synthetic development cases. Holdout stays sealed.

    Args:
        limit: Maximum cases. Valid range ``1..20``.
        case_ids: Optional repeatable ids. Every id must be development.
        query_classes: Optional class filters. Unknown classes fail closed.
        holdout_access: Must remain denied even if settings accidentally allow.

    Returns:
        Validated selection with dataset name and stable example ids.

    Raises:
        AgentEvalError: Bounds, split, class, or holdout checks fail.
        OnlineEvalError: Online ceiling checks fail.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise AgentEvalError("holdout_forbidden")
    if limit < 1 or limit > ONLINE_EVAL_MAX_CASES:
        raise AgentEvalError("sample_exceeds_ceiling")
    development = load_development_cases()
    by_id = {case.case_id: case for case in development}
    requested_ids = tuple(dict.fromkeys(case_ids))
    if requested_ids:
        selected: list[EvaluationCase] = []
        for case_id in requested_ids:
            case = by_id.get(case_id)
            if case is None:
                raise AgentEvalError("development_case_required")
            selected.append(case)
    else:
        selected = list(development)
    class_filters = tuple(dict.fromkeys(query_classes))
    if class_filters:
        known = {item.value for item in QueryClass}
        unknown = [item for item in class_filters if item not in known]
        if unknown:
            raise AgentEvalError("unsupported_query_class")
        matching = [
            case for case in selected if case.query_class.value in class_filters
        ]
        present = {case.query_class.value for case in matching}
        missing = [item for item in class_filters if item not in present]
        if missing:
            raise AgentEvalError("unsupported_query_class")
        selected = matching
    if len(selected) < 1:
        raise AgentEvalError("sample_exceeds_ceiling")
    selected = selected[:limit]
    assert_online_eval_permitted(
        mock_mode=ONLINE_EVAL_MOCK_DEFAULT,
        case_count=len(selected),
        max_usd=ONLINE_EVAL_MAX_USD,
        holdout_access=HoldoutAccess.denied(),
        unlimited_openai=False,
    )
    hashes = {case.case_id: case_content_hash(case) for case in selected}
    manifest_hash = selected_manifest_hash(selected)
    dataset_name = agent_eval_dataset_name(manifest_hash)
    example_ids = {
        case.case_id: example_uuid(dataset_name, case.case_id, hashes[case.case_id])
        for case in selected
    }
    return AgentEvalSelection(
        cases=tuple(selected),
        dataset_name=dataset_name,
        manifest_hash=manifest_hash,
        case_hashes=hashes,
        example_ids=example_ids,
        query_class_filters=class_filters,
    )


def selected_manifest_hash(cases: Sequence[EvaluationCase]) -> str:
    """Hash ordered selected case ids and content hashes.

    Args:
        cases: Ordered selected cases.

    Returns:
        SHA-256 hex digest.
    """

    material = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "split": DatasetSplit.DEVELOPMENT.value,
        "case_ids": [case.case_id for case in cases],
        "case_hashes": {case.case_id: case_content_hash(case) for case in cases},
    }
    return sha256_text(canonical_dumps(material))


def agent_eval_dataset_name(manifest_hash: str) -> str:
    """Return the versioned LangSmith dataset name.

    Args:
        manifest_hash: Full SHA-256 of the selected manifest.

    Returns:
        ``smart-rag-agent-eval-{schema}-{labels}-development-{12}``.
    """

    return (
        f"{AGENT_EVAL_DATASET_PREFIX}-{DATASET_SCHEMA_VERSION}-{LABEL_REVISION}"
        f"-development-{manifest_hash[:12]}"
    )


def example_uuid(dataset_name: str, case_id: str, case_hash: str) -> UUID:
    """Return a stable UUIDv5 example id.

    Args:
        dataset_name: Versioned dataset name.
        case_id: Frozen case identifier.
        case_hash: Case content SHA-256.

    Returns:
        UUIDv5 derived from dataset name, case id, and case hash.
    """

    return uuid5(NAMESPACE_URL, f"{dataset_name}:{case_id}:{case_hash}")


def case_to_input(case: EvaluationCase) -> AgentEvalInput:
    """Map one evaluation case to LangSmith example inputs.

    Args:
        case: Synthetic development case.

    Returns:
        Typed input payload.
    """

    return AgentEvalInput(
        case_id=case.case_id,
        query=case.query,
        language=case.language,
        query_class=case.query_class.value,
    )


def case_to_reference(case: EvaluationCase) -> AgentEvalReference:
    """Map one evaluation case to LangSmith reference outputs.

    Args:
        case: Synthetic development case.

    Returns:
        Typed reference payload for deterministic scorers.
    """

    visible_chunks: list[str] = []
    visible_tables: list[str] = []
    forbidden: list[str] = []
    for link in case.evidence_links:
        identifiers = tuple(item for item in (link.chunk_id, link.table_id) if item)
        if link.visible_to_actor:
            if link.chunk_id:
                visible_chunks.append(link.chunk_id)
            if link.table_id:
                visible_tables.append(link.table_id)
        else:
            forbidden.extend(identifiers)
    profile = case.expected_profile
    expected_fields = {
        "language": _profile_value(profile.language.value),
        "query_type": _profile_value(profile.query_type.value),
        "exact_terms": _profile_value(profile.exact_terms.value),
        "codes": _profile_value(profile.codes.value),
        "entities": _profile_value(profile.entities.value),
    }
    return AgentEvalReference(
        acceptable_answers=tuple(case.acceptable_answers),
        expected_route=case.expected_route.value,
        refusal_kind=case.refusal_kind.value,
        visible_chunk_ids=tuple(dict.fromkeys(visible_chunks)),
        visible_table_ids=tuple(dict.fromkeys(visible_tables)),
        forbidden_evidence_ids=tuple(dict.fromkeys(forbidden)),
        expected_profile_fields=expected_fields,
    )


def case_to_example_metadata(
    case: EvaluationCase,
    *,
    case_hash: str,
    manifest_hash: str,
) -> dict[str, object]:
    """Build LangSmith example metadata. No secrets.

    Args:
        case: Synthetic development case.
        case_hash: Case content SHA-256.
        manifest_hash: Selected-set manifest SHA-256.

    Returns:
        Exportable metadata mapping.
    """

    return {
        "schema_version": case.schema_version,
        "label_revision": case.label_revision,
        "split": DatasetSplit.DEVELOPMENT.value,
        "source_family_id": case.source_family_id,
        "query_class": case.query_class.value,
        "language": case.language,
        "redaction_class": case.redaction_class,
        "case_content_hash": case_hash,
        "manifest_hash": manifest_hash,
        "agent_eval_schema_version": AGENT_EVAL_SCHEMA_VERSION,
    }


def failed_target_output(case_id: str, *, failure_kind: str) -> AgentEvalOutput:
    """Return a scored failed target output so LangSmith still records the case.

    Args:
        case_id: Case identifier.
        failure_kind: Named infrastructure failure.

    Returns:
        Output with ``completed=False`` and empty citations.
    """

    return AgentEvalOutput(
        case_id=case_id,
        completed=False,
        failure_kind=failure_kind,
        answer_status="",
    )


def output_from_graph_state(
    case_id: str,
    state: Mapping[str, Any],
    *,
    run_id: str | None = None,
    conversation_id: str | None = None,
    latency_ms: int | None = None,
    agent_cost_usd: str = "0",
    bm25_fallback: str | None = None,
    graph_degraded: bool = False,
) -> AgentEvalOutput:
    """Extract evaluation output from final query-graph state.

    Args:
        case_id: Case identifier.
        state: Final graph state mapping.
        run_id: Application run id.
        conversation_id: Synthetic conversation id.
        latency_ms: End-to-end latency.
        agent_cost_usd: Recorded agent USD.
        bm25_fallback: Named BM25 fallback.
        graph_degraded: Whether graph retrieve was unbound or failed.

    Returns:
        Normalized output. Missing answer fields yield an incomplete row.
    """

    answer = _as_mapping(state.get("answer"))
    fusion = _as_mapping(state.get("fusion"))
    preparation = _as_mapping(state.get("preparation"))
    citations = _as_sequence(answer.get("citations"))
    table_citations = _as_sequence(answer.get("table_citations"))
    cited_chunks = _collect_ids(citations, "chunk_id")
    cited_tables = _collect_ids(citations, "table_id") | _collect_ids(
        table_citations, "table_id"
    )
    evidence_items = _as_sequence(fusion.get("evidence"))
    selected = _collect_ids(evidence_items, "chunk_id")
    selected |= _collect_ids(evidence_items, "table_id")
    selected_evidence = _selected_evidence_records(evidence_items)
    status = str(answer.get("status") or "")
    refusal = None
    if status == "refused":
        refusal = "refused"
    elif status == "partial":
        refusal = "approved_limitation"
    profile_fields = _extract_profile_fields(preparation)
    remaining_model = _optional_int(state.get("remaining_model_calls"))
    completed = bool(answer) and status in {"complete", "partial", "refused"}
    return AgentEvalOutput(
        case_id=case_id,
        run_id=run_id,
        conversation_id=conversation_id,
        completed=completed,
        failure_kind=None if completed else "target_incomplete",
        answer_text=str(answer.get("answer_text") or ""),
        answer_status=status,
        requested_route=_optional_str(state.get("requested_route")),
        effective_route=_optional_str(state.get("effective_route")),
        corrected_route=_optional_str(state.get("corrected_route")),
        cited_chunk_ids=tuple(sorted(cited_chunks)),
        cited_table_ids=tuple(sorted(cited_tables)),
        selected_evidence_ids=tuple(sorted(selected)),
        selected_evidence=selected_evidence,
        refusal_kind=refusal,
        profile_fields=profile_fields,
        remaining_model_calls=remaining_model,
        remaining_tool_calls=_optional_int(state.get("remaining_tool_calls")),
        remaining_corrections=_optional_int(state.get("remaining_corrections")),
        remaining_subquestions=_optional_int(state.get("remaining_subquestions")),
        remaining_recursion_steps=_optional_int(state.get("remaining_recursion_steps")),
        deadline_exceeded=bool(state.get("deadline_exceeded")),
        latency_ms=latency_ms,
        agent_cost_usd=agent_cost_usd,
        bm25_fallback=bm25_fallback,
        graph_degraded=graph_degraded,
    )


def parse_target_output(
    payload: Mapping[str, Any] | AgentEvalOutput,
) -> AgentEvalOutput:
    """Parse a LangSmith target payload into ``AgentEvalOutput``.

    Args:
        payload: Target return mapping or already-typed output.

    Returns:
        Typed output. Unknown mappings become an incomplete failed row.
    """

    if isinstance(payload, AgentEvalOutput):
        return payload
    try:
        return AgentEvalOutput.model_validate(payload)
    except (TypeError, ValueError):
        case_id = str(payload.get("case_id") or "unknown")
        return failed_target_output(case_id, failure_kind="target_output_invalid")


def parse_reference(
    payload: Mapping[str, Any] | AgentEvalReference,
) -> AgentEvalReference:
    """Parse a LangSmith example reference into ``AgentEvalReference``.

    Args:
        payload: Example outputs mapping or already-typed reference.

    Returns:
        Typed reference.

    Raises:
        AgentEvalError: When the reference cannot be validated.
    """

    if isinstance(payload, AgentEvalReference):
        return payload
    try:
        return AgentEvalReference.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise AgentEvalError("reference_invalid") from exc


def _selected_evidence_records(
    items: Sequence[Any],
) -> tuple[AgentEvalSelectedEvidence, ...]:
    """Build at most twelve id-plus-excerpt records from fusion evidence.

    Args:
        items: Fusion evidence mappings.

    Returns:
        Bounded synthetic evidence records. Excerpts are capped at 600
        characters. Duplicate identifiers are dropped.
    """

    records: list[AgentEvalSelectedEvidence] = []
    seen: set[str] = set()
    for item in items:
        mapping = _as_mapping(item)
        identifier = mapping.get("chunk_id") or mapping.get("table_id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            continue
        seen.add(identifier)
        excerpt = str(mapping.get("citation_text") or "")[:600]
        records.append(
            AgentEvalSelectedEvidence(evidence_id=identifier, excerpt=excerpt)
        )
        if len(records) >= 12:
            break
    return tuple(records)


def _profile_value(value: object) -> object:
    """Return a JSON-compatible profile value.

    Args:
        value: Profile field value.

    Returns:
        Lists copied as tuples of strings when possible.
    """

    if isinstance(value, list):
        return tuple(str(item) for item in cast(list[object], value))
    return value


def _extract_profile_fields(preparation: Mapping[str, Any]) -> dict[str, object]:
    """Extract comparable profile fields from graph preparation.

    Args:
        preparation: Preparation mapping.

    Returns:
        Mapping of stable field names to values.
    """

    nested = _as_mapping(preparation.get("profile"))
    source = nested or preparation
    fields: dict[str, object] = {}
    for key in ("language", "query_type", "exact_terms", "codes", "entities"):
        if key in source:
            value = source[key]
            if isinstance(value, Mapping) and "value" in value:
                wrapped = cast(Mapping[str, object], value)
                fields[key] = _profile_value(wrapped["value"])
            else:
                fields[key] = _profile_value(cast(object, value))
    return fields


def _as_mapping(value: object) -> dict[str, Any]:
    """Return a mapping or an empty dict.

    Args:
        value: Candidate mapping.

    Returns:
        String-keyed dict.
    """

    if isinstance(value, Mapping):
        typed = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed.items()}
    return {}


def _as_sequence(value: object) -> tuple[Any, ...]:
    """Return a tuple for a sequence, else empty.

    Args:
        value: Candidate sequence.

    Returns:
        Tuple of items.
    """

    if isinstance(value, (str, bytes)):
        return ()
    if isinstance(value, Sequence):
        return tuple(cast(Sequence[object], value))
    return ()


def _collect_ids(items: Sequence[Any], field: str) -> set[str]:
    """Collect non-empty string identifiers from mappings.

    Args:
        items: Mapping items.
        field: Identifier field name.

    Returns:
        Set of ids.
    """

    found: set[str] = set()
    for item in items:
        mapping = _as_mapping(item)
        raw = mapping.get(field)
        if isinstance(raw, str) and raw:
            found.add(raw)
    return found


def _optional_int(value: object) -> int | None:
    """Parse an optional integer remaining counter.

    Args:
        value: Candidate int.

    Returns:
        Int or None.
    """

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_str(value: object) -> str | None:
    """Return a non-empty string or None.

    Args:
        value: Candidate string.

    Returns:
        String or None.
    """

    if isinstance(value, str) and value:
        return value
    return None
