"""LangSmith export for every model and embedding gateway call.

Tracing is off unless ``LANGSMITH_TRACING`` is true on validated settings.
Exported spans omit prompts, queries, excerpts, embeddings, API keys, and
raw passages unless local ``LANGSMITH_EXPORT_IO`` is on. Hide-input/output
environment flags stay on by default because ``wrap_openai`` would otherwise
log Responses bodies.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, cast

from langsmith import get_current_run_tree as _get_current_run_tree
from langsmith import (
    traceable as _langsmith_traceable,  # pyright: ignore[reportUnknownVariableType]
)
from langsmith.utils import (
    tracing_is_enabled as _langsmith_tracing_is_enabled,  # pyright: ignore[reportUnknownVariableType]
)
from openai import AsyncOpenAI, OpenAI

from smart_rag_core.observability.logging import current_correlation_ids
from smart_rag_core.settings import SharedSettings, get_process_environ

if TYPE_CHECKING:
    from openai.types.create_embedding_response import CreateEmbeddingResponse

get_current_run_tree = cast(Any, _get_current_run_tree)
traceable = cast(Any, _langsmith_traceable)
tracing_is_enabled = cast(Any, _langsmith_tracing_is_enabled)

LangSmithRunType = Literal[
    "tool",
    "chain",
    "llm",
    "retriever",
    "embedding",
    "prompt",
    "parser",
]

LOGGER = logging.getLogger(__name__)

LANGSMITH_HIDE_INPUTS_ENV = "LANGSMITH_HIDE_INPUTS"
LANGSMITH_HIDE_OUTPUTS_ENV = "LANGSMITH_HIDE_OUTPUTS"
LANGSMITH_EXPORT_IO_ENV = "LANGSMITH_EXPORT_IO"
LANGSMITH_TRACING_ENV = "LANGSMITH_TRACING"
LANGCHAIN_TRACING_V2_ENV = "LANGCHAIN_TRACING_V2"

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "excerpts",
        "input",
        "inputs",
        "instructions",
        "prompt",
        "prompt_text",
        "query",
        "recent_memory",
        "system_prompt",
        "self",
        "text",
        "user_query",
        "vectors",
    }
)


def langsmith_export_io_enabled() -> bool:
    """Return whether local raw LangSmith I/O export is active.

    Returns:
        True only after validated startup wrote ``LANGSMITH_EXPORT_IO=true``.
        Staging and production never write that value.
    """

    return (get_process_environ(LANGSMITH_EXPORT_IO_ENV, "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def short_content_hash(value: str) -> str:
    """Return a truncated SHA-256 digest for content that must not be exported.

    Args:
        value: Prompt, query, excerpt, or other private text.

    Returns:
        First 16 hex characters of the SHA-256 digest.
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _json_preview(value: object) -> str:
    """Serialize a value for leak tests without raising on non-JSON types.

    Args:
        value: Arbitrary trace payload.

    Returns:
        JSON or ``repr`` text.
    """

    try:
        return json.dumps(value, default=str)
    except TypeError:
        return repr(value)


