"""Structured ``aquery_data`` contract models for the pinned LightRAG artifact.

Field names are taken from the installed 1.5.6 ``LightRAG.aquery_data``
docstring. Descriptions, keywords, file paths, and reference ordinals are
accepted as vendor payload members and are never evidence identifiers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from smart_rag_core.retrieval.graph import (
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    DEFAULT_MAX_SOURCE_IDS_PER_RELATION,
    GraphLeadChunk,
    GraphLeadEntity,
    GraphLeadRelation,
    GraphLeadSet,
    SourceIdContractError,
    parse_source_id_list,
)


class LightRagQueryFailure(ValueError):
    """Raised when structured query output is missing or not success."""


class LightRagEntityRecord(BaseModel):
    """Vendor entity object from ``aquery_data`` success ``data.entities``."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    entity_name: str
    entity_type: str | None = None
    description: str | None = None
    source_id: str | None = None
    file_path: str | None = None
    created_at: str | int | float | None = None
    reference_id: str | None = None


class LightRagRelationRecord(BaseModel):
    """Vendor relationship object from ``data.relationships``."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    src_id: str
    tgt_id: str
    description: str | None = None
    keywords: str | None = None
    weight: float | None = None
    source_id: str | None = None
    file_path: str | None = None
    created_at: str | int | float | None = None
    reference_id: str | None = None


class LightRagChunkRecord(BaseModel):
    """Vendor chunk object from ``data.chunks``."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    chunk_id: str
    content: str | None = None
    file_path: str | None = None
    reference_id: str | None = None


class LightRagReferenceRecord(BaseModel):
    """Vendor query-local reference ordinal. Never a citation ID."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    reference_id: str
    file_path: str | None = None


class LightRagKeywordMetadata(BaseModel):
    """Keyword lists echoed in ``metadata.keywords``."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    high_level: tuple[str, ...] = ()
    low_level: tuple[str, ...] = ()


class LightRagQueryMetadata(BaseModel):
    """``metadata`` object from an ``aquery_data`` payload.

    Success uses ``query_mode``. The pin's no-result failure envelope uses
    ``mode`` plus ``failure_reason`` instead.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    query_mode: str | None = None
    mode: str | None = None
    failure_reason: str | None = None
    keywords: LightRagKeywordMetadata | None = None


class LightRagQueryData(BaseModel):
    """``data`` object from a successful ``aquery_data`` payload."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    entities: tuple[LightRagEntityRecord, ...] = ()
    relationships: tuple[LightRagRelationRecord, ...] = ()
    chunks: tuple[LightRagChunkRecord, ...] = ()
    references: tuple[LightRagReferenceRecord, ...] = ()


