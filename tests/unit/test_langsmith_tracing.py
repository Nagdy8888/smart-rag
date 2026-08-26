"""LangSmith gateway tracing, redaction, and production call-site scans."""

from __future__ import annotations

import ast
import asyncio
import json
import os
from inspect import signature
from uuid import uuid4

import pytest
from smart_rag_core.gateways.embedding import EmbeddingRequest, create_embedding_gateway
from smart_rag_core.gateways.model import ModelRequest, create_model_gateway
from smart_rag_core.observability.langsmith_tracing import (
    LANGCHAIN_TRACING_V2_ENV,
    LANGSMITH_EXPORT_IO_ENV,
    LANGSMITH_HIDE_INPUTS_ENV,
    LANGSMITH_HIDE_OUTPUTS_ENV,
    LANGSMITH_TRACING_ENV,
    configure_langsmith,
    flush_langsmith_traces,
    general_chat_responses_traceable,
    payload_contains_forbidden_text,
    redact_gateway_inputs,
    redact_rerank_call_outputs,
    short_content_hash,
)
from smart_rag_core.observability.logging import correlation_context
from smart_rag_core.settings import (
    AgentSettings,
    SettingsValidationError,
    load_backend_settings,
)

from tests.support.langsmith import RecordingLangSmithClient
from tests.support.langsmith_scan import (
    _ALLOWED_EMBEDDINGS_CREATE,
    _ALLOWED_OPENAI_CTOR,
    _ALLOWED_RESPONSES_CREATE,
    CANARY_EMAIL,
    CANARY_PASSAGE,
    CANARY_TOKEN,
    REPO_ROOT,
    _call_name,
    _python_files,
    _tracing_context,
)


def test_tracing_requires_langsmith_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LANGSMITH_TRACING=true without a key fails typed startup validation."""

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    with pytest.raises(SettingsValidationError):
        load_backend_settings()


def test_langsmith_key_is_secret_in_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LangSmith credential is never included in settings repr."""

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_canary_must_not_leak")
    settings = load_backend_settings()
    assert settings.langsmith_tracing is True
    assert "lsv2_canary" not in repr(settings)


def test_configure_langsmith_forces_hide_and_default_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validated off tracing overwrites a leftover LANGSMITH_TRACING=true shell."""

    monkeypatch.setenv(LANGSMITH_TRACING_ENV, "false")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    settings = AgentSettings()
    monkeypatch.setenv(LANGSMITH_TRACING_ENV, "true")
    applied = configure_langsmith(settings)
    assert applied[LANGSMITH_HIDE_INPUTS_ENV] == "true"
    assert applied[LANGSMITH_HIDE_OUTPUTS_ENV] == "true"
    assert applied["LANGSMITH_EXPORT_IO"] == "false"
    assert applied[LANGSMITH_TRACING_ENV] == "false"
    assert applied[LANGCHAIN_TRACING_V2_ENV] == "false"


def test_configure_langsmith_enables_langchain_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled tracing also sets LANGCHAIN_TRACING_V2 for LangGraph export."""

    monkeypatch.setenv(LANGSMITH_TRACING_ENV, "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_canary_must_not_leak")
    monkeypatch.setenv("LANGSMITH_PROJECT", "smart-rag")
    settings = AgentSettings()
    applied = configure_langsmith(settings)
    assert applied[LANGSMITH_TRACING_ENV] == "true"
    assert applied[LANGCHAIN_TRACING_V2_ENV] == "true"
    assert os.environ[LANGCHAIN_TRACING_V2_ENV] == "true"
    assert os.environ["LANGCHAIN_PROJECT"] == "smart-rag"
    assert "lsv2_canary" not in repr(applied)
    assert "lsv2_canary" not in str(applied)


def test_flush_langsmith_traces_skips_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flush is a no-op when unit tests have no LangSmith credential."""

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    flush_langsmith_traces(timeout_seconds=0.1)


def test_pinned_langsmith_flush_exposes_timeout_contract() -> None:
    """The pinned SDK keeps the finite timeout needed by bounded shutdown."""

    from langsmith import Client

    timeout = signature(Client.flush).parameters["timeout"]
    assert timeout.default is None


def test_flush_langsmith_traces_zero_timeout_never_resolves_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-positive drain budget cannot touch LangSmith on a hot path."""

    from smart_rag_core.observability import langsmith_tracing as tracing

    def _unexpected_run_lookup() -> object:
        """Fail if a zero-budget drain tries to resolve a client.

        Raises:
            AssertionError: Always, because no lookup is permitted.
        """

        raise AssertionError("zero_timeout_resolved_langsmith_client")

    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_inert_test_key")
    monkeypatch.setattr(tracing, "tracing_is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_current_run_tree", _unexpected_run_lookup)
    flush_langsmith_traces(timeout_seconds=0.0)