def _as_int(value: object) -> int:
    """Coerce a traced numeric field to int.

    Args:
        value: Token count or similar numeric trace field.

    Returns:
        Integer form of ``value``.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value))


def _traced_output_value(outputs: object) -> object:
    """Return the nested LangSmith output or the original value.

    Args:
        outputs: Traceable return wrapper or the raw gateway response.

    Returns:
        The ``output`` entry when ``outputs`` is a mapping, otherwise
        ``outputs``.
    """

    if not isinstance(outputs, Mapping):
        return outputs
    mapped = cast(Mapping[str, object], outputs)
    return mapped.get("output", mapped)


def configure_langsmith(settings: SharedSettings) -> dict[str, str]:
    """Apply process LangSmith flags from validated deployable settings.

    Args:
        settings: Shared settings already validated at process start.

    Returns:
        Applied flag names and values. The API key is never included.

    Side Effects:
        Delegates to :meth:`SharedSettings.apply_langsmith_sdk_flags`.
    """

    return settings.apply_langsmith_sdk_flags()


def flush_langsmith_traces(*, timeout_seconds: float) -> None:
    """Drain the process LangSmith client within an explicit lifecycle bound.

    Per-request and per-model-call code must not call this function. LangSmith
    exports through its background queue during the process lifetime; a
    synchronous drain belongs only at process shutdown.

    Args:
        timeout_seconds: Maximum seconds to wait for queued trace operations.
            Non-positive values return immediately. ``None`` is deliberately
            unsupported because the pinned SDK interprets it as an unbounded
            queue wait.

    Side Effects:
        Flushes the active run's client, or the pinned SDK's process-cached
        client, when tracing and a key are configured. Trace export failures
        are logged without exposing the key and never propagate.
    """

    timeout = max(0.0, float(timeout_seconds))
    if timeout == 0.0:
        return
    if not tracing_is_enabled():
        return
    if not get_process_environ("LANGSMITH_API_KEY"):
        return
    try:
        run = get_current_run_tree()
        client = getattr(run, "client", None)
        if client is None:
            from langsmith.run_trees import get_cached_client

            client = get_cached_client()
        flush = getattr(client, "flush", None)
        if callable(flush):
            cast(Any, flush)(timeout=timeout)
    except Exception:
        LOGGER.info(
            "LangSmith flush failed",
            extra={"event": "langsmith.flush_failed"},
        )


def traced_openai_client(
    *,
    api_key: str,
    max_retries: int = 0,
    timeout: float | None = None,
) -> OpenAI:
    """Construct the only production OpenAI client.

    Args:
        api_key: Provider credential. Never logged.
        max_retries: SDK retry count. Production rerank uses ``0``.
        timeout: Client timeout in seconds.

    Returns:
        An ``OpenAI`` client. When tracing is enabled the client is wrapped
        with ``wrap_openai`` so Responses and Chat calls become child LLM
        runs. Hide-input/output flags omit prompt bodies unless local
        ``LANGSMITH_EXPORT_IO`` is on.

    Side Effects:
        May wrap the SDK client with LangSmith instrumentation.
    """

    client = OpenAI(api_key=api_key, max_retries=max_retries, timeout=timeout)
    if not tracing_is_enabled():
        return client
    from langsmith.wrappers import wrap_openai

    return wrap_openai(client)


def traced_async_openai_client(
    *,
    api_key: str,
    max_retries: int = 0,
    timeout: float | None = None,
) -> AsyncOpenAI:
    """Construct the only production async OpenAI client.

    Embeddings from async LightRAG/Hybrid paths must use this factory.
    Omitting ``timeout`` inherits the SDK 600-second default, which is
    longer than the LightRAG embedding watchdog and is forbidden there.

    Args:
        api_key: Provider credential. Never logged.
        max_retries: SDK retry count. Production embeddings use ``0``.
        timeout: Client timeout in seconds. Callers must pass an explicit
            bound; ``None`` still constructs the client for tests.

    Returns:
        An ``AsyncOpenAI`` client, optionally wrapped for LangSmith.

    Side Effects:
        May wrap the SDK client with LangSmith instrumentation.
    """

    client = AsyncOpenAI(api_key=api_key, max_retries=max_retries, timeout=timeout)
    if not tracing_is_enabled():
        return client
    from langsmith.wrappers import wrap_openai

    return wrap_openai(client)


def redact_gateway_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Replace gateway arguments with hashes, counts, and correlation IDs.

    Args:
        inputs: Traceable function arguments, including ``self`` and
            ``request``.

    Returns:
        Exportable metadata. Query text, excerpts, and prompts are omitted
        unless local ``LANGSMITH_EXPORT_IO`` is on. API keys stay omitted.
    """

    request = inputs.get("request")
    operation = getattr(request, "operation", None)
    if operation is None and getattr(request, "operation_key", None) is not None:
        operation = "embedding"
    payload: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "operation": str(operation or "unknown"),
    }
    export_io = langsmith_export_io_enabled()
    query = getattr(request, "query", None)
    if isinstance(query, str):
        payload["query_sha256"] = short_content_hash(query)
        payload["query_chars"] = len(query)
        if export_io:
            payload["query"] = query
    prompt = getattr(request, "prompt", None)
    if isinstance(prompt, str):
        payload["prompt_sha256"] = short_content_hash(prompt)
        payload["prompt_chars"] = len(prompt)
        if export_io:
            payload["prompt"] = prompt
    role = getattr(request, "role", None)
    if isinstance(role, str):
        payload["role"] = role
    system_prompt = getattr(request, "system_prompt", None)
    if isinstance(system_prompt, str):
        payload["system_prompt_sha256"] = short_content_hash(system_prompt)
        payload["system_prompt_chars"] = len(system_prompt)
        if export_io:
            payload["system_prompt"] = system_prompt
    prompt_text = getattr(request, "prompt_text", None)
    if isinstance(prompt_text, str):
        payload["prompt_text_sha256"] = short_content_hash(prompt_text)
        payload["prompt_text_chars"] = len(prompt_text)
        if export_io:
            payload["prompt_text"] = prompt_text
    recent_memory = getattr(request, "recent_memory", None)
    if isinstance(recent_memory, str) and recent_memory:
        payload["recent_memory_sha256"] = short_content_hash(recent_memory)
        payload["recent_memory_chars"] = len(recent_memory)
        if export_io:
            payload["recent_memory"] = recent_memory
    excerpts = getattr(request, "excerpts", None)
    if excerpts is not None:
        excerpt_list = tuple(str(item) for item in excerpts)
        payload["excerpt_count"] = len(excerpt_list)
        payload["excerpt_chars"] = sum(len(item) for item in excerpt_list)
        payload["excerpts_sha256"] = short_content_hash("\n".join(excerpt_list))
        if export_io:
            payload["excerpts"] = list(excerpt_list)
    candidate_ids = getattr(request, "candidate_ids", None)
    if candidate_ids is not None:
        payload["candidate_count"] = len(tuple(candidate_ids))
    for field in ("prompt_version", "prompt_sha256", "model_id", "operation_key"):
        value = getattr(request, field, None)
        if value is not None:
            payload[field] = value
    inputs_batch = getattr(request, "inputs", None)
    if inputs_batch is not None:
        texts = tuple(str(item) for item in inputs_batch)
        payload["input_count"] = len(texts)
        payload["input_chars"] = sum(len(item) for item in texts)
        payload["inputs_sha256"] = short_content_hash("\n".join(texts))
        if export_io:
            payload["inputs"] = list(texts)
    dimensions = getattr(request, "dimensions", None)
    if isinstance(dimensions, int):
        payload["dimensions"] = dimensions
    model = getattr(request, "model", None)
    if isinstance(model, str):
        payload["model"] = model
    timeout_seconds = getattr(request, "timeout_seconds", None)
    if isinstance(timeout_seconds, (int, float)):
        payload["timeout_seconds"] = float(timeout_seconds)
    return payload


