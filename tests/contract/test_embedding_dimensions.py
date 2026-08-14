"""Live OpenAI embedding dimension contract tests for Phase 2 qualification."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest
from openai import BadRequestError, OpenAI
from smart_rag_core.observability.langsmith_tracing import (
    configure_langsmith,
    traced_embeddings_create,
    traced_openai_client,
)
from smart_rag_core.settings.base import SharedSettings, load_settings


@dataclass(frozen=True)
class _EmbeddingCase:
    """One live embedding dimension qualification case."""

    case_id: str
    model: str
    dimensions: int | None = None


_CANDIDATES: tuple[_EmbeddingCase, ...] = (
    _EmbeddingCase("text-embedding-3-small-default", "text-embedding-3-small"),
    _EmbeddingCase("text-embedding-3-large-1536", "text-embedding-3-large", 1536),
    _EmbeddingCase("text-embedding-3-large-1024", "text-embedding-3-large", 1024),
)


def _live_openai_settings() -> SharedSettings | None:
    """Return settings when live OpenAI calls are permitted.

    Returns:
        Validated settings when mock mode is disabled and a key exists; else ``None``.
    """

    settings = load_settings(SharedSettings)
    if settings.mock_model_mode:
        return None
    if settings.openai_api_key is None:
        return None
    key = settings.openai_api_key.get_secret_value().strip()
    if not key or key.upper().startswith("REPLACE"):
        return None
    return settings


@pytest.fixture(scope="module")
def openai_client() -> OpenAI:
    """Construct one OpenAI client or skip when live credentials are unavailable."""

    settings = _live_openai_settings()
    if settings is None:
        pytest.skip("OPENAI_API_KEY missing or MOCK_MODEL_MODE enabled")
    assert settings.openai_api_key is not None
    configure_langsmith(settings)
    return traced_openai_client(api_key=settings.openai_api_key.get_secret_value())


@pytest.mark.parametrize("case", _CANDIDATES, ids=lambda case: case.case_id)
def test_supported_embedding_dimensions(
    openai_client: OpenAI,
    case: _EmbeddingCase,
) -> None:
    """Supported models return finite vectors at the requested dimension without substitution."""

    expected_dim = case.dimensions or 1536
    if case.dimensions is None:
        response = traced_embeddings_create(
            openai_client,
            input="Smart RAG embedding qualification probe.",
            model=case.model,
        )
    else:
        response = traced_embeddings_create(
            openai_client,
            input="Smart RAG embedding qualification probe.",
            model=case.model,
            dimensions=case.dimensions,
        )
    assert response.data
    vector = response.data[0].embedding
    assert len(vector) == expected_dim
    assert all(math.isfinite(value) for value in vector)
    assert response.model.startswith(case.model), (
        f"{case.case_id}: silent model substitution to {response.model}"
    )


def test_unsupported_embedding_dimension_raises(openai_client: OpenAI) -> None:
    """Unsupported dimensions fail explicitly instead of silently changing models."""

    with pytest.raises(BadRequestError):
        traced_embeddings_create(
            openai_client,
            model="text-embedding-3-large",
            input="dimension contract failure probe",
            dimensions=99999,
        )
