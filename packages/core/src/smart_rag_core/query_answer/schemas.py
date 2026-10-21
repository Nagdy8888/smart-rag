"""JSON Schema documents for answer and verifier Responses calls."""

from __future__ import annotations

from smart_rag_core.query_answer.verifier_output import keyed_verifier_schema
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_ANSWER_PARAGRAPHS,
    MAX_CITATION_SPAN_CHARS,
    MAX_CLAIM_CITATIONS,
    MAX_VERIFIER_LINKS,
)


def answer_json_schema() -> dict[str, object]:
    """Return the historical ``answer_v3`` structured-output schema.

    Live answer calls send :func:`answer_claims_json_schema`. This schema
    stays so a rollback to ``answer_v3`` needs only the version pins.
    Provider output omits ``answer_text``. Application code releases
    surviving atomic-link claims after verification.

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
            "paragraph_index",
        ],
        "properties": {
            "chunk_id": {"type": ["string", "null"]},
            "table_id": {"type": ["string", "null"]},
            "span": {
                "type": ["string", "null"],
                "maxLength": MAX_CITATION_SPAN_CHARS,
            },
            "source_ranges": {"type": "array", "items": {"type": "string"}},
            "inference": {"type": "boolean"},
            "atomic_link_id": {"type": ["string", "null"]},
            "paragraph_index": {"type": ["integer", "null"]},
        },
    }
    paragraph = {
        "type": "object",
        "additionalProperties": False,
        "required": ["paragraph_index", "text", "link_ids"],
        "properties": {
            "paragraph_index": {"type": "integer", "minimum": 0, "maximum": 5},
            "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            "link_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_VERIFIER_LINKS,
                "items": {"type": "string"},
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "paragraphs",
            "citations",
            "atomic_links",
            "composed_conclusion",
            "table_citations",
            "status",
            "refused_links",
        ],
        "properties": {
            "paragraphs": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_ANSWER_PARAGRAPHS,
                "items": paragraph,
            },
            "citations": {
                "type": "array",
                "maxItems": MAX_ANSWER_CITATIONS,
                "items": citation,
            },
            "atomic_links": {
                "type": "array",
                "maxItems": MAX_VERIFIER_LINKS,
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
            "table_citations": {
                "type": "array",
                "maxItems": MAX_ANSWER_CITATIONS,
                "items": citation,
            },
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "refused"],
            },
            "refused_links": {"type": "array", "items": {"type": "string"}},
        },
    }


def answer_claims_json_schema(
    *, max_claims: int = MAX_VERIFIER_LINKS
) -> dict[str, object]:
    """Return the strict answer claims structured-output schema.

    The bounded claim limit may reserve room for a requested artifact.
    ``source_id`` is a plain string; application code
    drops any citation whose ID was not sent in the request. Length caps
    are enforced by application code, not by string keywords.

    Args:
        max_claims: Existing six-claim ceiling, or a lower artifact reservation.

    Returns:
        OpenAI ``json_schema`` document. The model writes no link IDs,
        paragraph indices, or ``answer_text``.

    Raises:
        ValueError: When the requested limit exceeds the existing ceiling.
    """

    if not 0 <= max_claims <= MAX_VERIFIER_LINKS:
        raise ValueError("answer_claim_limit_invalid")
    citation = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_id", "span", "source_ranges"],
        "properties": {
            "source_id": {"type": "string"},
            "span": {"type": "string"},
            "source_ranges": {"type": "array", "items": {"type": "string"}},
        },
    }
    claim = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "kind", "citations"],
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["fact", "inference_link"]},
            "citations": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CLAIM_CITATIONS,
                "items": citation,
            },
        },
    }
    conclusion = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "claim_numbers"],
        "properties": {
            "text": {"type": "string"},
            "claim_numbers": {"type": "array", "items": {"type": "integer"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["claims", "conclusion", "status"],
        "properties": {
            "claims": {
                "type": "array",
                "maxItems": max_claims,
                "items": claim,
            },
            "conclusion": {"anyOf": [{"type": "null"}, conclusion]},
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "refused"],
            },
        },
    }


def general_chat_json_schema() -> dict[str, object]:
    """Return the strict no-source general-chat schema.

    Returns:
        OpenAI ``json_schema`` document with ``answer_text`` and ``status``
        only. Citations and source IDs are omitted.
    """

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer_text", "status"],
        "properties": {
            "answer_text": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "refused"],
            },
        },
    }


def web_answer_json_schema() -> dict[str, object]:
    """Return the strict Web-research synthesis schema.

    Returns:
        OpenAI ``json_schema`` document with ``answer_text``, ``status``,
        ``web_citations``, and ``atomic_links``. Company citation lists
        are omitted from the provider contract.
    """

    web_citation = {
        "type": "object",
        "additionalProperties": False,
        "required": ["web_source_id", "span"],
        "properties": {
            "web_source_id": {"type": "string", "minLength": 1, "maxLength": 36},
            "span": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_CITATION_SPAN_CHARS,
            },
        },
    }
    atomic_link = {
        "type": "object",
        "additionalProperties": False,
        "required": ["link_id", "claim", "web_source_ids"],
        "properties": {
            "link_id": {"type": "string", "minLength": 1, "maxLength": 64},
            "claim": {"type": "string", "minLength": 1, "maxLength": 2000},
            "web_source_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CLAIM_CITATIONS,
                "items": {"type": "string", "minLength": 1, "maxLength": 36},
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer_text", "status", "web_citations", "atomic_links"],
        "properties": {
            "answer_text": {"type": "string", "maxLength": 16_384},
            "status": {
                "type": "string",
                "enum": ["complete", "partial", "refused"],
            },
            "web_citations": {
                "type": "array",
                "maxItems": MAX_ANSWER_CITATIONS,
                "items": web_citation,
            },
            "atomic_links": {
                "type": "array",
                "maxItems": MAX_VERIFIER_LINKS,
                "items": atomic_link,
            },
        },
    }


def verifier_json_schema(link_ids: tuple[str, ...]) -> dict[str, object]:
    """Return the strict verifier schema bound to supplied link IDs.

    Args:
        link_ids: Batch of at most six link IDs.

    Returns:
        OpenAI ``json_schema`` document.
    """

    return keyed_verifier_schema(link_ids)


def eval_judge_json_schema() -> dict[str, object]:
    """Return the strict synthetic-eval judge schema.

    Returns:
        OpenAI ``json_schema`` document.
    """

    unit = {"type": "number", "minimum": 0, "maximum": 1}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "correctness",
            "groundedness",
            "refusal_quality",
            "rationale",
        ],
        "properties": {
            "correctness": unit,
            "groundedness": unit,
            "refusal_quality": unit,
            "rationale": {"type": "string", "maxLength": 240},
        },
    }


def pdf_eval_judge_json_schema() -> dict[str, object]:
    """Return the strict private-PDF judge schema.

    Returns:
        OpenAI ``json_schema`` document. Distinct from the synthetic judge.
    """

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "faithfulness", "claim_support"],
        "properties": {
            "status": {"type": "string", "enum": ["complete", "unscored"]},
            "faithfulness": {"type": "number", "minimum": 0, "maximum": 1},
            "claim_support": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["supported"],
                    "properties": {"supported": {"type": "boolean"}},
                },
            },
        },
    }