def redact_gateway_outputs(outputs: object) -> dict[str, Any]:
    """Keep usage and mode; drop passages, rankings text, and vectors.

    Args:
        outputs: Traceable return wrapper. LangSmith may nest the value
            under ``output``, or pass the gateway response object directly.

    Returns:
        Exportable metadata with token counts when present.
    """

    raw = _traced_output_value(outputs)
    payload: dict[str, Any] = {}
    mode = getattr(raw, "mode", None)
    if mode is not None:
        payload["mode"] = mode
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        payload["content_chars"] = len(content)
        payload["content_sha256"] = short_content_hash(content)
        if langsmith_export_io_enabled():
            payload["content"] = content
    request_id = getattr(raw, "request_id", None) or getattr(
        raw, "provider_request_id", None
    )
    if request_id is not None:
        payload["request_id"] = str(request_id)
    for field in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "model_calls",
    ):
        value = getattr(raw, field, None)
        if isinstance(value, int):
            payload[field] = value
    estimated_cost_usd = getattr(raw, "estimated_cost_usd", None)
    if estimated_cost_usd is not None:
        payload["estimated_cost_usd"] = float(estimated_cost_usd)
    model_id = getattr(raw, "model_id", None)
    if isinstance(model_id, str) and model_id:
        payload["model_id"] = model_id
    pricing_version = getattr(raw, "pricing_version", None)
    if isinstance(pricing_version, str) and pricing_version:
        payload["pricing_version"] = pricing_version
    if "estimated_cost_usd" not in payload:
        input_count = payload.get("input_tokens")
        output_count = payload.get("output_tokens")
        if isinstance(input_count, int) and isinstance(output_count, int):
            payload["estimated_cost_usd"] = float(
                estimate_traced_chat_cost_usd(
                    input_tokens=input_count,
                    output_tokens=output_count,
                )
            )
    vectors = getattr(raw, "vectors", None)
    if vectors is not None:
        payload["vector_count"] = len(tuple(vectors))
        if vectors:
            payload["vector_dimensions"] = len(tuple(vectors[0]))
    ranking_payload = getattr(raw, "payload", None)
    if isinstance(ranking_payload, dict):
        typed_payload = cast(dict[str, object], ranking_payload)
        payload["payload_keys"] = sorted(typed_payload)
        rankings = typed_payload.get("rankings")
        if isinstance(rankings, list):
            payload["ranking_count"] = len(cast(list[object], rankings))
    return payload


