"""Closed provider verdict map: exactly one verdict per requested link."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_answer.versions import MAX_VERIFIER_LINKS

VERIFIER_REASON_CODES = (
    "supported",
    "unsupported",
    "literal_mismatch",
    "invalid_inference",
    "insufficient_evidence",
)


def keyed_verifier_schema(link_ids: tuple[str, ...]) -> dict[str, object]:
    """Build required object keys instead of an array permitting duplicates.

    Args:
        link_ids: Unique requested atomic links, at most six.

    Returns:
        A strict schema with no omitted, duplicate, or foreign verdict IDs.

    Raises:
        ValueError: If the requested batch is malformed.
    """
    if (
        not link_ids
        or len(link_ids) > MAX_VERIFIER_LINKS
        or len(set(link_ids)) != len(link_ids)
        or any(not item.strip() for item in link_ids)
    ):
        raise ValueError("verifier_batch_invalid")
    verdict = {
        "type": "object",
        "additionalProperties": False,
        "required": ["supported", "reason"],
        "properties": {
            "supported": {"type": "boolean"},
            "reason": {"type": "string", "enum": list(VERIFIER_REASON_CODES)},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["link_verdicts"],
        "properties": {
            "link_verdicts": {
                "type": "object",
                "additionalProperties": False,
                "required": list(link_ids),
                "properties": {key: verdict for key in link_ids},
            }
        },
    }


def normalize_keyed_verdicts(
    payload: dict[str, object], link_ids: tuple[str, ...]
) -> dict[str, object]:
    """Translate the provider map to the established internal verdict list.

    Args:
        payload: Parsed provider JSON, never trusted as authorization.
        link_ids: Exact requested IDs and their stable output order.

    Returns:
        Internal list shape without inventing a support flag or verdict.

    Raises:
        ValueError: If any verdict is absent, foreign, or malformed.
    """
    raw = payload.get("link_verdicts")
    if not isinstance(raw, dict):
        raise ValueError("verifier_verdict_mismatch")
    mapped = cast(dict[str, object], raw)
    if set(mapped) != set(link_ids):
        raise ValueError("verifier_verdict_mismatch")
    verdicts: list[dict[str, object]] = []
    for link_id in link_ids:
        item = mapped[link_id]
        if not isinstance(item, dict):
            raise ValueError("verifier_schema_invalid")
        item = cast(dict[str, object], item)
        if (
            set(item) != {"supported", "reason"}
            or not isinstance(item.get("supported"), bool)
            or not isinstance(item.get("reason"), str)
            or item["reason"] not in VERIFIER_REASON_CODES
            or item["supported"] != (item["reason"] == "supported")
        ):
            raise ValueError("verifier_schema_invalid")
        verdicts.append({"link_id": link_id, **item})
    return {"link_verdicts": verdicts}
