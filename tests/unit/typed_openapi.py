"""Typed helpers for OpenAPI TestClient JSON access in unit tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast, runtime_checkable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smart_rag_api.main import create_app


def fastapi_app(client: TestClient) -> FastAPI:
    """Return the FastAPI application bound to an entered TestClient.

    Starlette types ``TestClient.app`` as a generic ASGI callable. Tests that
    read or write ``app.state`` need the concrete FastAPI instance.

    Args:
        client: Entered FastAPI TestClient.

    Returns:
        The wrapped FastAPI app.

    Raises:
        TypeError: If ``client.app`` is not a FastAPI instance.
    """

    application = client.app
    if not isinstance(application, FastAPI):
        raise TypeError("expected FastAPI application")
    return application


def client_app_state(client: TestClient) -> Any:
    """Return ``app.state`` from an entered TestClient.

    Args:
        client: Entered FastAPI TestClient.

    Returns:
        Starlette application state. Attribute types are untyped by Starlette.
    """

    return fastapi_app(client).state


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


def json_object_list(value: object) -> list[dict[str, object]]:
    """Narrow a decoded JSON value to a list of objects.

    Args:
        value: Decoded JSON value.

    Returns:
        List of string-keyed mappings.

    Raises:
        TypeError: If the value is not a JSON array of objects.
    """

    if not isinstance(value, list):
        raise TypeError("expected JSON array")
    items = cast(list[object], value)
    return [json_object(item) for item in items]


@runtime_checkable
class JsonResponse(Protocol):
    """HTTP response with JSON decoding used by OpenAPI unit tests."""

    status_code: int
    text: str
    content: bytes
    headers: Mapping[str, str]

    def json(self) -> object:
        """Return the decoded JSON body."""
        ...


@runtime_checkable
class OpenAPIClient(Protocol):
    """Subset of TestClient used by OpenAPI registration and RBAC tests."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> JsonResponse:
        """Send one GET request.

        Args:
            url: Request path.
            headers: Optional request headers.
        """
        ...

    def post(
        self,
        url: str,
        *,
        json: object | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> JsonResponse:
        """Send one POST request.

        Args:
            url: Request path.
            json: Optional JSON body.
            headers: Optional request headers.
            content: Optional raw body.
        """
        ...

    def delete(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> JsonResponse:
        """Send one DELETE request.

        Args:
            url: Request path.
            headers: Optional request headers.
        """
        ...


def as_openapi_client(client: object) -> OpenAPIClient:
    """Narrow a TestClient instance to the OpenAPI helper protocol.

    Args:
        client: Entered FastAPI TestClient.

    Returns:
        The same client typed for ``get`` / ``post`` / ``delete``.

    Raises:
        TypeError: If the object does not provide the expected methods.
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


def permit_test_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Permit ``X-Test-*`` headers for OpenAPI unit tests.

    Bypass is ``APP_ENV=test`` and ``ALLOW_TEST_IDENTITY=true``. Staging
    and production cannot enable the flag.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