def redact_openai_call_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Redact keyword arguments for a traced OpenAI SDK call.

    Args:
        inputs: Traceable arguments. ``api_key``, ``query``, ``user_query``,
            ``recent_memory``, ``excerpts``, and ``prompt_text`` are never
            copied.

    Returns:
        Counts, hashes, model id, and timeout only.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    export_io = langsmith_export_io_enabled()
    for key, value in inputs.items():
        if key == "api_key":
            continue
        if key in _SENSITIVE_KEYS:
            if isinstance(value, str):
                payload[f"{key}_sha256"] = short_content_hash(value)
                payload[f"{key}_chars"] = len(value)
                if export_io:
                    payload[key] = value
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                payload[f"{key}_count"] = len(cast(Sequence[object], value))
                if export_io:
                    payload[key] = [str(item) for item in cast(Sequence[object], value)]
            continue
        if (
            key == "candidate_ids"
            and isinstance(value, Sequence)
            and not isinstance(value, (str, bytes))
        ):
            payload["candidate_count"] = len(cast(Sequence[object], value))
            continue
        if key in {
            "model_id",
            "model",
            "prompt_version",
            "prompt_sha256",
            "input_hash",
            "timeout_seconds",
            "max_retries",
            "role",
        }:
            payload[key] = value
    return payload