def test_flush_langsmith_traces_uses_explicit_client_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle drain forwards a finite timeout to the active trace client."""

    from smart_rag_core.observability import langsmith_tracing as tracing

    calls: list[float | None] = []

    class _Client:
        """Record the timeout passed to the pinned client contract."""

        def flush(self, timeout: float | None = None) -> None:
            """Record one bounded flush request.

            Args:
                timeout: Maximum queue-drain wait in seconds.
            """

            calls.append(timeout)

    class _Run:
        """Expose the recording client through the current run tree."""

        def __init__(self) -> None:
            """Bind one recording client."""

            self.client = _Client()

    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_inert_test_key")
    monkeypatch.setattr(tracing, "tracing_is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_current_run_tree", _Run)
    flush_langsmith_traces(timeout_seconds=0.25)
    assert calls == [0.25]


def test_flush_langsmith_traces_uses_process_cached_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown drains the same cached client used by default traceable spans."""

    from langsmith import run_trees
    from smart_rag_core.observability import langsmith_tracing as tracing

    calls: list[float | None] = []

    class _Client:
        """Record the process-cached client drain."""

        def flush(self, timeout: float | None = None) -> None:
            """Record the bounded shutdown wait.

            Args:
                timeout: Maximum queue-drain wait in seconds.
            """

            calls.append(timeout)

    client = _Client()
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_inert_test_key")
    monkeypatch.setattr(tracing, "tracing_is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_current_run_tree", lambda: None)
    monkeypatch.setattr(run_trees, "get_cached_client", lambda: client)
    flush_langsmith_traces(timeout_seconds=0.5)
    assert calls == [0.5]


def test_flush_langsmith_traces_never_breaks_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A LangSmith drain error is telemetry loss, not an application error."""

    from smart_rag_core.observability import langsmith_tracing as tracing

    class _Client:
        """Raise the simulated provider-side drain failure."""

        def flush(self, timeout: float | None = None) -> None:
            """Fail one bounded drain.

            Args:
                timeout: Maximum queue-drain wait in seconds.

            Raises:
                RuntimeError: Always, to model an unavailable exporter.
            """

            del timeout
            raise RuntimeError("langsmith_unavailable")

    class _Run:
        """Expose the failing client through the current run tree."""

        def __init__(self) -> None:
            """Bind one failing client."""

            self.client = _Client()

    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_inert_test_key")
    monkeypatch.setattr(tracing, "tracing_is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_current_run_tree", _Run)
    flush_langsmith_traces(timeout_seconds=0.1)


def test_redact_gateway_inputs_omits_query_and_excerpts() -> None:
    """Canary query/excerpt/email never appear in the exported input dict."""

    request = ModelRequest(prompt=f"{CANARY_TOKEN} {CANARY_EMAIL} {CANARY_PASSAGE}")
    with correlation_context(request_id="req-trace-1"):
        payload = redact_gateway_inputs({"self": object(), "request": request})
    assert payload["operation"] == "foundation_probe"
    assert payload["prompt_sha256"] == short_content_hash(request.prompt)
    assert payload["correlation"]["request_id"] == "req-trace-1"
    assert not payload_contains_forbidden_text(
        payload, CANARY_TOKEN, CANARY_EMAIL, CANARY_PASSAGE
    )


def test_redact_gateway_inputs_includes_prompt_when_export_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local LANGSMITH_EXPORT_IO keeps prompt text on the gateway span."""

    monkeypatch.setenv(LANGSMITH_EXPORT_IO_ENV, "true")
    request = ModelRequest(prompt=f"{CANARY_TOKEN} {CANARY_EMAIL} {CANARY_PASSAGE}")
    payload = redact_gateway_inputs({"self": object(), "request": request})
    assert payload["prompt"] == request.prompt


def test_configure_langsmith_local_export_io_unhides_wrap_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local export I/O clears hide flags so wrap_openai child spans keep bodies."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv(LANGSMITH_TRACING_ENV, "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_canary_must_not_leak")
    monkeypatch.setenv(LANGSMITH_EXPORT_IO_ENV, "true")
    settings = AgentSettings()
    applied = configure_langsmith(settings)
    assert applied[LANGSMITH_HIDE_INPUTS_ENV] == "false"
    assert applied[LANGSMITH_HIDE_OUTPUTS_ENV] == "false"
    assert applied[LANGSMITH_EXPORT_IO_ENV] == "true"


