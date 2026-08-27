"""Hashed identity and redacted query-trace payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from smart_rag_core.observability.langsmith_tracing import (
    estimate_traced_chat_cost_usd,
    langsmith_export_io_enabled,
    langsmith_usage_metadata,
    short_content_hash,
)
from smart_rag_core.observability.logging import (
    current_correlation_ids,
)

_PARENT_INPUT_KEYS = frozenset(
    {
        "case_id",
        "run_id",
        "user_id_sha256",
        "conversation_id_sha256",
        "requested_route",
        "effective_route",
        "corrected_route",
        "graph_name",
    }
)


def hashed_user_id(user_id: UUID | str) -> str:
    """Return a truncated SHA-256 of a user id. Never the raw UUID in traces.

    Args:
        user_id: Authenticated subject.

    Returns:
        First 16 hex characters of SHA-256.
    """

    return short_content_hash(str(user_id))


def hashed_conversation_id(conversation_id: UUID | str) -> str:
    """Return a truncated SHA-256 of a conversation id.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        First 16 hex characters of SHA-256.
    """

    return short_content_hash(str(conversation_id))


def redact_query_agent_eval_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Keep case/run hashes and routes; drop query, answer, and secrets.

    Args:
        inputs: Traceable kwargs.

    Returns:
        Exportable parent inputs plus correlation ids.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    for key in _PARENT_INPUT_KEYS:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    return payload


def redact_query_agent_eval_outputs(outputs: object) -> dict[str, Any]:
    """Export status, counts, and routes only. Never copy answer text.

    Args:
        outputs: Traceable return wrapper or the raw thunk result.

    Returns:
        Completed flag, route, citation count, latency, and cost when present.
    """

    raw: object = outputs
    if isinstance(outputs, Mapping):
        mapped = dict(cast(Mapping[str, object], outputs))
        raw = mapped.get("output", mapped)
    if not isinstance(raw, Mapping):
        return {"completed": True}
    payload: dict[str, Any] = {}
    typed = cast(Mapping[str, object], raw)
    completed = typed.get("completed")
    if isinstance(completed, bool):
        payload["completed"] = completed
    failure_kind = typed.get("failure_kind")
    if isinstance(failure_kind, str) and failure_kind:
        payload["failure_kind"] = failure_kind[:64]
    for key in ("effective_route", "answer_status"):
        value = typed.get(key)
        if isinstance(value, str) and value:
            payload[key] = value[:64]
    cited = typed.get("cited_chunk_ids")
    tables = typed.get("cited_table_ids")
    cited_count = 0
    if isinstance(cited, (list, tuple)):
        cited_count += len(cast(Sequence[object], cited))
    if isinstance(tables, (list, tuple)):
        cited_count += len(cast(Sequence[object], tables))
    payload["citation_count"] = cited_count
    latency = typed.get("latency_ms")
    if isinstance(latency, int):
        payload["latency_ms"] = latency
    cost = typed.get("agent_cost_usd")
    if isinstance(cost, str):
        payload["cost_usd"] = cost
    return payload or {"completed": True}


_SSE_PARENT_INPUT_KEYS = frozenset(
    {
        "run_id",
        "user_id_sha256",
        "requested_route",
        "effective_route",
        "model_versions",
        "prompt_versions",
    }
)

_SSE_PARENT_OUTPUT_KEYS = frozenset(
    {
        "termination_reason",
        "terminal_event_type",
        "stream_exhausted",
    }
)


def _optional_token_count(value: object) -> int | None:
    """Return a non-boolean integer token count.

    Args:
        value: Candidate token field.

    Returns:
        Integer count, or None when the value is missing or invalid.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def optional_cost_usd(value: object) -> Decimal | None:
    """Return a non-negative USD estimate.

    Args:
        value: Candidate cost field.

    Returns:
        Decimal USD, or None when the value is missing or invalid.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        cost = value
    elif isinstance(value, (int, float)):
        cost = Decimal(str(value))
    elif isinstance(value, str) and value:
        try:
            cost = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    if cost < 0:
        return None
    return cost


def _attach_hashed_text(
    payload: dict[str, Any],
    *,
    field: str,
    value: object,
    export_io: bool,
    display_key: str,
) -> None:
    """Hash private chat text and copy it only when local I/O export is on.

    Args:
        payload: Exportable mapping being built.
        field: Source field name used for hash and char-count keys.
        value: User message or assistant prose.
        export_io: Whether local raw I/O export is active.
        display_key: LangSmith Input/Output key (``input`` or ``output``).
    """

    if not isinstance(value, str) or not value:
        return
    payload[f"{field}_sha256"] = short_content_hash(value)
    payload[f"{field}_chars"] = len(value)
    if export_io:
        payload[field] = value
        payload[display_key] = value


def usage_token_counts(typed: Mapping[str, object]) -> tuple[int, int] | None:
    """Read prompt/completion token totals from a summary mapping.

    Args:
        typed: Termination summary or traceable return wrapper.

    Returns:
        ``(input_tokens, output_tokens)`` when either count is present.
    """

    input_tokens = _optional_token_count(typed.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _optional_token_count(typed.get("prompt_tokens"))
    output_tokens = _optional_token_count(typed.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _optional_token_count(typed.get("completion_tokens"))
    if input_tokens is None and output_tokens is None:
        return None
    return (
        0 if input_tokens is None else input_tokens,
        0 if output_tokens is None else output_tokens,
    )


def _attach_usage_fields(payload: dict[str, Any], typed: Mapping[str, object]) -> None:
    """Copy token counts and estimated USD onto a parent-span payload.

    Args:
        payload: Exportable mapping being built.
        typed: Termination summary or traceable return wrapper.
    """

    counts = usage_token_counts(typed)
    if counts is None:
        return
    input_count, output_count = counts
    payload["input_tokens"] = input_count
    payload["output_tokens"] = output_count
    payload["total_tokens"] = input_count + output_count
    cost = optional_cost_usd(typed.get("estimated_cost_usd"))
    if cost is None:
        cost = estimate_traced_chat_cost_usd(
            input_tokens=input_count,
            output_tokens=output_count,
        )
    payload["estimated_cost_usd"] = float(cost)
    usage = langsmith_usage_metadata(
        input_tokens=input_count,
        output_tokens=output_count,
        total_cost_usd=cost,
    )
    payload["usage_metadata"] = usage
    payload["usage"] = {
        "input_tokens": input_count,
        "output_tokens": output_count,
        "total_tokens": input_count + output_count,
        "estimated_cost_usd": float(cost),
    }


def _promote_visible_output(payload: dict[str, Any]) -> None:
    """Put token and USD fields inside LangSmith's Output panel.

    Args:
        payload: Exportable mapping after hashed-text and usage attachment.

    Side Effects:
        When local I/O export set a string ``output``, replace it with an
        object that keeps the assistant text next to token and USD fields.
        LangSmith's pretty view otherwise shows only the string.
    """

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return
    text = payload.get("output")
    if isinstance(text, str) and text:
        payload["output"] = {"text": text, **usage}


def redact_query_run_sse_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Export correlation IDs, hashed user, route, and optional chat input.

    Args:
        inputs: Traceable kwargs. JWTs and emails must never be present.
            ``user_message`` is hashed unless local ``LANGSMITH_EXPORT_IO``
            is on.

    Returns:
        Redacted parent inputs. Raw user text is included only for local
        I/O export.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    for key in _SSE_PARENT_INPUT_KEYS:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            payload[key] = value[:64]
        elif isinstance(value, Mapping):
            mapped = cast(Mapping[object, object], value)
            payload[key] = {
                str(item_key)[:64]: str(item_value)[:64]
                for item_key, item_value in mapped.items()
            }
    _attach_hashed_text(
        payload,
        field="user_message",
        value=inputs.get("user_message"),
        export_io=langsmith_export_io_enabled(),
        display_key="input",
    )
    return payload


def redact_query_run_sse_outputs(outputs: object) -> dict[str, Any]:
    """Export termination, usage, and optional assistant prose.

    Args:
        outputs: Traceable return wrapper or the raw summary mapping.

    Returns:
        Termination reason, token counts, and estimated USD. Assistant
        text is included only when local ``LANGSMITH_EXPORT_IO`` is on.
        Never copies JWTs, emails, sources, or extra summary keys.
    """

    raw: object = outputs
    if isinstance(outputs, Mapping):
        mapped = dict(cast(Mapping[str, object], outputs))
        raw = mapped.get("output", mapped)
    if not isinstance(raw, Mapping):
        return {"termination_reason": "unknown"}
    payload: dict[str, Any] = {}
    typed = cast(Mapping[str, object], raw)
    for key in _SSE_PARENT_OUTPUT_KEYS:
        value = typed.get(key)
        if key == "stream_exhausted" and isinstance(value, bool):
            payload[key] = value
        elif isinstance(value, str) and value:
            payload[key] = value[:64]
    _attach_hashed_text(
        payload,
        field="assistant_message",
        value=typed.get("assistant_message"),
        export_io=langsmith_export_io_enabled(),
        display_key="output",
    )
    _attach_usage_fields(payload, typed)
    _promote_visible_output(payload)
    return payload or {"termination_reason": "unknown"}