def redact_rerank_call_outputs(outputs: object) -> dict[str, Any]:
    """Export Responses usage without response bodies.

    LangSmith passes ``process_outputs`` the traced function's raw return
    value. The pinned rerank, query-profile, and general-chat adapters return
    a four-item tuple, while direct redactor tests may provide the SDK-style
    ``{"output": tuple}`` wrapper.

    Args:
        outputs: Raw return value or traceable wrapper around
            ``(payload, request_id, input_tokens, output_tokens)``.

    Returns:
        Request id, valid token counts, and payload key names. Malformed
        values return safe partial metadata or an empty mapping and never
        expose the response body.
    """

    raw = _traced_output_value(outputs)
    if not isinstance(raw, tuple):
        return {}
    items = list(cast(Sequence[object], raw))
    if len(items) < 4:
        return {}
    loaded, request_id, input_tokens, output_tokens = (
        items[0],
        items[1],
        items[2],
        items[3],
    )
    payload: dict[str, Any] = {"payload_keys": []}
    if isinstance(loaded, Mapping):
        typed_loaded = cast(Mapping[object, object], loaded)
        payload["payload_keys"] = sorted(str(key) for key in typed_loaded)
    if request_id is not None:
        payload["request_id"] = str(request_id)
    for field, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
    ):
        try:
            payload[field] = _as_int(value)
        except (TypeError, ValueError, OverflowError):
            continue
    return payload


def redact_lightrag_llm_call_outputs(outputs: object) -> dict[str, Any]:
    """Export LightRAG extract usage without callback text.

    Args:
        outputs: Traceable return wrapper around ``(content, request_id,
            input_tokens, cached_input_tokens, output_tokens,
            estimated_cost_usd)``.

    Returns:
        Request id, token counts, estimated USD, and content length/hash.
        Raw extract text is omitted.
    """

    if isinstance(outputs, Mapping):
        typed_outputs = cast(Mapping[str, Any], outputs)
        raw: object = typed_outputs.get("output", outputs)
    else:
        raw = outputs
    if not isinstance(raw, tuple):
        return {}
    items = list(cast(Sequence[object], raw))
    if len(items) < 6:
        return {}
    (
        content,
        request_id,
        input_tokens,
        cached_input_tokens,
        output_tokens,
        estimated_cost_usd,
    ) = (
        items[0],
        items[1],
        items[2],
        items[3],
        items[4],
        items[5],
    )
    input_count = _as_int(input_tokens)
    output_count = _as_int(output_tokens)
    payload: dict[str, Any] = {
        "request_id": str(request_id),
        "input_tokens": input_count,
        "cached_input_tokens": _as_int(cached_input_tokens),
        "output_tokens": output_count,
        "total_tokens": input_count + output_count,
        "estimated_cost_usd": float(str(estimated_cost_usd)),
    }
    if isinstance(content, str):
        payload["content_chars"] = len(content)
        payload["content_sha256"] = short_content_hash(content)
        if langsmith_export_io_enabled():
            payload["content"] = content
    return payload


def redact_embedding_call_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Redact ``embeddings.create`` keyword arguments.

    Args:
        inputs: Traceable arguments including ``input`` texts.

    Returns:
        Model, dimensions, input count, and a hash of the concatenated
        inputs. Raw strings are omitted.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    model = inputs.get("model")
    if isinstance(model, str):
        payload["model"] = model
    dimensions = inputs.get("dimensions")
    if isinstance(dimensions, int):
        payload["dimensions"] = dimensions
    raw_input = inputs.get("input")
    if isinstance(raw_input, str):
        texts = (raw_input,)
    elif isinstance(raw_input, Sequence) and not isinstance(raw_input, (str, bytes)):
        texts = tuple(str(item) for item in cast(Sequence[object], raw_input))
    else:
        texts = ()
    if texts:
        payload["input_count"] = len(texts)
        payload["input_chars"] = sum(len(item) for item in texts)
        payload["inputs_sha256"] = short_content_hash("\n".join(texts))
        if langsmith_export_io_enabled():
            payload["input"] = list(texts)
    return payload


