"""Unit tests for conversation deletion HTTP, store payload, and compaction."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.conversations import get_conversation_service
from smart_rag_core.memory.payload import (
    StorePayloadError,
    validate_memory_store_payload,
)
from smart_rag_core.memory.summary import compact_query_state
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext

from tests.unit.typed_openapi import as_openapi_client, json_object

_OWNER = "00000000-0000-4000-8000-000000000001"
_MEMBER = "00000000-0000-4000-8000-000000000002"


def _identity(user_id: str, role: str) -> dict[str, str]:
    """Return APP_ENV=test identity headers.

    Args:
        user_id: Subject UUID.
        role: Role label.

    Returns:
        Header mapping.
    """

    return {
        "X-Test-User-Id": user_id,
        "X-Test-Role": role,
        "X-Test-Authorization-Version": "1",
    }


def _noop_rate_limit(*args: object, **kwargs: object) -> None:
    """Skip FastAPI rate limits in unit tests.

    Args:
        *args: Ignored.
        **kwargs: Ignored.
    """

    del args, kwargs


class _OwnerDeleteService:
    """Fake conversation service that succeeds for the owner only."""

    def delete(self, caller: CallerContext, *, conversation_id: UUID) -> None:
        """Allow the fixture owner and 404 everyone else.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.

        Raises:
            QueryAdmissionError: ``not_found`` for non-owners.
        """

        del conversation_id
        if str(caller.user_id) != _OWNER:
            raise QueryAdmissionError("not_found")


def test_owner_delete_returns_204(monkeypatch: pytest.MonkeyPatch) -> None:
    """Owner DELETE returns 204 with an empty body."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_conversation_service] = lambda: (
        _OwnerDeleteService()
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        deleted = client.delete(
            f"/conversations/{uuid4()}",
            headers=_identity(_OWNER, "owner"),
        )
    assert deleted.status_code == 204
    assert deleted.content == b""


def test_foreign_delete_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Foreign DELETE is 404, not 403, matching tombstone denial."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_conversation_service] = lambda: (
        _OwnerDeleteService()
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        deleted = client.delete(
            f"/conversations/{uuid4()}",
            headers=_identity(_MEMBER, "member"),
        )
    assert deleted.status_code == 404
    assert json_object(deleted.json())["detail"] == "not_found"


def test_store_rejects_source_document_keys() -> None:
    """LangGraph store writes fail closed on passage/snippet/html/source."""

    with pytest.raises(StorePayloadError, match="source_document_rejected"):
        validate_memory_store_payload({"passage": "full source copy"})
    with pytest.raises(StorePayloadError, match="source_document_rejected"):
        validate_memory_store_payload({"snippet": "bm25"})
    with pytest.raises(StorePayloadError, match="source_document_rejected"):
        validate_memory_store_payload({"html": "<p>doc</p>"})
    with pytest.raises(StorePayloadError, match="source_document_rejected"):
        validate_memory_store_payload({"source": "file.pdf"})
    compact = validate_memory_store_payload(
        {"summary": "preferences only", "preferences": {"locale": "en"}}
    )
    assert compact["summary"] == "preferences only"


def test_compact_query_state_hashes_citation_text() -> None:
    """Checkpoints replace citation_text with hashes and counts."""

    compacted = compact_query_state(
        {"fusion": {"citation_text": "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"}}
    )
    fusion = compacted["fusion"]
    assert isinstance(fusion, dict)
    assert "citation_text" not in fusion
    assert "citation_text_sha256" in fusion
    assert fusion["citation_text_chars"] == len("SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT")
    assert "SECRET_COMPANY_PASSAGE" not in str(compacted)


def test_usage_response_has_no_source_text_fields() -> None:
    """Company/user usage JSON cannot carry deleted conversation source text."""

    from smart_rag_api.schemas.fastapi_security import UsageResponse

    dumped = UsageResponse.model_json_schema()
    properties = json_object(dumped.get("properties", {}))
    forbidden = {"prompt", "query", "passage", "snippet", "html", "source", "message"}
    assert forbidden.isdisjoint(properties)
    assert set(properties) <= {
        "scope",
        "cost_usd",
        "prompt_tokens",
        "completion_tokens",
        "usage_rows",
    }
