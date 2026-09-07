"""Contract tests for GET /conversations/{id}/messages transcript reads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.conversations import get_conversation_transcript_service
from smart_rag_api.services.conversation_transcript import (
    ConversationMessageRecord,
    ConversationTranscriptService,
    list_conversation_messages,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.contract.integration_support import (
    require_supabase_db_url,
    try_connect,
)
from tests.unit.typed_openapi import (
    OpenAPIClient,
    as_openapi_client,
    json_object,
    json_object_list,
    permit_test_identity,
)

_OWNER = "00000000-0000-4000-8000-000000000001"


def _identity(user_id: str = _OWNER, role: str = "member") -> dict[str, str]:
    """Return test identity headers.

    Args:
        user_id: Caller user id.
        role: Server role label.

    Returns:
        Header mapping for ``APP_ENV=test``.
    """

    return {
        "X-Test-User-Id": user_id,
        "X-Test-Role": role,
        "X-Test-Authorization-Version": "1",
    }


def _noop_rate_limit(*args: object, **kwargs: object) -> None:
    """Skip FastAPI-owned limiter in isolated HTTP tests.

    Args:
        *args: Ignored.
        **kwargs: Ignored.
    """

    del args, kwargs


class _FakeTranscriptService:
    """Canned transcript used by the HTTP contract."""

    def __init__(
        self,
        records: tuple[ConversationMessageRecord, ...] | None = None,
        *,
        error: QueryAdmissionError | None = None,
    ) -> None:
        """Store the canned page or error.

        Args:
            records: Newest-first records when the call succeeds.
            error: Raised instead of returning records.
        """

        self._records = records or ()
        self._error = error
        self.last_limit: int | None = None
        self.last_before: UUID | None = None

    def list(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        limit: int = 50,
        before_id: UUID | None = None,
    ) -> tuple[ConversationMessageRecord, ...]:
        """Return the canned page or raise the canned error.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.
            limit: Requested page size.
            before_id: Optional keyset cursor.

        Returns:
            Canned records.

        Raises:
            QueryAdmissionError: When constructed with an error.
        """

        del caller, conversation_id
        self.last_limit = limit
        self.last_before = before_id
        if self._error is not None:
            raise self._error
        records = self._records
        if before_id is not None:
            start = next(
                (
                    index + 1
                    for index, item in enumerate(records)
                    if item.message_id == before_id
                ),
                len(records),
            )
            records = records[start:]
        return records[:limit]


def _record(
    *,
    role: str,
    content: str,
    created_at: datetime,
    message_id: UUID | None = None,
) -> ConversationMessageRecord:
    """Build one transcript record.

    Args:
        role: ``user`` or ``assistant``.
        content: Escaped content.
        created_at: Persist timestamp.
        message_id: Optional id.

    Returns:
        Frozen transcript record.
    """

    return ConversationMessageRecord(
        message_id=message_id or uuid4(),
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=created_at,
    )


@contextmanager  # type: ignore[deprecated]
def _client(
    monkeypatch: pytest.MonkeyPatch,
    service: _FakeTranscriptService,
) -> Iterator[OpenAPIClient]:
    """Yield an OpenAPI client with the fake transcript service.

    Args:
        monkeypatch: Pytest monkeypatch.
        service: Fake service.

    Yields:
        Typed OpenAPI client.
    """

    permit_test_identity(monkeypatch)
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_conversation_transcript_service] = lambda: (
        service
    )
    with TestClient(application) as raw:
        yield as_openapi_client(raw)


def test_transcript_route_is_registered() -> None:
    """``GET /conversations/{id}/messages`` is in OpenAPI."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    methods = json_object(paths["/conversations/{conversation_id}/messages"])
    assert "get" in methods
    assert "post" in methods