def redact_embedding_call_outputs(outputs: object) -> dict[str, Any]:
    """Export embedding usage without vector values.

    Args:
        outputs: Traceable return value. LangSmith may pass a mapping or the
            raw ``CreateEmbeddingResponse`` / ``EmbeddingResponse``.

    Returns:
        Embedding count, dimension, and token usage when present.
    """

    raw = _traced_output_value(outputs)
    payload: dict[str, Any] = {}
    data = getattr(raw, "data", None)
    if data:
        payload["embedding_count"] = len(tuple(data))
        first = data[0]
        vector = getattr(first, "embedding", None)
        if vector is not None:
            payload["dimensions"] = len(tuple(vector))
    usage = getattr(raw, "usage", None)
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        if isinstance(prompt_tokens, int):
            payload["prompt_tokens"] = prompt_tokens
        total_tokens = getattr(usage, "total_tokens", None)
        if isinstance(total_tokens, int):
            payload["total_tokens"] = total_tokens
    request_id = getattr(raw, "id", None)
    if request_id is not None:
        payload["request_id"] = str(request_id)
    return payload


def estimate_traced_chat_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> Decimal:
    """Estimate standard-API USD for gpt-4o-mini token counts.

    Args:
        input_tokens: Provider-reported input tokens, including cached tokens.
        output_tokens: Provider-reported output tokens.
        cached_input_tokens: Input tokens billed at the cached-input rate.

    Returns:
        Pinned list-price estimate. The OpenAI invoice remains canonical.

    Raises:
        ValueError: If counts are negative or cached input exceeds total input.
    """

    from smart_rag_core.gateways.openai_lightrag import estimate_lightrag_llm_cost

    return estimate_lightrag_llm_cost(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )


def langsmith_usage_metadata(
    *,
    input_tokens: int,
    output_tokens: int,
    total_cost_usd: Decimal | None = None,
) -> dict[str, int | float]:
    """Build the LangSmith-recognized usage payload.

    Args:
        input_tokens: Provider-reported input token count.
        output_tokens: Provider-reported output token count.
        total_cost_usd: Optional precomputed total. When omitted, input and
            output costs are estimated separately from the pinned list price.

    Returns:
        Mapping with token counts plus ``input_cost``, ``output_cost``, and
        ``total_cost``. LangSmith shows these on LLM runs.
    """

    if total_cost_usd is not None and output_tokens == 0:
        input_cost = total_cost_usd
        output_cost = Decimal("0")
        total_cost = total_cost_usd
    elif total_cost_usd is not None and input_tokens == 0:
        input_cost = Decimal("0")
        output_cost = total_cost_usd
        total_cost = total_cost_usd
    else:
        input_cost = estimate_traced_chat_cost_usd(
            input_tokens=input_tokens,
            output_tokens=0,
        )
        output_cost = estimate_traced_chat_cost_usd(
            input_tokens=0,
            output_tokens=output_tokens,
        )
        total_cost = (
            total_cost_usd if total_cost_usd is not None else input_cost + output_cost
        )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost": float(input_cost),
        "output_cost": float(output_cost),
        "total_cost": float(total_cost),
    }


def record_current_usage_metadata(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    total_cost_usd: Decimal,
) -> None:
    """Attach recognized token and cost metadata to the current model span.

    Args:
        provider: Provider slug shown by LangSmith, such as ``openai``.
        model: Provider model id used by the call.
        input_tokens: Provider-reported input token count.
        output_tokens: Provider-reported output token count.
        total_cost_usd: Application estimate in USD.

    Side Effects:
        Updates only the active LangSmith run tree. No-op when tracing is off
        or no current run exists. Raw model inputs and outputs are never added.
    """

    if not tracing_is_enabled():
        return
    run = get_current_run_tree()
    if run is None:
        return
    run.metadata["ls_provider"] = provider
    run.metadata["ls_model_name"] = model
    run.set(
        usage_metadata=langsmith_usage_metadata(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_cost_usd=total_cost_usd,
        )
    )


