"""Bounded summary operation through the application model gateway."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.gateways.openai_answer import (
    OpenAIAnswerError,
    parse_structured_response,
)
from smart_rag_core.memory.preferences import PreferenceUpdate
from smart_rag_core.memory.versions import SUMMARY_PROMPT_SHA256
from smart_rag_core.models.env_pins import ALLOWED_SUMMARY_MODEL_IDS, SUMMARY_MODEL_ID
from smart_rag_core.observability.langsmith_tracing import traced_openai_client


class SummaryModelRequest(BaseModel):
    """Conversation data is untrusted; no tools, documents, or retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    messages: str = Field(min_length=1, max_length=12_000)
    previous_summary: str = Field(default="", max_length=2000)
    previous_preferences: str = Field(default="{}", max_length=1000)
    prompt_text: str = Field(min_length=1, max_length=12_000)
    prompt_version: Literal["summary_v4"] = "summary_v4"
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_id: str = SUMMARY_MODEL_ID
    remaining_deadline_seconds: float = Field(gt=0, le=6)


class SummaryModelResponse(BaseModel):
    """Compact prose and actual provider usage, never source bodies."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    summary: str = Field(min_length=1, max_length=1400)
    preference_updates: tuple[PreferenceUpdate, ...] = Field(default=(), max_length=4)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


def execute_summary(api_key: str, request: SummaryModelRequest) -> SummaryModelResponse:
    """One Responses call, no hidden retries, bounded structured output."""
    from openai import APIError, omit

    if request.model_id not in ALLOWED_SUMMARY_MODEL_IDS:
        raise OpenAIAnswerError("summary_model_invalid")
    if (
        request.prompt_sha256 != SUMMARY_PROMPT_SHA256
        or sha256(request.prompt_text.encode()).hexdigest() != request.prompt_sha256
    ):
        raise OpenAIAnswerError("summary_prompt_invalid")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=request.remaining_deadline_seconds
    )
    try:
        response = client.responses.create(
            model=request.model_id,
            instructions=request.prompt_text,
            input=json.dumps(
                {
                    "previous_summary": request.previous_summary,
                    "previous_preferences": request.previous_preferences,
                    "messages": request.messages,
                },
                ensure_ascii=False,
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "conversation_summary",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["summary", "preference_updates"],
                        "properties": {
                            "summary": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1400,
                            },
                            "preference_updates": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["key", "value", "user_quote"],
                                    "properties": {
                                        "key": {
                                            "type": "string",
                                            "pattern": "^[a-z][a-z0-9_]{0,39}$",
                                        },
                                        "value": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 100,
                                        },
                                        "user_quote": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 180,
                                        },
                                    },
                                },
                            },
                        },
                    },
                }
            },
            max_output_tokens=900,
            reasoning={"effort": "low"} if request.model_id == "gpt-6-luna" else omit,
            store=False,
        )
    except APIError as exc:
        raise OpenAIAnswerError("summary_provider_failed") from exc
    payload, _, prompt, completion = parse_structured_response(response, kind="summary")
    return SummaryModelResponse.model_validate(
        {
            "summary": payload.get("summary"),
            "preference_updates": payload.get("preference_updates", []),
            "input_tokens": prompt,
            "output_tokens": completion,
        }
    )