def test_creator_receives_newest_first_user_and_assistant_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Creator GET returns newest-first user/assistant messages."""

    now = datetime.now(tz=UTC)
    newer = _record(role="assistant", content="answer", created_at=now)
    older = _record(
        role="user", content="question", created_at=now - timedelta(seconds=5)
    )
    service = _FakeTranscriptService((newer, older))
    conversation_id = uuid4()
    with _client(monkeypatch, service) as client:
        response = client.get(
            f"/conversations/{conversation_id}/messages",
            headers=_identity(),
        )
    assert response.status_code == 200
    body = json_object(response.json())
    items = json_object_list(body["items"])
    assert [item["role"] for item in items] == ["assistant", "user"]
    assert [item["content"] for item in items] == ["answer", "question"]
    assert body["next_before_id"] is None
    assert all(item["role"] in {"user", "assistant"} for item in items)


def test_second_page_via_before_has_no_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``before`` returns the next older page without repeating ids."""

    now = datetime.now(tz=UTC)
    first = _record(role="user", content="m1", created_at=now)
    second = _record(
        role="assistant", content="m2", created_at=now - timedelta(seconds=1)
    )
    third = _record(role="user", content="m3", created_at=now - timedelta(seconds=2))
    service = _FakeTranscriptService((first, second, third))
    conversation_id = uuid4()
    with _client(monkeypatch, service) as client:
        page_one = client.get(
            f"/conversations/{conversation_id}/messages?limit=2",
            headers=_identity(),
        )
        body_one = json_object(page_one.json())
        items_one = json_object_list(body_one["items"])
        cursor = body_one["next_before_id"]
        page_two = client.get(
            f"/conversations/{conversation_id}/messages?limit=2&before={cursor}",
            headers=_identity(),
        )
    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert cursor == str(second.message_id)
    items_two = json_object_list(json_object(page_two.json())["items"])
    ids_one = {item["message_id"] for item in items_one}
    ids_two = {item["message_id"] for item in items_two}
    assert ids_one.isdisjoint(ids_two)
    assert service.last_before == second.message_id


def test_other_user_receives_idor_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Foreign conversations return generic 404."""

    service = _FakeTranscriptService(error=QueryAdmissionError("not_found"))
    with _client(monkeypatch, service) as client:
        response = client.get(
            f"/conversations/{uuid4()}/messages",
            headers=_identity(str(uuid4()), "member"),
        )
    assert response.status_code == 404
    assert json_object(response.json())["detail"] == "not_found"


def test_unauthenticated_transcript_is_unauthorized() -> None:
    """Transcript GET requires a bearer token or test identity."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        response = client.get(f"/conversations/{uuid4()}/messages")
    assert response.status_code == 401


def test_limit_is_clamped_at_one_hundred(monkeypatch: pytest.MonkeyPatch) -> None:
    """``limit`` above 100 is rejected; 100 is accepted and passed through."""

    service = _FakeTranscriptService(())
    conversation_id = uuid4()
    with _client(monkeypatch, service) as client:
        rejected = client.get(
            f"/conversations/{conversation_id}/messages?limit=101",
            headers=_identity(),
        )
        accepted = client.get(
            f"/conversations/{conversation_id}/messages?limit=100",
            headers=_identity(),
        )
    assert rejected.status_code == 422
    assert accepted.status_code == 200
    assert service.last_limit == 100


def test_deleted_conversation_receives_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deleted conversations return the same generic 404."""

    service = _FakeTranscriptService(error=QueryAdmissionError("conversation_deleted"))
    with _client(monkeypatch, service) as client:
        response = client.get(
            f"/conversations/{uuid4()}/messages",
            headers=_identity(),
        )
    assert response.status_code == 404
    assert json_object(response.json())["detail"] == "not_found"


def _ensure_local_postgres() -> str:
    """Return the explicit ``SUPABASE_DB_URL`` when reachable, else skip.

    Returns:
        Postgres URL from ``SUPABASE_DB_URL``.

    Raises:
        pytest.skip: When the DSN is unset, hosted, or unreachable.
    """

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Postgres unreachable at {url}")
    connection.close()
    return url


@pytest.fixture
def db_url() -> str:
    """Yield the explicit ``SUPABASE_DB_URL`` or skip."""

    return _ensure_local_postgres()


@pytest.fixture
def db_connection(db_url: str) -> Iterator[psycopg.Connection]:
    """Yield one postgres-role connection with rollback on exit."""

    connection = psycopg.connect(db_url)
    connection.autocommit = False
    exists = connection.execute(
        """
        SELECT 1
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'app'
          AND p.proname = 'list_conversation_messages'
        """
    ).fetchone()
    if exists is None:
        connection.close()
        pytest.skip(
            "app.list_conversation_messages is not applied; run the P1 migration"
        )
    yield connection
    connection.rollback()
    connection.close()


def _insert_user_profile(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    role: str,
) -> None:
    """Insert one Auth user and application profile.

    Args:
        cursor: Open cursor.
        user_id: Auth user id.
        role: Profile role.
    """

    cursor.execute(
        """
        INSERT INTO auth.users (
          id, instance_id, aud, role, email, encrypted_password,
          email_confirmed_at, created_at, updated_at
        )
        VALUES (
          %s,
          '00000000-0000-0000-0000-000000000000'::uuid,
          'authenticated',
          'authenticated',
          %s,
          crypt('test-password', gen_salt('bf')),
          timezone('utc', now()),
          timezone('utc', now()),
          timezone('utc', now())
        )
        """,
        (user_id, f"{user_id}@example.com"),
    )
    cursor.execute(
        """
        INSERT INTO app.profiles (user_id, role, monthly_llm_budget_usd)
        VALUES (%s, %s::app.user_role, %s)
        """,
        (user_id, role, Decimal("200.00")),
    )


def _insert_conversation(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    """Insert one undeleted conversation.

    Args:
        cursor: Open cursor.
        user_id: Creator id.
        conversation_id: Conversation id.
    """

    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'transcript fixture')
        """,
        (conversation_id, user_id),
    )


