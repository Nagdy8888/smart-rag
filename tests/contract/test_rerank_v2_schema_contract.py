"""rerank_v2 strict json_schema fits the pinned OpenAI SDK contract (A3)."""

from __future__ import annotations

import importlib.metadata
from typing import cast

from openai.types.responses import ResponseFormatTextJSONSchemaConfigParam
from smart_rag_core.retrieval.profiles import RERANK_POOL_SIZE
from smart_rag_core.retrieval.rerank_labels import (
    rerank_label_json_schema,
    rerank_labels,
)

_STRICT_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
    }
)


def _problems(node: dict[str, object], path: str) -> list[str]:
    """Return strict-mode problems in one schema node and its children.

    Args:
        node: JSON schema object.
        path: Location used in messages.

    Returns:
        Problem descriptions; empty when the node is strict-compatible.
    """

    found = [
        f"{path}: unsupported {key}" for key in node if key not in _STRICT_KEYWORDS
    ]
    if node.get("type") == "object":
        properties = cast(dict[str, dict[str, object]], node.get("properties", {}))
        if node.get("additionalProperties") is not False:
            found.append(f"{path}: additionalProperties must be false")
        if sorted(cast(list[str], node.get("required", []))) != sorted(properties):
            found.append(f"{path}: every property must be required")
        for name, child in properties.items():
            found.extend(_problems(child, f"{path}.{name}"))
    items = node.get("items")
    if isinstance(items, dict):
        found.extend(_problems(cast(dict[str, object], items), f"{path}[]"))
    return found


def test_pinned_openai_sdk_has_the_json_schema_format_keys() -> None:
    """The adapter's ``text.format`` keys exist in the pinned SDK type."""

    assert importlib.metadata.version("openai") == "2.26.0"
    keys = (
        ResponseFormatTextJSONSchemaConfigParam.__required_keys__
        | ResponseFormatTextJSONSchemaConfigParam.__optional_keys__
    )
    assert {"name", "schema", "strict", "type"} <= keys


def test_label_schema_is_strict_compatible_for_every_pool_size() -> None:
    """Every node uses supported keywords, forbids extras, and requires all keys."""

    for count in range(2, RERANK_POOL_SIZE + 1):
        labels = rerank_labels(count)
        schema = rerank_label_json_schema(labels)
        assert _problems(schema, "$") == []
        properties = cast(dict[str, dict[str, object]], schema["properties"])
        assert "input_hash" not in properties
        assert properties["ranking"]["maxItems"] == count
        items = cast(dict[str, object], properties["ranking"]["items"])
        assert items["enum"] == list(labels)
