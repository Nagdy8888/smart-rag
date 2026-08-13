"""Unit contracts for Storage Admin missing-object classification."""

from __future__ import annotations

import secrets
from collections.abc import Callable

import httpx
import pytest
from smart_rag_api.storage_admin import objects
from smart_rag_api.storage_admin.objects import StorageAdminError, delete_object
from smart_rag_api.storage_admin.settings import PrivilegedStorageSettings


def _settings() -> PrivilegedStorageSettings:
    """Return isolated Storage settings with an ephemeral fixture credential."""

    return PrivilegedStorageSettings.model_validate(
        {
            "SUPABASE_URL": "https://project.invalid",
            "SUPABASE_STORAGE_ADMIN_SECRET": secrets.token_urlsafe(48),
        }
    )


def _install_response(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Patch the boundary client with one deterministic mock transport."""

    real_client = httpx.Client

    def client_factory(*, timeout: float) -> httpx.Client:
        """Construct a real client backed by the supplied handler."""

        return real_client(
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(objects.httpx, "Client", client_factory)


def test_provider_no_such_key_envelope_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current HTTP 400/inner-404 missing envelope is retry success."""

    def handler(_request: httpx.Request) -> httpx.Response:
        """Return the current local Storage missing-object envelope."""

        return httpx.Response(
            400,
            json={
                "statusCode": "404",
                "error": "not_found",
                "message": "Object not found",
                "code": "NoSuchKey",
            },
        )

    _install_response(monkeypatch, handler)
    delete_object(
        _settings(),
        bucket="documents-quarantine",
        object_path="missing.txt",
    )


def test_arbitrary_bad_request_is_not_idempotent_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic HTTP 400 remains a hard Storage Admin failure."""

    def handler(_request: httpx.Request) -> httpx.Response:
        """Return a non-missing bad request."""

        return httpx.Response(
            400,
            json={
                "statusCode": "400",
                "error": "invalid_request",
                "code": "InvalidKey",
            },
        )

    _install_response(monkeypatch, handler)
    with pytest.raises(StorageAdminError, match="status=400"):
        delete_object(
            _settings(),
            bucket="documents-quarantine",
            object_path="bad.txt",
        )
