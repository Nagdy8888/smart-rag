"""One context connection is reused for every load in a retrieve."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_agents.query.runtime.adapters_hybrid import (
    context_loader_for_connection,
)
from smart_rag_core.security.identity import CallerContext, UserRole


def test_context_loader_for_connection_reuses_the_given_connection(
    monkeypatch,
) -> None:
    """Two loads use the injected connection and do not open another."""

    connection = object()
    seen: list[object] = []

    def _fetch(
        bound: object,
        *,
        caller: CallerContext,
        chunk_ids: tuple[object, ...],
    ) -> tuple[()]:
        """Record the connection and return no rows.

        Args:
            bound: Connection passed by the loader.
            caller: Retrieve caller.
            chunk_ids: Requested IDs.

        Returns:
            Empty authorized context.
        """

        del caller, chunk_ids
        seen.append(bound)
        return ()

    def _connect(*_args: object, **_kwargs: object) -> object:
        """Fail if the shared loader opens a connection.

        Returns:
            Never.

        Raises:
            AssertionError: Always.
        """

        raise AssertionError("connect_postgres must not run")

    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.adapters_hybrid.fetch_authorized_chunk_context",
        _fetch,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.adapters_hybrid.connect_postgres",
        _connect,
    )
    loader = context_loader_for_connection(
        connection,  # type: ignore[arg-type]
        CallerContext(
            user_id=str(uuid4()),
            role=UserRole.MEMBER,
            authorization_version=1,
        ),
    )
    first = uuid4()
    second = uuid4()
    assert loader((first,)) == ()
    assert loader((second,)) == ()
    assert seen == [connection, connection]