class LightRagQueryResult(BaseModel):
    """Top-level structured ``aquery_data`` envelope."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    status: Literal["success", "failure"]
    message: str = ""
    data: LightRagQueryData | None = None
    metadata: LightRagQueryMetadata | None = None


def parse_aquery_data_payload(payload: Mapping[str, object]) -> LightRagQueryResult:
    """Validate a vendor ``aquery_data`` mapping into typed models.

    Args:
        payload: Mapping returned by ``LightRAG.aquery_data``.

    Returns:
        Typed result. Callers must still convert leads through
        ``to_graph_leads`` before using source IDs.

    Raises:
        LightRagQueryFailure: If status is not ``success`` or required
            structured fields cannot be validated.
    """

    try:
        result = LightRagQueryResult.model_validate(dict(payload))
    except ValidationError as exc:
        raise LightRagQueryFailure("aquery_data_shape_invalid") from exc
    if result.status != "success":
        reason = result.message or "aquery_data_failure"
        if result.metadata is not None and result.metadata.failure_reason:
            reason = f"{reason}:{result.metadata.failure_reason}"
        raise LightRagQueryFailure(reason)
    return result


def to_graph_leads(result: LightRagQueryResult) -> GraphLeadSet:
    """Convert structured vendor data into application lead objects.

    Description, keywords, file_path, and reference_id fields are ignored as
    identifiers. Source-id lists that hit the retention cap are dropped.

    Args:
        result: Successful structured query result.

    Returns:
        Application lead set with only qualified machine fields.

    Raises:
        LightRagQueryFailure: If ``data`` or ``metadata`` is missing.
    """

    if result.data is None or result.metadata is None:
        raise LightRagQueryFailure("aquery_data_missing_data")
    entities: list[GraphLeadEntity] = []
    for item in result.data.entities:
        source_ids = _optional_source_ids(
            item.source_id, limit=DEFAULT_MAX_SOURCE_IDS_PER_ENTITY
        )
        entities.append(
            GraphLeadEntity(
                entity_name=item.entity_name,
                entity_type=item.entity_type,
                source_ids=source_ids,
            )
        )
    relations: list[GraphLeadRelation] = []
    for item in result.data.relationships:
        source_ids = _optional_source_ids(
            item.source_id, limit=DEFAULT_MAX_SOURCE_IDS_PER_RELATION
        )
        relations.append(
            GraphLeadRelation(
                src_id=item.src_id,
                tgt_id=item.tgt_id,
                source_ids=source_ids,
            )
        )
    chunks = tuple(
        GraphLeadChunk(chunk_id=item.chunk_id) for item in result.data.chunks
    )
    keywords = result.metadata.keywords or LightRagKeywordMetadata()
    mode = result.metadata.query_mode or result.metadata.mode
    lead_mode: Literal["local", "hybrid", "global"]
    if mode == "local":
        lead_mode = "local"
    elif mode == "hybrid":
        lead_mode = "hybrid"
    elif mode == "global":
        lead_mode = "global"
    else:
        raise LightRagQueryFailure(f"unsupported_query_mode:{mode}")
    return GraphLeadSet(
        mode=lead_mode,
        entities=tuple(entities),
        relations=tuple(relations),
        chunks=chunks,
        high_level_keywords=tuple(keywords.high_level),
        low_level_keywords=tuple(keywords.low_level),
    )


def _optional_source_ids(raw: str | None, *, limit: int) -> tuple[str, ...]:
    """Parse source IDs or return empty when the vendor omitted them.

    Args:
        raw: Delimiter-joined source list.
        limit: Retention cap.

    Returns:
        Parsed tokens, or empty when unavailable.

    Raises:
        LightRagQueryFailure: If tokens are present but ambiguous/truncated.
    """

    if raw is None or not raw.strip():
        return ()
    try:
        return parse_source_id_list(raw, limit=limit)
    except SourceIdContractError as exc:
        raise LightRagQueryFailure(str(exc)) from exc


def as_string_mapping(payload: object) -> Mapping[str, object]:
    """Narrow a vendor dict to ``Mapping[str, object]``.

    Args:
        payload: Value returned by ``aquery_data``.

    Returns:
        String-keyed mapping.

    Raises:
        LightRagQueryFailure: If the payload is not a mapping.
    """

    if not isinstance(payload, Mapping):
        raise LightRagQueryFailure("aquery_data_not_mapping")
    untyped = cast(Mapping[object, object], payload)
    if not all(isinstance(key, str) for key in untyped):
        raise LightRagQueryFailure("aquery_data_non_string_keys")
    return cast(Mapping[str, object], untyped)


def sequence_of_str(value: object) -> tuple[str, ...]:
    """Validate a string sequence from vendor metadata.

    Args:
        value: Untyped vendor list.

    Returns:
        Tuple of strings.

    Raises:
        LightRagQueryFailure: If a non-string item is present.
    """

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise LightRagQueryFailure("expected_string_sequence")
    items: list[str] = []
    for raw_item in cast(Sequence[object], value):
        if not isinstance(raw_item, str):
            raise LightRagQueryFailure("expected_string_sequence")
        items.append(raw_item)
    return tuple(items)