def test_live_rpc_filters_roles_paginates_and_clamps(
    db_connection: psycopg.Connection,
) -> None:
    """Live RPC returns full user/assistant content, paginates, and clamps."""

    creator_id = uuid4()
    stranger_id = uuid4()
    conversation_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=creator_id, role="member")
        _insert_user_profile(cursor, user_id=stranger_id, role="owner")
        _insert_conversation(
            cursor, user_id=creator_id, conversation_id=conversation_id
        )
        for index in range(5):
            cursor.execute(
                """
                INSERT INTO app.messages (conversation_id, role, content, created_at)
                VALUES (
                  %s,
                  %s,
                  %s,
                  timezone('utc', now()) - (%s * interval '1 second')
                )
                """,
                (
                    conversation_id,
                    "user" if index % 2 == 0 else "assistant",
                    f"msg-{index}-" + ("x" * 20),
                    index,
                ),
            )
        cursor.execute(
            """
            INSERT INTO app.messages (conversation_id, role, content)
            VALUES (%s, 'system', 'hidden-system'), (%s, 'tool', 'hidden-tool')
            """,
            (conversation_id, conversation_id),
        )
        version_row = cursor.execute(
            "SELECT app.current_authorization_version()"
        ).fetchone()
        assert version_row is not None
        version = int(version_row[0])
    db_connection.commit()
    db_connection.execute("SET ROLE app_api")
    creator = CallerContext(
        user_id=str(creator_id),
        role=UserRole.MEMBER,
        authorization_version=version,
    )
    first_page = list_conversation_messages(
        db_connection,
        caller=creator,
        conversation_id=conversation_id,
        limit=2,
    )
    assert len(first_page) == 2
    assert all(item.role in {"user", "assistant"} for item in first_page)
    assert all("hidden-" not in item.content for item in first_page)
    assert "msg-0" in first_page[0].content
    second_page = list_conversation_messages(
        db_connection,
        caller=creator,
        conversation_id=conversation_id,
        limit=2,
        before_id=first_page[-1].message_id,
    )
    first_ids = {item.message_id for item in first_page}
    second_ids = {item.message_id for item in second_page}
    assert first_ids.isdisjoint(second_ids)
    stranger = CallerContext(
        user_id=str(stranger_id),
        role=UserRole.OWNER,
        authorization_version=version,
    )
    db_connection.execute("SAVEPOINT transcript_error")
    try:
        with pytest.raises(QueryAdmissionError, match="not_found"):
            list_conversation_messages(
                db_connection,
                caller=stranger,
                conversation_id=conversation_id,
            )
    finally:
        db_connection.execute("ROLLBACK TO SAVEPOINT transcript_error")
        db_connection.execute("RELEASE SAVEPOINT transcript_error")


def test_transcript_service_factory_matches_router_dependency() -> None:
    """Router factory returns the transcript service type."""

    from smart_rag_api.routers.conversations import (
        get_conversation_transcript_service,
    )

    service = get_conversation_transcript_service("postgresql://unused")
    assert isinstance(service, ConversationTranscriptService)
