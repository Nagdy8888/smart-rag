"""Unit tests for server-authoritative crawl enqueue policy."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

from smart_rag_api.services.crawl_enqueue import (
    CRAWL_SERVER_CONTENT_CLASS,
    CRAWL_SERVER_GRAPH_ELIGIBLE,
    enqueue_approved_website_crawl,
)


def test_crawl_enqueue_ignores_client_content_class_and_graph_eligible() -> None:
    """Owner/admin crawl enqueue still forces real_company and graph_eligible=false."""

    captured: dict[str, object] = {}
    row = {
        "document_id": uuid4(),
        "version_id": uuid4(),
        "source_id": uuid4(),
        "approval_id": uuid4(),
        "job_id": uuid4(),
    }

    class _Cursor:
        """Capture RPC bind parameters without opening Postgres."""

        def __enter__(self) -> _Cursor:
            """Return this cursor.

            Returns:
                The same cursor instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, _sql: str, params: object = None) -> None:
            """Record bind parameters from the enqueue RPC.

            Args:
                _sql: Unused SQL text.
                params: Positional bind values.
            """

            captured["params"] = params

        def fetchone(self) -> dict[str, Any]:
            """Return a stub enqueue result row.

            Returns:
                Identifier mapping expected by ``CrawlEnqueueOutcome``.
            """

            return row

    class _Connection:
        """Connection double used as a context manager."""

        def __enter__(self) -> _Connection:
            """Return this connection.

            Returns:
                The same connection instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, *_args: object, **_kwargs: object) -> None:
            """Ignore ``SET ROLE`` and other setup statements."""

            return None

        def cursor(self, **_kwargs: object) -> _Cursor:
            """Return the capturing cursor.

            Args:
                **_kwargs: Unused psycopg cursor kwargs.

            Returns:
                Stub cursor.
            """

            return _Cursor()

        def commit(self) -> None:
            """No-op commit."""

            return None

    with patch(
        "smart_rag_api.services.crawl_enqueue.psycopg.connect",
        return_value=_Connection(),
    ):
        enqueue_approved_website_crawl(
            "postgresql://unused",
            caller_user_id=uuid4(),
            caller_role="owner",
            caller_authorization_version=1,
            start_url="https://example.test/docs",
            approved_domain="example.test",
            idempotency_key="crawl-policy-unit",
            document_title="Example",
            max_depth=1,
            max_pages=5,
            content_class="synthetic",
            graph_eligible=True,
            attestation_policy_version="phase3_v1",
        )

    params = captured["params"]
    assert isinstance(params, tuple)
    assert params[9] == CRAWL_SERVER_CONTENT_CLASS
    assert params[9] == "real_company"
    assert params[10] is CRAWL_SERVER_GRAPH_ELIGIBLE
    assert params[10] is False
