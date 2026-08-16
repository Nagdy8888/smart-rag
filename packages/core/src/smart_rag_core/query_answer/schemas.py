"""JSON Schema documents for answer and verifier Responses calls."""

from __future__ import annotations

from smart_rag_core.query_answer.versions import MAX_VERIFIER_LINKS


def answer_json_schema() -> dict[str, object]:
    """Return the strict answer structured-output schema.

    Returns:
        OpenAI ``json_schema`` document.
    """

    citation = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "chunk_id",
            "table_id",
            "span",
            "source_ranges",
            "inference",
            "atomic_link_id",
        ],
        "properties": {
            "chunk_id": {"type": ["string", "null"]},
            "table_id": {"type": ["string", "null"]},
            "span": {"type": ["string", "null"]},
            "source_ranges": {"type": "array", "items": {"type": "string"}},
            "inference": {"type": "boolean"},
            "atomic_link_id": {"type": ["string", "null"]},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "answer_text",
            "citations",
            "atomic_links",
            "composed_conclusion",
            "table_citations",
            "status",
            "refused_links",
        ],
        "properties": {
            "answer_text": {"type": "string"},
            "citations": {"type": "array", "items": citation},
            "atomic_links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "link_id",
                        "claim",
                        "chunk_ids",
                        "table_id",
                        "source_ranges",
                        "kind",
                        "priority",
                    ],
                    "properties": {
                        "link_id": {"type": "string"},
                        "claim": {"type": "string"},
                        "chunk_ids": {"type": "array", "items": {"type": "string"}},
                        "table_id": {"type": ["string", "null"]},
                        "source_ranges": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "kind": {"type": "string", "enum": ["fact", "inference_link"]},
                        "priority": {"type": "integer"},
                    },
                },
            },
            "composed_conclusion": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["text", "kind", "link_ids"],
                        "properties": {
                            "text": {"type": "string"},
                            "kind": {"type": "string", "enum": ["inference"]},
                            "link_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                ]
            },
            "table_citations": {"type": "array", "items": citation},
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "refused"],
            },
            "refused_links": {"type": "array", "items": {"type": "string"}},
        },
    }


def verifier_json_schema(link_ids: tuple[str, ...]) -> dict[str, object]:
    """Return the strict verifier schema bound to supplied link IDs.

    Args:
        link_ids: Batch of at most six link IDs.

    Returns:
        OpenAI ``json_schema`` document.
    """

    enum_ids = list(link_ids) or ["none"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["link_verdicts"],
        "properties": {
            "link_verdicts": {
                "type": "array",
                "maxItems": MAX_VERIFIER_LINKS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["link_id", "supported", "reason"],
                    "properties": {
                        "link_id": {"type": "string", "enum": enum_ids},
                        "supported": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                },
            }
        },
    }