def record_gateway_response_usage(response: object) -> None:
    """Attach token and USD metadata from one gateway response.

    Args:
        response: Gateway return value. Token fields are optional; foundation
            fixtures without usage are ignored.

    Side Effects:
        Updates the active LangSmith run when tracing is on and the response
        reports token counts. Raw prompts and completions are never added.
    """

    input_tokens = getattr(response, "input_tokens", None)
    output_tokens = getattr(response, "output_tokens", None)
    if isinstance(input_tokens, bool) or isinstance(output_tokens, bool):
        return
    if not isinstance(input_tokens, int) and not isinstance(output_tokens, int):
        return
    input_count = input_tokens if isinstance(input_tokens, int) else 0
    output_count = output_tokens if isinstance(output_tokens, int) else 0
    raw_cost = getattr(response, "estimated_cost_usd", None)
    if raw_cost is None:
        total_cost = estimate_traced_chat_cost_usd(
            input_tokens=input_count,
            output_tokens=output_count,
        )
    else:
        total_cost = Decimal(str(raw_cost))
    model_id = getattr(response, "model_id", None)
    record_current_usage_metadata(
        provider="openai",
        model=model_id if isinstance(model_id, str) and model_id else "",
        input_tokens=input_count,
        output_tokens=output_count,
        total_cost_usd=total_cost,
    )


def payload_contains_forbidden_text(payload: object, *needles: str) -> bool:
    """Return whether serialized payload text contains any needle.

    Args:
        payload: Trace inputs, outputs, or extra.
        *needles: Substrings that must never appear, such as canary secrets.

    Returns:
        True when any needle is present.
    """

    rendered = _json_preview(payload).lower()
    return any(needle.lower() in rendered for needle in needles)


@traceable(
    name="openai.embeddings",
    run_type="embedding",
    process_inputs=redact_embedding_call_inputs,
    process_outputs=redact_embedding_call_outputs,
)
def traced_embeddings_create(
    client: OpenAI,
    *,
    input_usd_per_million: Decimal = Decimal("0"),
    **kwargs: Any,
) -> CreateEmbeddingResponse:
    """Issue one embeddings request through the traced factory client.

    Args:
        client: Client from :func:`traced_openai_client`.
        input_usd_per_million: Pinned input-token price used for the displayed
            LangSmith estimate. Zero leaves cost at zero.
        **kwargs: Forwarded to ``client.embeddings.create``. ``input`` text
            is hashed in the exported span and never copied.

    Returns:
        Provider embedding response.

    Side Effects:
        One HTTPS embeddings request. Creates a LangSmith span when tracing
        is enabled.
    """

    response = client.embeddings.create(**kwargs)
    usage = getattr(response, "usage", None)
    input_tokens = (
        int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
    )
    cost = Decimal(input_tokens) * input_usd_per_million / Decimal(1_000_000)
    record_current_usage_metadata(
        provider="openai",
        model=str(kwargs.get("model", "") or ""),
        input_tokens=input_tokens,
        output_tokens=0,
        total_cost_usd=cost,
    )
    return response


@traceable(
    name="openai.embeddings",
    run_type="embedding",
    process_inputs=redact_embedding_call_inputs,
    process_outputs=redact_embedding_call_outputs,
)
async def traced_embeddings_create_async(
    client: AsyncOpenAI,
    *,
    input_usd_per_million: Decimal = Decimal("0"),
    **kwargs: Any,
) -> CreateEmbeddingResponse:
    """Issue one async embeddings request through the traced factory client.

    Args:
        client: Client from :func:`traced_async_openai_client`.
        input_usd_per_million: Pinned input-token price used for the displayed
            LangSmith estimate. Zero leaves cost at zero.
        **kwargs: Forwarded to ``client.embeddings.create``. ``input`` text
            is hashed in the exported span and never copied.

    Returns:
        Provider embedding response.

    Side Effects:
        One HTTPS embeddings request. Creates a LangSmith span when tracing
        is enabled. Does not block the event loop on the HTTP wait.
    """

    response = await client.embeddings.create(**kwargs)
    usage = getattr(response, "usage", None)
    input_tokens = (
        int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
    )
    cost = Decimal(input_tokens) * input_usd_per_million / Decimal(1_000_000)
    record_current_usage_metadata(
        provider="openai",
        model=str(kwargs.get("model", "") or ""),
        input_tokens=input_tokens,
        output_tokens=0,
        total_cost_usd=cost,
    )
    return response


