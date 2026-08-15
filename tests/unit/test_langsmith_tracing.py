"""Unit tests for redacted LangSmith tracing of every model call."""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langsmith import tracing_context
from smart_rag_core.gateways.embedding import EmbeddingRequest, create_embedding_gateway
from smart_rag_core.gateways.model import ModelRequest, create_model_gateway
from smart_rag_core.observability.langsmith_tracing import (
    LANGSMITH_HIDE_INPUTS_ENV,
    LANGSMITH_HIDE_OUTPUTS_ENV,
    LANGSMITH_TRACING_ENV,
    configure_langsmith,
    payload_contains_forbidden_text,
    redact_gateway_inputs,
    short_content_hash,
)
from smart_rag_core.observability.logging import correlation_context
from smart_rag_core.settings import (
    AgentSettings,
    SettingsValidationError,
    load_backend_settings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED_OPENAI_CTOR = {
    Path("packages/core/src/smart_rag_core/observability/langsmith_tracing.py"),
}
_ALLOWED_RESPONSES_CREATE = {
    Path("packages/core/src/smart_rag_core/gateways/openai_rerank.py"),
}
_ALLOWED_EMBEDDINGS_CREATE = {
    Path("packages/core/src/smart_rag_core/observability/langsmith_tracing.py"),
}
_SCAN_ROOTS = (
    Path("packages"),
    Path("apps"),
    Path("scripts"),
)

CANARY_TOKEN = "sk-canarysecretFORBID123456"  # noqa: S105 - inert leak canary
CANARY_EMAIL = "canary.user@example.com"
CANARY_PASSAGE = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"


class RecordingLangSmithClient:
    """In-memory LangSmith client that never opens a network connection."""

    def __init__(self) -> None:
        """Initialize empty create/update buffers."""

        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    def create_run(
        self,
        name: str,
        inputs: dict[str, Any],
        run_type: str = "chain",
        **kwargs: Any,
    ) -> None:
        """Record one create_run payload.

        Args:
            name: Run name.
            inputs: Run inputs after process_inputs.
            run_type: LangSmith run type.
            **kwargs: Additional SDK fields including outputs.
        """

        self.created.append(
            {
                "name": name,
                "inputs": inputs,
                "run_type": run_type,
                "kwargs": kwargs,
            }
        )

    def update_run(self, run_id: object, **kwargs: Any) -> None:
        """Record one update_run payload.

        Args:
            run_id: Run identifier.
            **kwargs: Output/end fields.
        """

        self.updated.append({"run_id": run_id, **kwargs})

    def __getattr__(self, name: str) -> Any:
        """Ignore unused Client methods used by RunTree internals.

        Args:
            name: Attribute requested by the SDK.

        Returns:
            A no-op callable.
        """

        def _ignored(*args: Any, **kwargs: Any) -> None:
            """Swallow unused SDK calls.

            Args:
                *args: Positional SDK arguments.
                **kwargs: Keyword SDK arguments.
            """

            return None

        return _ignored


def _python_files() -> tuple[Path, ...]:
    """Return authored production Python files under packages, apps, and scripts.

    Returns:
        Sorted relative paths.
    """

    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(
            path.relative_to(REPO_ROOT)
            for path in (REPO_ROOT / root).rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return tuple(sorted(files))


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
    assert applied[LANGSMITH_TRACING_ENV] == "false"


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


def test_mock_generate_is_traced_without_prompt_body() -> None:
    """Enabled tracing records model.generate without the prompt text."""

    recorder = RecordingLangSmithClient()
    gateway = create_model_gateway(AgentSettings())
    request = ModelRequest(prompt=f"probe {CANARY_PASSAGE}")
    with tracing_context(enabled=True, client=recorder):  # type: ignore[arg-type]
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
    with tracing_context(enabled=False, client=recorder):  # type: ignore[arg-type]
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
    with tracing_context(enabled=True, client=recorder):  # type: ignore[arg-type]
        asyncio.run(gateway.embed(request))
    names = [item["name"] for item in recorder.created]
    assert "embedding.embed" in names
    serialized = json.dumps(recorder.created + recorder.updated, default=str)
    assert CANARY_PASSAGE not in serialized


def _call_name(node: ast.AST) -> str | None:
    """Return a dotted call name when the callee is a Name or Attribute.

    Args:
        node: AST node, expected to be ``ast.Call``.

    Returns:
        Dotted name such as ``OpenAI`` or ``client.embeddings.create``.
    """

    if not isinstance(node, ast.Call):
        return None
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
        return ".".join(reversed(parts))
    return None


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
