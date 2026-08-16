"""Versioned LightRAG extraction policy hash used in mapping generations.

The pipeline pin ``graph_pipeline_v1`` is never rewritten here. Entity-rule
and extraction-policy changes bump ``entity_rules_generation`` instead of
mixing embeddings in place.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from smart_rag_core.jobs.limits import GRAPH_PIPELINE_VERSION

DEFAULT_ALLOWED_ENTITY_TYPES: tuple[str, ...] = (
    "CONCEPT",
    "EVENT",
    "LOCATION",
    "ORG",
    "ORGANIZATION",
    "PERSON",
    "PRODUCT",
    "PROJECT",
)
DEFAULT_ALLOWED_LANGUAGES: tuple[str, ...] = ("ar", "en", "mixed")
DEFAULT_ENTITY_EXTRACT_MAX_GLEANING = 0
DEFAULT_JSON_MODE = True
DEFAULT_RELATION_LABEL_POLICY = "directed"
EXTRACTION_POLICY_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_EXTRACTION_POLICY_HASH = (
    "b8719e2481b2f8ed85be76d13e19c092428e92ffdf3d36bcd5e5e9656c65bd08"
)


@dataclass(frozen=True, slots=True)
class ExtractionPolicySnapshot:
    """Durable extraction/entity-rule generation used at map and query time.

    Attributes:
        entity_rules_generation: Monotonic approved-rule generation.
        extraction_policy_hash: SHA-256 of allowed types/languages/gleaning.
        allowed_entity_types: Uppercase application entity types.
        allowed_languages: ``en``, ``ar``, and/or ``mixed``.
        entity_extract_max_gleaning: LightRAG gleaning cap (0-3).
        json_mode: Structured JSON extraction required.
        relation_label_policy: ``directed`` or ``symmetric``.
    """

    entity_rules_generation: int = 1
    extraction_policy_hash: str = ""
    allowed_entity_types: tuple[str, ...] = DEFAULT_ALLOWED_ENTITY_TYPES
    allowed_languages: tuple[str, ...] = DEFAULT_ALLOWED_LANGUAGES
    entity_extract_max_gleaning: int = DEFAULT_ENTITY_EXTRACT_MAX_GLEANING
    json_mode: bool = DEFAULT_JSON_MODE
    relation_label_policy: str = DEFAULT_RELATION_LABEL_POLICY


def hash_extraction_policy(
    *,
    allowed_entity_types: Sequence[str] = DEFAULT_ALLOWED_ENTITY_TYPES,
    allowed_languages: Sequence[str] = DEFAULT_ALLOWED_LANGUAGES,
    entity_extract_max_gleaning: int = DEFAULT_ENTITY_EXTRACT_MAX_GLEANING,
    json_mode: bool = DEFAULT_JSON_MODE,
    relation_label_policy: str = DEFAULT_RELATION_LABEL_POLICY,
) -> str:
    """Hash the application extraction overlay. Never mutates vendor graphs.

    Args:
        allowed_entity_types: Permitted entity types for rules and extraction.
        allowed_languages: Permitted extraction languages.
        entity_extract_max_gleaning: Bounded gleaning iterations.
        json_mode: Whether JSON-mode extraction is required.
        relation_label_policy: Directed or symmetric statement identity.

    Returns:
        Lowercase SHA-256 hex digest.

    Raises:
        ValueError: If gleaning is outside ``0..3``.
    """

    if entity_extract_max_gleaning < 0 or entity_extract_max_gleaning > 3:
        raise ValueError("gleaning_out_of_bounds")
    payload: dict[str, object] = {
        "allowed_entity_types": sorted(
            {item.strip().upper() for item in allowed_entity_types}
        ),
        "allowed_languages": sorted({item.strip() for item in allowed_languages}),
        "entity_extract_max_gleaning": entity_extract_max_gleaning,
        "json_mode": json_mode,
        "pipeline": GRAPH_PIPELINE_VERSION,
        "relation_label_policy": relation_label_policy,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def default_extraction_policy() -> ExtractionPolicySnapshot:
    """Return the pinned default policy with generation ``1``.

    Returns:
        Snapshot whose hash matches ``DEFAULT_EXTRACTION_POLICY_HASH``.
    """

    digest = hash_extraction_policy()
    return ExtractionPolicySnapshot(
        entity_rules_generation=1,
        extraction_policy_hash=digest,
        allowed_entity_types=DEFAULT_ALLOWED_ENTITY_TYPES,
        allowed_languages=DEFAULT_ALLOWED_LANGUAGES,
        entity_extract_max_gleaning=DEFAULT_ENTITY_EXTRACT_MAX_GLEANING,
        json_mode=DEFAULT_JSON_MODE,
        relation_label_policy=DEFAULT_RELATION_LABEL_POLICY,
    )


def policy_from_row(row: Mapping[str, object]) -> ExtractionPolicySnapshot:
    """Build a snapshot from a ``graph_extraction_policy`` mapping.

    Args:
        row: Database row or cursor mapping.

    Returns:
        Typed snapshot. Missing keys fall back to defaults.
    """

    types_raw = row.get("allowed_entity_types") or DEFAULT_ALLOWED_ENTITY_TYPES
    langs_raw = row.get("allowed_languages") or DEFAULT_ALLOWED_LANGUAGES
    return ExtractionPolicySnapshot(
        entity_rules_generation=_as_int(row.get("entity_rules_generation") or 1),
        extraction_policy_hash=str(row.get("extraction_policy_hash") or ""),
        allowed_entity_types=_as_str_tuple(types_raw),
        allowed_languages=_as_str_tuple(langs_raw),
        entity_extract_max_gleaning=_as_int(
            row.get("entity_extract_max_gleaning")
            or DEFAULT_ENTITY_EXTRACT_MAX_GLEANING
        ),
        json_mode=bool(row.get("json_mode", DEFAULT_JSON_MODE)),
        relation_label_policy=str(
            row.get("relation_label_policy") or DEFAULT_RELATION_LABEL_POLICY
        ),
    )


def _as_int(value: object) -> int:
    """Coerce a policy numeric column to int.

    Args:
        value: Database number, numeric string, or already an int.

    Returns:
        Integer form of ``value``.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return int(str(value))


def _as_str_tuple(value: object) -> tuple[str, ...]:
    """Return string items from a JSON/list column.

    Args:
        value: Database array, JSON list, or fallback tuple.

    Returns:
        Tuple of stringified items.
    """

    items = cast(Sequence[object], value)
    return tuple(str(item) for item in items)
