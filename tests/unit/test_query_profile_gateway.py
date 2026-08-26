"""Query-profile gateway: mock safety, schema bounds, and live adapter pins."""

from __future__ import annotations

import asyncio
import inspect
import socket
from typing import cast

import pytest
from pydantic import ValidationError
from smart_rag_agents.prompts import query_profile_prompt_text
from smart_rag_agents.query.live_runtime import (
    QueryGraphProcessBindings,
    bind_profile_model_caller,
    build_query_graph_deps,
    build_query_process_bindings,
)
from smart_rag_core.gateways.model import (
    QueryProfileModelRequest,
    create_model_gateway,
)
from smart_rag_core.gateways.openai_profile import execute_openai_query_profile
from smart_rag_core.query_profile.schemas import query_profile_json_schema
from smart_rag_core.query_profile.versions import (
    ALLOWED_PROFILE_MODEL_IDS,
    PROFILE_MODEL_ID,
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import PreparationModelPayload
from smart_rag_core.settings import AgentSettings, SharedSettings


def test_mock_query_profile_uses_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock profile classification does not resolve DNS or retrieve."""

    def _deny(*_args: object, **_kwargs: object) -> None:
        """Fail if mock generation attempts DNS.

        Args:
            *_args: Unexpected positional arguments.
            **_kwargs: Unexpected keyword arguments.
        """

        raise AssertionError("mock query profile attempted network resolution")

    monkeypatch.setattr(socket, "getaddrinfo", _deny)
    gateway = create_model_gateway(AgentSettings())
    response = asyncio.run(
        gateway.generate_query_profile(QueryProfileModelRequest(query="hi my friend"))
    )
    assert response.mode == "mock"
    assert response.model_calls == 1
    assert response.retrieval_performed is False
    assert response.payload["knowledge_scope"] == KnowledgeScope.GENERAL_KNOWLEDGE.value
    assert response.payload["knowledge_scope_confidence"] == 0.95
    assert "scope_degradation_reason" not in response.payload


def test_mock_profile_classifies_company_and_conflict() -> None:
    """Mock heuristics cover company, user-text, fixtures, and mixed conflict."""

    gateway = create_model_gateway(AgentSettings())

    async def _scope(query: str) -> str:
        """Return mock knowledge_scope for one query.

        Args:
            query: User text.

        Returns:
            Scope enum value.
        """

        response = await gateway.generate_query_profile(
            QueryProfileModelRequest(query=query)
        )
        return str(response.payload["knowledge_scope"])

    assert asyncio.run(_scope("What is our refund period?")) == (
        KnowledgeScope.COMPANY_DOCUMENTS.value
    )
    assert asyncio.run(_scope("Explain photosynthesis")) == (
        KnowledgeScope.GENERAL_KNOWLEDGE.value
    )
    assert (
        asyncio.run(_scope("Rewrite this paragraph: The sky is blue."))
        == KnowledgeScope.USER_SUPPLIED_TEXT.value
    )
    assert (
        asyncio.run(
            _scope("What is the capital of France and what is our refund period?")
        )
        == KnowledgeScope.AMBIGUOUS.value
    )
    ordinary = asyncio.run(
        gateway.generate_query_profile(
            QueryProfileModelRequest(query="What is the capital of Japan?")
        )
    )
    assert ordinary.payload["knowledge_scope"] == KnowledgeScope.GENERAL_KNOWLEDGE.value
    assert float(ordinary.payload["knowledge_scope_confidence"]) >= 0.85


def test_mock_query_profile_rejects_version_mismatch() -> None:
    """A wrong prompt hash fails closed before any fixture payload."""

    gateway = create_model_gateway(AgentSettings())
    with pytest.raises(ValueError, match="profile_prompt_version_mismatch"):
        asyncio.run(
            gateway.generate_query_profile(
                QueryProfileModelRequest(
                    query="Hello",
                    prompt_sha256="0" * 64,
                )
            )
        )


def test_query_profile_schema_forbids_extra_fields_and_over_bound_lists() -> None:
    """The strict schema rejects unknown fields and a fourth subquestion."""

    schema = query_profile_json_schema()
    assert schema["additionalProperties"] is False
    properties_raw = schema["properties"]
    assert isinstance(properties_raw, dict)
    properties = cast(dict[str, object], properties_raw)
    assert "scope_degradation_reason" not in properties
    subquestions = properties["subquestions"]
    assert isinstance(subquestions, dict)
    assert subquestions["maxItems"] == 3
    valid: dict[str, object] = {
        "rewrite": None,
        "query_type": None,
        "subquestions": [],
        "variants": [],
        "hl_keywords": [],
        "ll_keywords": [],
        "retrieval_profile_id": None,
        "metadata_filters": [],
        "confidence": 0.9,
        "relationship_intent": None,
        "knowledge_scope": KnowledgeScope.GENERAL_KNOWLEDGE.value,
        "knowledge_scope_confidence": 0.9,
    }
    payload = PreparationModelPayload.model_validate(valid)
    assert payload.knowledge_scope == KnowledgeScope.GENERAL_KNOWLEDGE.value
    with pytest.raises(ValidationError):
        PreparationModelPayload.model_validate(
            {**valid, "scope_degradation_reason": "profile_unavailable"}
        )
    with pytest.raises(ValidationError):
        PreparationModelPayload.model_validate(
            {**valid, "subquestions": ["a", "b", "c", "d"]}
        )


def test_live_profile_adapter_keeps_store_false() -> None:
    """The live adapter pins store=False, retries, schema, and gpt-4o-mini."""

    source = inspect.getsource(inspect.unwrap(execute_openai_query_profile))
    assert inspect.unwrap(execute_openai_query_profile) is not (
        execute_openai_query_profile
    )
    assert "store=False" in source
    assert "max_retries=0" in source
    assert "ALLOWED_PROFILE_MODEL_IDS" in source
    assert "PROFILE_PROMPT_VERSION" in source
    assert "PROFILE_PROMPT_SHA256" in source
    assert "tools=" not in source
    assert PROFILE_MODEL_ID == "gpt-4o-mini"
    assert PROFILE_MODEL_ID in ALLOWED_PROFILE_MODEL_IDS
    assert PROFILE_PROMPT_VERSION == "query_profile_v1"
    assert len(PROFILE_PROMPT_SHA256) == 64


def test_live_runtime_binds_profile_caller_and_actual_model_id() -> None:
    """FastAPI/live Studio deps bind a profile caller; local studio does not."""

    bindings = build_query_process_bindings(
        settings=SharedSettings(mock_model_mode=True),
        supabase_dsn="postgresql://unit@127.0.0.1:1/postgres",
    )
    assert bindings.query_profile_prompt_text == query_profile_prompt_text()
    assert bindings.profile_model_id == PROFILE_MODEL_ID
    deps = build_query_graph_deps(
        bindings=bindings,
        connection=None,
        cancel_check=None,
    )
    assert deps.model_caller is not None
    assert deps.profile_model_id == PROFILE_MODEL_ID
    assert deps.query_profile_prompt_text == query_profile_prompt_text()
    payload = deps.model_caller("hi my friend", ())
    assert payload.knowledge_scope == KnowledgeScope.GENERAL_KNOWLEDGE.value
    assert payload.knowledge_scope_confidence == 0.95


def test_bound_profile_caller_rejects_degradation_reason_in_payload() -> None:
    """The sync thunk treats a model-supplied degradation reason as malformed."""

    class _Gateway:
        """Return an illegal degradation field in the profile payload."""

        async def generate_query_profile(
            self, request: QueryProfileModelRequest
        ) -> object:
            """Return a payload that includes a server-only field.

            Args:
                request: Unused profile request.

            Returns:
                Object with an illegal ``payload``.
            """

            del request

            class _Response:
                """Minimal gateway response."""

                def __init__(self) -> None:
                    """Store an illegal server-only field on the payload."""

                    self.payload: dict[str, object] = {
                        "rewrite": None,
                        "query_type": None,
                        "subquestions": [],
                        "variants": [],
                        "hl_keywords": [],
                        "ll_keywords": [],
                        "retrieval_profile_id": None,
                        "metadata_filters": [],
                        "confidence": 0.9,
                        "relationship_intent": None,
                        "knowledge_scope": "general_knowledge",
                        "knowledge_scope_confidence": 0.9,
                        "scope_degradation_reason": "profile_unavailable",
                    }

            return _Response()

    caller = bind_profile_model_caller(
        gateway=_Gateway(),
        prompt_text=query_profile_prompt_text(),
        model_id=PROFILE_MODEL_ID,
        cancel_check=None,
    )
    with pytest.raises(ValueError, match="profile_malformed"):
        caller("Why is the sky blue?", ())


def test_query_graph_process_bindings_require_profile_prompt() -> None:
    """Process bindings expose the profile prompt used by live deps."""

    bindings = QueryGraphProcessBindings(
        hybrid_retriever=object(),  # type: ignore[arg-type]
        model_gateway=object(),
        graph_retriever=None,
        table_executor=None,
        answer_prompt_text="answer",
        general_chat_prompt_text="general",
        verifier_prompt_text="verifier",
        query_profile_prompt_text="query_profile",
        profile_model_id=PROFILE_MODEL_ID,
        supabase_dsn="postgresql://unit@127.0.0.1:1/postgres",
    )
    assert bindings.query_profile_prompt_text == "query_profile"
    assert bindings.profile_model_id == PROFILE_MODEL_ID