def test_mock_generate_is_traced_without_prompt_body() -> None:
    """Enabled tracing records model.generate without the prompt text."""

    recorder = RecordingLangSmithClient()
    gateway = create_model_gateway(AgentSettings())
    request = ModelRequest(prompt=f"probe {CANARY_PASSAGE}")
    with _tracing_context(enabled=True, client=recorder):
        asyncio.run(gateway.generate(request))
    names = [item["name"] for item in recorder.created]
    assert "model.generate" in names
    for item in recorder.created:
        assert not payload_contains_forbidden_text(
            item, CANARY_PASSAGE, CANARY_TOKEN, CANARY_EMAIL
        )
    assert not payload_contains_forbidden_text(
        recorder.updated, CANARY_PASSAGE, CANARY_TOKEN, CANARY_EMAIL
    )


def test_tracing_disabled_creates_no_runs() -> None:
    """Default mock settings do not create LangSmith runs."""

    recorder = RecordingLangSmithClient()
    gateway = create_model_gateway(AgentSettings())
    with _tracing_context(enabled=False, client=recorder):
        asyncio.run(gateway.generate(ModelRequest(prompt="foundation probe")))
    assert recorder.created == []


def test_mock_embed_is_traced_without_input_text() -> None:
    """Enabled tracing records embedding.embed without input strings."""

    recorder = RecordingLangSmithClient()
    gateway = create_embedding_gateway(AgentSettings())
    request = EmbeddingRequest(
        operation_key="trace-test",
        inputs=(CANARY_PASSAGE,),
        model="text-embedding-3-large",
        dimensions=8,
    )
    with _tracing_context(enabled=True, client=recorder):
        asyncio.run(gateway.embed(request))
    names = [item["name"] for item in recorder.created]
    assert "embedding.embed" in names
    serialized = json.dumps(recorder.created + recorder.updated, default=str)
    assert CANARY_PASSAGE not in serialized


def test_redact_embedding_request_exports_timeout_not_text() -> None:
    """Embedding traces may export the HTTP bound, never input text."""

    request = EmbeddingRequest(
        operation_key="trace-timeout",
        inputs=(CANARY_PASSAGE,),
        model="text-embedding-3-large",
        dimensions=8,
        timeout_seconds=20.0,
    )
    payload = redact_gateway_inputs({"request": request})
    assert payload["timeout_seconds"] == 20.0
    assert payload["input_count"] == 1
    assert not payload_contains_forbidden_text(payload, CANARY_PASSAGE)


