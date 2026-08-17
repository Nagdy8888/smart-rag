"""Digest-bound candidate image records and mismatch rejection."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.release.constants import IMAGE_MANIFEST_SCHEMA_VERSION
from smart_rag_core.release.errors import CandidateDigestMismatchError


class CandidateImageRecord(BaseModel):
    """One locally built candidate image identity.

    Attributes:
        service: Compose service or profile image name.
        image_name: Docker image repository:tag.
        image_id: Docker image Id (``sha256:...``).
        repo_digest: Registry RepoDigest when present; otherwise none.
        created: Image created timestamp from ``docker inspect``.
        user: Container user recorded in the image config.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str = Field(min_length=1, max_length=64)
    image_name: str = Field(min_length=1, max_length=256)
    image_id: str = Field(min_length=10, max_length=128)
    repo_digest: str | None = None
    created: str = Field(min_length=1, max_length=64)
    user: str = Field(min_length=1, max_length=32)


class ImageDigestManifest(BaseModel):
    """Immutable candidate-image digest manifest.

    Attributes:
        schema_version: Frozen manifest schema.
        compose_file: Candidate Compose file used for the build.
        overlay_file: Always none; Packet 8 overlay is not candidate identity.
        images: Built application images.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-images-v1"] = (
        IMAGE_MANIFEST_SCHEMA_VERSION
    )
    compose_file: str
    overlay_file: None = None
    images: tuple[CandidateImageRecord, ...]


def reject_digest_mismatch(
    recorded: CandidateImageRecord,
    *,
    observed_image_id: str,
    observed_repo_digest: str | None = None,
) -> None:
    """Reject a running or rebuilt image that does not match the freeze.

    Args:
        recorded: Manifest row.
        observed_image_id: Live ``docker inspect`` Id.
        observed_repo_digest: Live RepoDigest when the engine reports one.

    Raises:
        CandidateDigestMismatchError: If Id or digest differs.
    """

    if recorded.image_id != observed_image_id:
        raise CandidateDigestMismatchError(
            f"image id mismatch for {recorded.service}: "
            f"recorded {recorded.image_id} observed {observed_image_id}"
        )
    if (
        recorded.repo_digest is not None
        and observed_repo_digest is not None
        and recorded.repo_digest != observed_repo_digest
    ):
        raise CandidateDigestMismatchError(
            f"repo digest mismatch for {recorded.service}: "
            f"recorded {recorded.repo_digest} observed {observed_repo_digest}"
        )


def identity_key(record: CandidateImageRecord) -> str:
    """Return the immutable identity string later packets must consume.

    Args:
        record: Manifest row.

    Returns:
        RepoDigest when present, otherwise the image Id.
    """

    if record.repo_digest:
        return record.repo_digest
    return record.image_id


def image_record_from_inspect(
    *,
    service: str,
    image_name: str,
    payload: dict[str, object],
) -> CandidateImageRecord:
    """Build a digest record from ``docker inspect`` JSON.

    Args:
        service: Compose service name.
        image_name: Image reference used for inspect.
        payload: First ``docker inspect`` object.

    Returns:
        Frozen image record.
    """

    image_id = str(payload.get("Id") or "")
    created = str(payload.get("Created") or "")
    user = "unspecified"
    config = payload.get("Config")
    if isinstance(config, dict):
        typed_config = cast(dict[str, object], config)
        raw_user = typed_config.get("User")
        if isinstance(raw_user, str) and raw_user:
            user = raw_user
    repo_digest: str | None = None
    repo_digests = payload.get("RepoDigests")
    if isinstance(repo_digests, list) and repo_digests:
        typed_digests = cast(list[object], repo_digests)
        first = typed_digests[0]
        if isinstance(first, str) and first:
            repo_digest = first
    return CandidateImageRecord(
        service=service,
        image_name=image_name,
        image_id=image_id,
        repo_digest=repo_digest,
        created=created,
        user=user,
    )