def rerank_responses_traceable(func: Any) -> Any:
    """Apply the redacted Responses rerank span decorator.

    Args:
        func: ``execute_openai_rerank`` implementation.

    Returns:
        Traceable wrapper that hashes query/excerpts and omits API keys.
    """

    return traceable(
        name="openai.responses.rerank",
        run_type="llm",
        process_inputs=redact_openai_call_inputs,
        process_outputs=redact_rerank_call_outputs,
    )(func)


def conversation_title_responses_traceable(func: Any) -> Any:
    """Apply the redacted Responses session-title span decorator.

    Args:
        func: ``execute_openai_conversation_title`` implementation.

    Returns:
        Traceable wrapper that hashes prompt and excerpt text and omits
        API keys.
    """

    return traceable(
        name="openai.responses.conversation_title",
        run_type="llm",
        process_inputs=redact_openai_call_inputs,
        process_outputs=redact_rerank_call_outputs,
    )(func)


def general_chat_responses_traceable(func: Any) -> Any:
    """Apply the redacted Responses general-chat span decorator.

    Args:
        func: ``execute_openai_general_chat`` implementation.

    Returns:
        Traceable wrapper that hashes prompt/query text and omits API keys.
    """

    return traceable(
        name="openai.responses.general_chat",
        run_type="llm",
        process_inputs=redact_openai_call_inputs,
        process_outputs=redact_rerank_call_outputs,
    )(func)


def query_profile_responses_traceable(func: Any) -> Any:
    """Apply the redacted Responses query-profile span decorator.

    Args:
        func: ``execute_openai_query_profile`` implementation.

    Returns:
        Traceable wrapper that hashes prompt/query/memory and omits API keys.
    """

    return traceable(
        name="openai.responses.query_profile",
        run_type="llm",
        process_inputs=redact_openai_call_inputs,
        process_outputs=redact_rerank_call_outputs,
    )(func)


def lightrag_llm_responses_traceable(func: Any) -> Any:
    """Apply the redacted Responses LightRAG extract span decorator.

    Args:
        func: ``execute_openai_lightrag_llm`` implementation.

    Returns:
        Traceable wrapper that hashes prompts and omits extract bodies.
    """

    return traceable(
        name="openai.responses.lightrag_llm",
        run_type="llm",
        process_inputs=redact_openai_call_inputs,
        process_outputs=redact_lightrag_llm_call_outputs,
    )(func)


def model_call_traceable(*, name: str, run_type: LangSmithRunType = "llm") -> Any:
    """Return a ``traceable`` decorator for ModelGateway or EmbeddingGateway methods.

    Args:
        name: Stable LangSmith run name such as ``model.rerank``.
        run_type: LangSmith run type. Use ``embedding`` for embedding batches.

    Returns:
        Decorator that redacts gateway request/response bodies and attaches
        recognized token and USD metadata when the response reports usage.
    """

    def decorator(func: Any) -> Any:
        """Wrap one gateway method with a redacted LangSmith span.

        Args:
            func: Async gateway method that accepts ``request``.

        Returns:
            Traceable coroutine that records usage metadata after the call.
        """

        @functools.wraps(func)
        async def _record_usage(self: Any, request: Any) -> Any:
            """Invoke the gateway method and attach token and USD metadata.

            Args:
                self: Gateway instance.
                request: Typed gateway request.

            Returns:
                Unchanged gateway response.
            """

            result = await func(self, request)
            record_gateway_response_usage(result)
            return result

        return traceable(
            name=name,
            run_type=run_type,
            process_inputs=redact_gateway_inputs,
            process_outputs=redact_gateway_outputs,
        )(_record_usage)

    return decorator
