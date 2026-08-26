"""Allow-listed SSE event types, intervals, and extra=forbid payloads."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

HEARTBEAT_INTERVAL_SECONDS: Final[int] = 15
"""Production SSE heartbeat interval. Tests may inject a shorter clock only
when they also assert this constant remains 15."""

ALLOWED_SSE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "status",
        "tool_progress",
        "heartbeat",
        "route_correction",
        "limitation",
        "deadline",
        "partial",
        "cache",
        "coverage",
        "optional_tool_disclosure",
        "citation_preview",
        "answer_origin",
        "token_delta",
        "usage",
        "completed",
        "cancelled",
        "error",
    }
)

TERMINAL_SSE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"completed", "cancelled", "error", "partial"}
)

FORBIDDEN_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "passage",
        "snippet",
        "html",
        "traceback",
        "exception",
        "stack",
        "stacktrace",
        "source_html",
        "retrieved_text",
        "page_content",
        "content_html",
        "secret",
        "password",
        "api_key",
        "token",
    }
)

SseProgressPhase = Literal["started", "completed", "failed"]


SseEventType = Literal[
    "schema",
    "status",
    "tool_progress",
    "heartbeat",
    "route_correction",
    "limitation",
    "deadline",
    "partial",
    "cache",
    "coverage",
    "optional_tool_disclosure",
    "citation_preview",
    "answer_origin",
    "token_delta",
    "usage",
    "completed",
    "cancelled",
    "error",
]


class _SsePayload(BaseModel):
    """Base extra=forbid payload for allow-listed SSE events."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SchemaPayload(_SsePayload):
    """First event on every new stream."""

    sse_schema_version: str = Field(min_length=1, max_length=32)


class StatusPayload(_SsePayload):
    """Stage/status without retrieved text.

    ``phase`` is optional so persisted legacy rows without it still replay.
    """

    stage: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=64)
    phase: SseProgressPhase | None = None


class ToolProgressPayload(_SsePayload):
    """Optional-tool progress without args, results, or display text."""

    tool_key: str = Field(min_length=1, max_length=64)
    phase: SseProgressPhase


class HeartbeatPayload(_SsePayload):
    """Empty persisted heartbeat payload."""


class RouteCorrectionPayload(_SsePayload):
    """Single-correction diagnostic. No evidence text."""

    from_route: str | None = Field(default=None, max_length=64)
    to_route: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=128)


class LimitationPayload(_SsePayload):
    """Named limitation code only."""

    code: str = Field(min_length=1, max_length=128)


class DeadlinePayload(_SsePayload):
    """Deadline exhaustion notice before ``partial``."""

    route_family: str | None = Field(default=None, max_length=64)


class PartialPayload(_SsePayload):
    """Verified partial/insufficient terminal."""

    reason: str = Field(min_length=1, max_length=128)


class CachePayload(_SsePayload):
    """Retrieval cache diagnostic. IDs/status only."""

    status: str = Field(min_length=1, max_length=64)


class CoveragePayload(_SsePayload):
    """Coverage score without passage text."""

    coverage_score: float | None = None


class OptionalToolDisclosurePayload(_SsePayload):
    """Selected optional tool keys only."""

    tool_keys: tuple[str, ...] = ()


class CitationPreviewPayload(_SsePayload):
    """Citation identifiers and ranks. No passage text."""

    citation_ids: tuple[str, ...] = ()
    ranks: tuple[int, ...] = ()


class AnswerOriginPayload(_SsePayload):
    """Strict-split answer origin. Never inferred from route family."""

    origin: str = Field(min_length=1, max_length=64)


class TokenDeltaPayload(_SsePayload):
    """Generated answer token delta. Never retrieved source text."""

    delta: str = Field(default="", max_length=4096)


class UsagePayload(_SsePayload):
    """Token usage without prompts."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class CompletedPayload(_SsePayload):
    """Successful terminal."""


class CancelledPayload(_SsePayload):
    """Cancellation terminal."""


class ErrorPayload(_SsePayload):
    """Sanitized error code. Never an exception message."""

    code: str = Field(min_length=1, max_length=128)


PAYLOAD_MODELS: Final[dict[str, type[BaseModel]]] = {
    "schema": SchemaPayload,
    "status": StatusPayload,
    "tool_progress": ToolProgressPayload,
    "heartbeat": HeartbeatPayload,
    "route_correction": RouteCorrectionPayload,
    "limitation": LimitationPayload,
    "deadline": DeadlinePayload,
    "partial": PartialPayload,
    "cache": CachePayload,
    "coverage": CoveragePayload,
    "optional_tool_disclosure": OptionalToolDisclosurePayload,
    "citation_preview": CitationPreviewPayload,
    "answer_origin": AnswerOriginPayload,
    "token_delta": TokenDeltaPayload,
    "usage": UsagePayload,
    "completed": CompletedPayload,
    "cancelled": CancelledPayload,
    "error": ErrorPayload,
}
