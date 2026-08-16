"""Typed helpers for OpenAPI TestClient JSON access in unit tests."""

from __future__ import annotations

from typing import Protocol, cast, runtime_checkable

from fastapi.testclient import TestClient
from smart_rag_api.main import create_app


def json_object(value: object) -> dict[str, object]:
    """Narrow a decoded JSON value to a string-keyed object.

    Args:
        value: Decoded JSON value.

    Returns:
        String-keyed mapping.

    Raises:
        TypeError: If the value is not a JSON object.
    """

    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    return cast(dict[str, object], value)


@runtime_checkable
class JsonResponse(Protocol):
    """HTTP response with JSON decoding used by OpenAPI unit tests."""

    status_code: int

    def json(self) -> object:
        """Return the decoded JSON body."""
        ...


@runtime_checkable
class OpenAPIClient(Protocol):
    """Subset of TestClient used by OpenAPI registration and RBAC tests."""

    def get(self, url: str) -> JsonResponse:
        """Send one GET request.

        Args:
            url: Request path.
        """
        ...

    def post(
        self,
        url: str,
        *,
        json: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> JsonResponse:
        """Send one POST request.

        Args:
            url: Request path.
            json: Optional JSON body.
            headers: Optional request headers.
        """
        ...


def as_openapi_client(client: object) -> OpenAPIClient:
    """Narrow a TestClient instance to the OpenAPI helper protocol.

    Args:
        client: Entered FastAPI TestClient.

    Returns:
        The same client typed for ``get`` / ``post``.

    Raises:
        TypeError: If the object does not provide ``get`` and ``post``.
    """

    if not isinstance(client, OpenAPIClient):
        raise TypeError("expected OpenAPI test client")
    return client


def openapi_test_client() -> TestClient:
    """Build one FastAPI TestClient for OpenAPI unit tests.

    Returns:
        TestClient bound to ``create_app()``.
    """

    return TestClient(create_app())
