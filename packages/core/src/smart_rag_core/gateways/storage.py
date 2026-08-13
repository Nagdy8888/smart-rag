"""Supabase Storage HTTP gateway for privileged object lifecycle operations."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

import httpx


class StorageGatewayError(Exception):
    """Raised when a Storage HTTP operation fails."""


@dataclass(frozen=True, slots=True)
class StorageObjectMetadata:
    """Verified object metadata from provider bytes."""

    bucket: str
    path: str
    byte_size: int
    content_hash_sha256: str
    media_type: str | None


@dataclass(frozen=True, slots=True)
class StorageGateway:
    """Privileged Storage REST client for worker/core ingestion boundaries."""

    supabase_url: str
    admin_secret: str
    timeout_seconds: float = 120.0

    def download_object(self, *, bucket: str, object_path: str) -> bytes:
        """Download one object stream through the Storage HTTP API.

        Args:
            bucket: Private bucket id.
            object_path: Object key without leading slash.

        Returns:
            Exact provider bytes.

        Raises:
            StorageGatewayError: On transport or non-success HTTP responses.
            ValueError: When bucket/path is empty.
        """

        url = self._object_url(bucket, object_path)
        headers = self._headers()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise StorageGatewayError(
                f"storage download transport failure: {exc}"
            ) from exc
        if response.status_code != 200:
            raise StorageGatewayError(
                f"storage download failed status={response.status_code}"
            )
        return response.content

    def copy_object(
        self,
        *,
        source_bucket: str,
        source_path: str,
        destination_bucket: str,
        destination_path: str,
    ) -> None:
        """Copy one object via the Storage HTTP API.

        Cross-bucket promotion uses download+upload because the provider copy
        endpoint is same-bucket oriented in local Supabase builds.

        Args:
            source_bucket: Source bucket id.
            source_path: Source object key.
            destination_bucket: Destination bucket id.
            destination_path: Destination object key.

        Raises:
            StorageGatewayError: On transport or non-success HTTP responses.
            ValueError: When required paths are empty.
        """

        source = source_path.lstrip("/")
        destination = destination_path.lstrip("/")
        if not source_bucket or not destination_bucket or not source or not destination:
            raise ValueError("source and destination bucket/path are required")

        if source_bucket == destination_bucket:
            base = self.supabase_url.rstrip("/")
            url = f"{base}/storage/v1/object/copy"
            headers = {**self._headers(), "Content-Type": "application/json"}
            body = {
                "bucketId": destination_bucket,
                "sourceKey": source,
                "destinationKey": destination,
            }
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                raise StorageGatewayError(
                    f"storage copy transport failure: {exc}"
                ) from exc
            if response.status_code not in {200, 201, 204}:
                raise StorageGatewayError(
                    f"storage copy failed status={response.status_code}"
                )
            return

        data = self.download_object(bucket=source_bucket, object_path=source)
        upload_url = self._object_url(destination_bucket, destination)
        headers = {
            **self._headers(),
            "Content-Type": "application/octet-stream",
            "x-upsert": "false",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(upload_url, headers=headers, content=data)
        except httpx.HTTPError as exc:
            raise StorageGatewayError(
                f"storage upload transport failure: {exc}"
            ) from exc
        if response.status_code not in {200, 201}:
            raise StorageGatewayError(
                f"storage upload failed status={response.status_code}"
            )

    def upload_object(
        self,
        *,
        bucket: str,
        object_path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload one immutable object via the Storage HTTP API.

        Args:
            bucket: Destination bucket id.
            object_path: Destination object key.
            data: Exact bytes to store.
            content_type: Provider content type header.

        Raises:
            StorageGatewayError: On transport or non-success HTTP responses.
            ValueError: When bucket/path is empty.
        """

        normalized_bucket = bucket.strip()
        normalized_path = object_path.lstrip("/")
        if not normalized_bucket or not normalized_path:
            raise ValueError("bucket and object_path are required")
        upload_url = self._object_url(normalized_bucket, normalized_path)
        headers = {
            **self._headers(),
            "Content-Type": content_type,
            "x-upsert": "false",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(upload_url, headers=headers, content=data)
        except httpx.HTTPError as exc:
            raise StorageGatewayError(
                f"storage upload transport failure: {exc}"
            ) from exc
        if response.status_code not in {200, 201}:
            raise StorageGatewayError(
                f"storage upload failed status={response.status_code}"
            )

    def delete_object(self, *, bucket: str, object_path: str) -> None:
        """Delete one object via the Storage HTTP API.

        Args:
            bucket: Bucket id.
            object_path: Object key.

        Raises:
            StorageGatewayError: On transport failures or unexpected responses.

        Side Effects:
            Provider DELETE; idempotent on validated missing-object envelopes.
        """

        normalized_bucket = bucket.strip()
        normalized_path = object_path.lstrip("/")
        if not normalized_bucket or not normalized_path:
            raise ValueError("bucket and object_path are required")

        url = self._object_url(normalized_bucket, normalized_path)
        headers = self._headers()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.delete(url, headers=headers)
        except httpx.HTTPError as exc:
            raise StorageGatewayError(
                f"storage delete transport failure: {exc}"
            ) from exc
        if response.status_code in {200, 204} or _is_missing_object(response):
            return
        raise StorageGatewayError(
            f"storage delete failed status={response.status_code}"
        )

    def verify_object(
        self,
        *,
        bucket: str,
        object_path: str,
        expected_hash: str,
        expected_bytes: int,
    ) -> StorageObjectMetadata:
        """Download and verify hash/size for promotion verification.

        Args:
            bucket: Bucket id.
            object_path: Object key.
            expected_hash: Lowercase SHA-256 hex digest.
            expected_bytes: Expected byte length.

        Returns:
            Verified metadata when hash and size match.

        Raises:
            StorageGatewayError: When verification fails or download fails.
        """

        data = self.download_object(bucket=bucket, object_path=object_path)
        digest = hashlib.sha256(data).hexdigest()
        if digest.lower() != expected_hash.lower():
            raise StorageGatewayError(
                f"hash mismatch expected={expected_hash} actual={digest}"
            )
        if len(data) != expected_bytes:
            raise StorageGatewayError(
                f"size mismatch expected={expected_bytes} actual={len(data)}"
            )
        return StorageObjectMetadata(
            bucket=bucket,
            path=object_path.lstrip("/"),
            byte_size=len(data),
            content_hash_sha256=digest.lower(),
            media_type=None,
        )

    def _object_url(self, bucket: str, object_path: str) -> str:
        """Build one object GET/DELETE URL."""

        normalized_bucket = bucket.strip()
        normalized_path = object_path.lstrip("/")
        encoded_path = "/".join(
            quote(part, safe="") for part in normalized_path.split("/")
        )
        base = self.supabase_url.rstrip("/")
        return f"{base}/storage/v1/object/{quote(normalized_bucket, safe='')}/{encoded_path}"

    def _headers(self) -> dict[str, str]:
        """Return authenticated Storage headers."""

        return {
            "Authorization": f"Bearer {self.admin_secret}",
            "apikey": self.admin_secret,
        }


def _is_missing_object(response: httpx.Response) -> bool:
    """Recognize current Storage API missing-object responses."""

    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = cast(dict[str, object], payload)
    status_code = error.get("statusCode")
    return (
        status_code in {404, "404"}
        and error.get("error") == "not_found"
        and error.get("code") == "NoSuchKey"
    )
