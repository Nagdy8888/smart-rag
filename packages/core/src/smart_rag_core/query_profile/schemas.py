"""Strict JSON Schema for the one structured query-profile call."""

from __future__ import annotations

_KNOWLEDGE_SCOPES = (
    "general_knowledge",
    "company_documents",
    "user_supplied_text",
    "deterministic",
    "ambiguous",
    "web",
)


def query_profile_json_schema() -> dict[str, object]:
    """Return the strict profile structured-output schema.

    The document covers exactly the ``PreparationModelPayload`` fields.
    ``scope_degradation_reason`` is server-derived and is not in the model
    output.

    Returns:
        OpenAI ``json_schema`` document with ``additionalProperties``
        false and max-three subquestion/variant bounds.
    """

    string_list = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "rewrite",
            "query_type",
            "subquestions",
            "variants",
            "hl_keywords",
            "ll_keywords",
            "retrieval_profile_id",
            "metadata_filters",
            "confidence",
            "relationship_intent",
            "knowledge_scope",
            "knowledge_scope_confidence",
            "requested_sources",
            "clarification_question",
        ],
        "properties": {
            "clarification_question": {
                "type": ["string", "null"],
                "maxLength": 300,
                "description": "One focused question ONLY if missing policy, subject, time, or jurisdiction would materially change the company answer. Otherwise null. Do not invent company facts, source names, countries, or choices. Do not ask for secrets. Do not clarify ordinary answerable questions.",
            },
            "rewrite": {"type": ["string", "null"]},
            "query_type": {"type": ["string", "null"]},
            "subquestions": {**string_list, "maxItems": 3},
            "variants": {**string_list, "maxItems": 3},
            "hl_keywords": {**string_list, "maxItems": 12},
            "ll_keywords": {**string_list, "maxItems": 12},
            "retrieval_profile_id": {"type": ["string", "null"]},
            "metadata_filters": {**string_list, "maxItems": 8},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "relationship_intent": {"type": ["boolean", "null"]},
            "knowledge_scope": {
                "anyOf": [
                    {"type": "string", "enum": list(_KNOWLEDGE_SCOPES)},
                    {"type": "null"},
                ]
            },
            "knowledge_scope_confidence": {
                "anyOf": [
                    {"type": "number", "minimum": 0, "maximum": 1},
                    {"type": "null"},
                ]
            },
            "requested_sources": {**string_list, "maxItems": 8},
        },
    }
