"""``rerank_v2`` label contract: labels, strict schema, and validation.

The model sees pool-order labels (``c01`` to ``c20``) instead of chunk
UUIDs and returns an ordered label array plus per-label support. The
server maps labels back to the supplied IDs. The model never echoes an
input hash; the OpenAI adapter still computes and traces it.
"""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from smart_rag_core.retrieval.profiles import RERANK_POOL_SIZE
from smart_rag_core.retrieval.rerank import RerankPayloadError, RerankRanking
from smart_rag_core.retrieval.rerank_versions import RERANK_LABEL_PREFIX


def rerank_labels(count: int) -> tuple[str, ...]:
    """Return pool-order candidate labels for one rerank request.

    Args:
        count: Pool size, from 2 to ``RERANK_POOL_SIZE``.

    Returns:
        ``("c01", "c02", ...)`` with ``count`` entries.

    Raises:
        ValueError: ``rerank_pool_size_invalid`` when ``count`` is out of range.
    """

    if count < 2 or count > RERANK_POOL_SIZE:
        raise ValueError("rerank_pool_size_invalid")
    return tuple(f"{RERANK_LABEL_PREFIX}{index:02d}" for index in range(1, count + 1))


def rerank_label_json_schema(labels: tuple[str, ...]) -> dict[str, object]:
    """Build the strict ``rerank_v2`` JSON schema for one pool size.

    Only keywords that OpenAI strict mode supports are used: ``type``,
    ``enum``, ``properties``, ``required``, ``additionalProperties``,
    ``items``, ``minItems``, ``maxItems``, ``minimum``, and ``maximum``.
    The schema depends only on ``len(labels)``, so repeated pool sizes
    reuse the same schema.

    Args:
        labels: Output of ``rerank_labels``.

    Returns:
        JSON schema object with ``status``, ``ranking``, and ``support``.
    """

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "ranking", "support"],
        "properties": {
            "status": {"type": "string", "enum": ["complete"]},
            "ranking": {
                "type": "array",
                "minItems": 1,
                "maxItems": len(labels),
                "items": {"type": "string", "enum": list(labels)},
            },
            "support": {
                "type": "object",
                "additionalProperties": False,
                "required": list(labels),
                "properties": {
                    label: {"type": "number", "minimum": 0, "maximum": 1}
                    for label in labels
                },
            },
        },
    }


class RerankLabelPayloadModel(BaseModel):
    """Parsed ``rerank_v2`` payload before label mapping.

    Attributes:
        status: Must be ``complete``.
        ranking: Labels best first. Duplicates and unknown labels are
            resolved by ``validate_rerank_label_payload``.
        support: Label to ranking feature in ``[0, 1]``. Not a probability.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["complete"]
    ranking: list[str]
    support: dict[str, float]

    @field_validator("support", mode="before")
    @classmethod
    def reject_invalid_support(cls, value: object) -> object:
        """Reject boolean or out-of-range support values.

        Args:
            value: Raw ``support`` field.

        Returns:
            The unchanged value. Non-dict input is left to type validation.

        Raises:
            ValueError: ``rerank_support_invalid`` for a boolean, or
                ``rerank_support_out_of_bounds`` outside ``[0, 1]``.
        """

        if not isinstance(value, dict):
            return value
        for item in cast(dict[object, object], value).values():
            if isinstance(item, bool):
                raise ValueError("rerank_support_invalid")
            if isinstance(item, int | float) and (item < 0.0 or item > 1.0):
                raise ValueError("rerank_support_out_of_bounds")
        return cast(object, value)


def validate_rerank_label_payload(
    payload: object,
    *,
    candidate_ids: tuple[UUID, ...],
) -> tuple[RerankRanking, ...]:
    """Map a ``rerank_v2`` payload to rankings that cover the whole pool.

    The first occurrence of each supplied label wins. Duplicate and unknown
    labels are ignored. Unranked candidates are appended in pool order with
    support ``0.0`` and ``appended=True``. Ranks run from 1 to the pool size.

    Args:
        payload: Parsed provider JSON object.
        candidate_ids: Supplied chunk IDs in pool order (label order).

    Returns:
        One ranking per candidate, best first.

    Raises:
        RerankPayloadError: ``json`` when the payload fails the shape
            check, ``length`` when ``ranking`` is empty, ``unknown_id``
            when no ranked label was supplied.
        ValueError: ``rerank_pool_size_invalid`` for a pool outside
            2..``RERANK_POOL_SIZE``.
    """

    labels = rerank_labels(len(candidate_ids))
    try:
        body = RerankLabelPayloadModel.model_validate(payload)
    except ValidationError as error:
        raise RerankPayloadError("rerank_schema_invalid", subcode="json") from error
    if not body.ranking:
        raise RerankPayloadError("rerank_ranking_length", subcode="length")
    by_label = dict(zip(labels, candidate_ids, strict=True))
    order: list[str] = []
    for label in body.ranking:
        if label in by_label and label not in order:
            order.append(label)
    if not order:
        raise RerankPayloadError("rerank_unknown_or_missing_id", subcode="unknown_id")
    rows = [
        RerankRanking(
            chunk_id=by_label[label],
            rank=rank,
            support=float(body.support.get(label, 0.0)),
        )
        for rank, label in enumerate(order, start=1)
    ]
    for label in labels:
        if label not in order:
            rows.append(
                RerankRanking(
                    chunk_id=by_label[label],
                    rank=len(rows) + 1,
                    support=0.0,
                    appended=True,
                )
            )
    return tuple(rows)