def test_production_openai_calls_use_traced_helpers() -> None:
    """Packages, apps, and scripts construct OpenAI only through the traced factory."""

    openai_ctors: list[str] = []
    responses_creates: list[str] = []
    embeddings_creates: list[str] = []
    for relative in _python_files():
        tree = ast.parse(
            (REPO_ROOT / relative).read_text(encoding="utf-8"),
            filename=str(relative),
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name is None:
                continue
            if name in {"OpenAI", "openai.OpenAI", "AsyncOpenAI", "openai.AsyncOpenAI"}:
                if relative not in _ALLOWED_OPENAI_CTOR:
                    openai_ctors.append(f"{relative}:{node.lineno}:{name}")
            if name.endswith("responses.create"):
                if relative not in _ALLOWED_RESPONSES_CREATE:
                    responses_creates.append(f"{relative}:{node.lineno}:{name}")
            if name.endswith("embeddings.create"):
                if relative not in _ALLOWED_EMBEDDINGS_CREATE:
                    embeddings_creates.append(f"{relative}:{node.lineno}:{name}")
    assert openai_ctors == []
    assert responses_creates == []
    assert embeddings_creates == []


def test_rerank_prompt_canary_is_hashed_not_copied() -> None:
    """Rerank request excerpts are hashed in gateway redaction."""

    from smart_rag_core.gateways.model import RerankModelRequest
    from smart_rag_core.retrieval.rerank_versions import (
        RERANK_PROMPT_SHA256,
        RERANK_PROMPT_VERSION,
    )

    first = str(uuid4())
    second = str(uuid4())
    request = RerankModelRequest(
        query=CANARY_PASSAGE,
        prompt_version=RERANK_PROMPT_VERSION,
        prompt_sha256=RERANK_PROMPT_SHA256,
        prompt_text=CANARY_TOKEN,
        candidate_ids=[first, second],
        excerpts=[CANARY_EMAIL, "second excerpt"],
        remaining_deadline_seconds=8.0,
    )
    payload = redact_gateway_inputs({"request": request})
    assert payload["operation"] == "rerank"
    assert payload["excerpt_count"] == 2
    assert payload["query_sha256"] == short_content_hash(CANARY_PASSAGE)
    assert not payload_contains_forbidden_text(
        payload, CANARY_TOKEN, CANARY_EMAIL, CANARY_PASSAGE
    )


def test_redact_gateway_outputs_accepts_embedding_response() -> None:
    """LangSmith may pass EmbeddingResponse directly instead of a mapping."""

    from decimal import Decimal

    from smart_rag_core.gateways.embedding import EmbeddingResponse
    from smart_rag_core.observability.langsmith_tracing import redact_gateway_outputs

    response = EmbeddingResponse(
        mode="openai",
        vectors=((0.0, 1.0),),
        provider_request_id="req-1",
        fixture_provenance="openai://text-embedding-3-large",
        estimated_cost_usd=Decimal("0"),
    )
    payload = redact_gateway_outputs(response)
    assert payload["mode"] == "openai"
    assert payload["vector_count"] == 1
    assert payload["vector_dimensions"] == 2
    assert payload["request_id"] == "req-1"


def test_responses_redactor_accepts_raw_general_chat_tuple() -> None:
    """Pinned LangSmith passes the function's tuple directly to process_outputs."""

    outputs = (
        {"status": "complete", "answer_text": CANARY_PASSAGE},
        "resp-general-1",
        258,
        17,
    )
    payload = redact_rerank_call_outputs(outputs)
    assert payload == {
        "payload_keys": ["answer_text", "status"],
        "request_id": "resp-general-1",
        "input_tokens": 258,
        "output_tokens": 17,
    }
    assert CANARY_PASSAGE not in json.dumps(payload)


def test_responses_redactor_accepts_mapping_wrapper() -> None:
    """The redactor remains compatible with explicit SDK-style output wrappers."""

    payload = redact_rerank_call_outputs(
        {
            "output": (
                {"rankings": [{"chunk_id": "private-id"}]},
                "resp-rerank-1",
                12,
                3,
            )
        }
    )
    assert payload == {
        "payload_keys": ["rankings"],
        "request_id": "resp-rerank-1",
        "input_tokens": 12,
        "output_tokens": 3,
    }
    assert "private-id" not in json.dumps(payload)


@pytest.mark.parametrize("outputs", [None, "text", (), (1, 2, 3)])
def test_responses_redactor_ignores_malformed_shapes(outputs: object) -> None:
    """Malformed trace output cannot prevent the LangSmith span from ending."""

    assert redact_rerank_call_outputs(outputs) == {}


def test_responses_redactor_omits_invalid_token_counts() -> None:
    """Invalid usage fields produce safe partial metadata instead of an exception."""

    payload = redact_rerank_call_outputs(
        ({"status": "complete"}, "resp-invalid-usage", "bad", object())
    )
    assert payload == {
        "payload_keys": ["status"],
        "request_id": "resp-invalid-usage",
    }


def test_general_chat_trace_closes_for_raw_tuple_output() -> None:
    """The pinned traceable processor records an end update for general chat."""

    recorder = RecordingLangSmithClient()

    @general_chat_responses_traceable
    def _general_chat() -> tuple[dict[str, str], str, int, int]:
        """Return the exact four-item adapter result shape.

        Returns:
            General-chat payload, provider request id, and token counts.
        """

        return (
            {"status": "complete", "answer_text": CANARY_PASSAGE},
            "resp-general-trace",
            20,
            4,
        )

    with _tracing_context(enabled=True, client=recorder):
        result = _general_chat()

    assert result[1] == "resp-general-trace"
    completed = [
        item
        for item in recorder.updated
        if isinstance(item.get("outputs"), dict)
        and item["outputs"].get("request_id") == "resp-general-trace"
    ]
    assert len(completed) == 1
    assert completed[0].get("end_time") is not None
    assert CANARY_PASSAGE not in json.dumps(completed, default=str)


def test_usage_metadata_is_attached_without_model_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recognized LangSmith usage fields carry counts and cost only."""

    from decimal import Decimal

    from smart_rag_core.observability import langsmith_tracing as tracing

    class _Run:
        """Minimal current-run stub that records usage metadata."""

        def __init__(self) -> None:
            """Initialize mutable metadata and an empty usage payload."""

            self.metadata: dict[str, object] = {}
            self.usage_metadata: dict[str, object] = {}

        def set(self, *, usage_metadata: dict[str, object]) -> None:
            """Record the usage payload passed by the tracing helper.

            Args:
                usage_metadata: LangSmith-recognized counts and costs.
            """

            self.usage_metadata = usage_metadata

    run = _Run()
    monkeypatch.setattr(tracing, "tracing_is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_current_run_tree", lambda: run)
    tracing.record_current_usage_metadata(
        provider="openai",
        model="text-embedding-3-large",
        input_tokens=123,
        output_tokens=0,
        total_cost_usd=Decimal("0.00001599"),
    )
    assert run.metadata == {
        "ls_provider": "openai",
        "ls_model_name": "text-embedding-3-large",
    }
    assert run.usage_metadata["input_tokens"] == 123
    assert run.usage_metadata["output_tokens"] == 0
    assert run.usage_metadata["total_tokens"] == 123
    assert run.usage_metadata["input_cost"] == pytest.approx(0.00001599)
    assert run.usage_metadata["output_cost"] == pytest.approx(0.0)
    assert run.usage_metadata["total_cost"] == pytest.approx(0.00001599)
    assert not payload_contains_forbidden_text(
        (run.metadata, run.usage_metadata),
        CANARY_TOKEN,
        CANARY_EMAIL,
        CANARY_PASSAGE,
    )


def test_record_gateway_response_usage_estimates_missing_usd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway responses without a cost field still attach a USD estimate."""

    from decimal import Decimal

    from smart_rag_core.gateways.model import RerankModelResponse
    from smart_rag_core.observability import langsmith_tracing as tracing
    from smart_rag_core.observability.langsmith_tracing import (
        estimate_traced_chat_cost_usd,
        record_gateway_response_usage,
    )

    class _Run:
        """Minimal current-run stub that records usage metadata."""

        def __init__(self) -> None:
            """Initialize mutable metadata and an empty usage payload."""

            self.metadata: dict[str, object] = {}
            self.usage_metadata: dict[str, object] = {}

        def set(self, *, usage_metadata: dict[str, object]) -> None:
            """Record the usage payload passed by the tracing helper.

            Args:
                usage_metadata: LangSmith-recognized counts and costs.
            """

            self.usage_metadata = usage_metadata

    run = _Run()
    monkeypatch.setattr(tracing, "tracing_is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_current_run_tree", lambda: run)
    response = RerankModelResponse(
        mode="openai",
        payload={"status": "complete"},
        request_id="req-rerank-1",
        input_tokens=200,
        output_tokens=40,
    )
    record_gateway_response_usage(response)
    expected = estimate_traced_chat_cost_usd(input_tokens=200, output_tokens=40)
    assert run.usage_metadata["input_tokens"] == 200
    assert run.usage_metadata["output_tokens"] == 40
    assert run.usage_metadata["total_tokens"] == 240
    assert run.usage_metadata["total_cost"] == pytest.approx(float(expected))
    payload = tracing.redact_gateway_outputs(response)
    assert payload["estimated_cost_usd"] == pytest.approx(float(expected))
    assert Decimal(str(payload["estimated_cost_usd"])) == expected


def test_lightrag_trace_exports_usage_cost_without_extract_text() -> None:
    """LightRAG spans expose token/cost metadata but never extract content."""

    from decimal import Decimal

    from smart_rag_core.gateways.model import (
        LightRagLlmRequest,
        LightRagLlmResponse,
    )
    from smart_rag_core.observability.langsmith_tracing import (
        redact_gateway_outputs,
        redact_lightrag_llm_call_outputs,
    )

    request = LightRagLlmRequest(
        role="extract",
        prompt=CANARY_PASSAGE,
        system_prompt=CANARY_TOKEN,
    )
    inputs = redact_gateway_inputs({"request": request})
    response = LightRagLlmResponse(
        mode="openai",
        content=f"entity-row {CANARY_EMAIL}",
        provider_request_id="resp_extract_1",
        model_id="gpt-4o-mini",
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=30,
        total_tokens=130,
        model_calls=1,
        estimated_cost_usd=Decimal("0.0000524"),
        pricing_version="openai-api-pricing-2026-08-19",
    )
    outputs = redact_gateway_outputs(response)
    helper_outputs = redact_lightrag_llm_call_outputs(
        {
            "output": (
                response.content,
                response.provider_request_id,
                response.input_tokens,
                response.cached_input_tokens,
                response.output_tokens,
                response.estimated_cost_usd,
            )
        }
    )
    assert redact_lightrag_llm_call_outputs(None) == {}
    assert inputs["role"] == "extract"
    assert outputs["total_tokens"] == 130
    assert outputs["estimated_cost_usd"] == pytest.approx(0.0000524)
    assert helper_outputs["cached_input_tokens"] == 20
    assert helper_outputs["total_tokens"] == 130
    assert not payload_contains_forbidden_text(
        (inputs, outputs, helper_outputs),
        CANARY_TOKEN,
        CANARY_EMAIL,
        CANARY_PASSAGE,
    )
