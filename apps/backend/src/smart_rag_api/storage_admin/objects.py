"""Storage HTTP API helpers for privileged object lifecycle operations.

Deletes must go through the Supabase Storage HTTP API. Direct SQL mutation of
``storage.objects`` is not object deletion and is forbidden by Phase 2 Packet 5.
"""

from __future__ import annotations

from typing import cast
from urllib.parse import quote

import httpx

from smart_rag_api.storage_admin.settings import PrivilegedStorageSettings


class StorageAdminError(Exception):
    """Raised when a privileged Storage Admin HTTP operation fails."""


def _is_missing_object(response: httpx.Response) -> bool:
    """Recognize current Storage API missing-object responses.

    Args:
        response: Supabase Storage HTTP response.

    Returns:
        ``True`` for HTTP 404 or the current HTTP 400 envelope whose internal
        status/code explicitly identify ``NoSuchKey``.
    """

    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        payload: object = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = cast(dict[object, object], payload)
    return (
        error.get("statusCode") in {404, "404"}
        and error.get("error") == "not_found"
        and error.get("code") == "NoSuchKey"
    )


def delete_object(
    settings: PrivilegedStorageSettings,
    *,
    bucket: str,
    object_path: str,
    timeout_seconds: float = 30.0,
) -> None:
    """Delete one Storage object via the Storage HTTP API.

    Args:
        settings: Privileged Storage settings with admin secret.
        bucket: Private bucket id (for example ``documents-quarantine``).
        object_path: Object key inside the bucket. Leading slashes are stripped.
        timeout_seconds: HTTP timeout bound in seconds.

    Returns:
        None when the provider accepts the delete, including its validated
        missing-object response.

    Raises:
        StorageAdminError: On non-success responses other than a validated
            missing-object envelope.
        ValueError: When bucket or path is empty.

    Side Effects:
        Performs an authenticated DELETE against Supabase Storage. Does not
        execute SQL against ``storage.objects``.

    Idempotency:
        Safe to retry; provider 404 is treated as success after a prior delete.
    """

    normalized_bucket = bucket.strip()
    normalized_path = object_path.lstrip("/")
    if not normalized_bucket or not normalized_path:
        raise ValueError("bucket and object_path are required")

    base = str(settings.supabase_url).rstrip("/")
    # Storage API: DELETE /storage/v1/object/{bucket}/{path}
    encoded_path = "/".join(quote(part, safe="") for part in normalized_path.split("/"))
    url = f"{base}/storage/v1/object/{quote(normalized_bucket, safe='')}/{encoded_path}"
    headers = {
        "Authorization": (
            f"Bearer {settings.supabase_storage_admin_secret.get_secret_value()}"
        ),
        "apikey": settings.supabase_storage_admin_secret.get_secret_value(),
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.delete(url, headers=headers)
    except httpx.HTTPError as exc:
        raise StorageAdminError(f"storage delete transport failure: {exc}") from exc

    if response.status_code in {200, 204} or _is_missing_object(response):
        return
    raise StorageAdminError(f"storage delete failed status={response.status_code}")


def delete_objects(
    settings: PrivilegedStorageSettings,
    *,
    bucket: str,
    object_paths: list[str],
    timeout_seconds: float = 30.0,
) -> None:
    """Delete multiple Storage objects via the Storage HTTP API remove endpoint.

    Args:
        settings: Privileged Storage settings with admin secret.
        bucket: Private bucket id.
        object_paths: Object keys to remove.
        timeout_seconds: HTTP timeout bound in seconds.

    Raises:
        StorageAdminError: On non-success HTTP responses.
        ValueError: When bucket is empty or paths list is empty.

    Side Effects:
        POST ``/storage/v1/object/remove/{bucket}`` with JSON body. Retries are
        safe for duplicate removals.
    """

    normalized_bucket = bucket.strip()
    paths = [path.lstrip("/") for path in object_paths if path and path.strip()]
    if not normalized_bucket or not paths:
        raise ValueError("bucket and at least one object_path are required")

    base = str(settings.supabase_url).rstrip("/")
    url = f"{base}/storage/v1/object/remove/{quote(normalized_bucket, safe='')}"
    headers = {
        "Authorization": (
            f"Bearer {settings.supabase_storage_admin_secret.get_secret_value()}"
        ),
        "apikey": settings.supabase_storage_admin_secret.get_secret_value(),
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, headers=headers, json={"prefixes": paths})
    except httpx.HTTPError as exc:
        raise StorageAdminError(f"storage remove transport failure: {exc}") from exc

    if response.status_code not in {200, 204}:
        raise StorageAdminError(f"storage remove failed status={response.status_code}")
