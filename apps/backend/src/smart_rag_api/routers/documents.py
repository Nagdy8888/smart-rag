"""Thin document list/detail and signed-upload/finalize routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.fastapi_security import (
    DocumentResponse,
    FinalizeUploadHttpRequest,
    FinalizeUploadHttpResponse,
    SignedUploadRequest,
    SignedUploadResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.documents_http import (
    DocumentService,
    UploadFinalizeError,
    UploadQuotaError,
)
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.upload_finalize import UploadFinalizeRequest

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> DocumentService:
    """Factory for document HTTP operations.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Document service.
    """

    return DocumentService(postgres_url)


@router.get("", response_model=list[DocumentResponse])
def list_documents_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[DocumentService, Depends(get_document_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=80)] = None,
) -> list[DocumentResponse]:
    """List ACL-visible non-deleted documents.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.
        limit: Page size, default 50, max 200.
        cursor: Optional ``created_at,id`` keyset cursor.

    Returns:
        Visible documents with escaped titles, newest first.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"doc-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        records = service.list(caller, limit=limit, cursor=cursor)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return [
        DocumentResponse(
            document_id=item.document_id,
            title=item.title,
            visibility=item.visibility,
            current_version_id=item.current_version_id,
            visibility_generation=item.visibility_generation,
            created_at=item.created_at,
        )
        for item in records
    ]


@router.post("/uploads", response_model=SignedUploadResponse)
def reserve_upload_route(
    request: Request,
    body: SignedUploadRequest,
    caller: CallerContextDep,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> SignedUploadResponse:
    """Reserve quarantine upload quota. CloudFront signing is Phase 10.

    Args:
        request: Active request.
        body: Declared bytes and idempotency key.
        caller: Authenticated caller with upload capability.
        service: Injected service.

    Returns:
        Reservation, storage path, and ``signed_url=null`` locally.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"upload-start:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        reservation = service.reserve_upload(
            caller,
            declared_bytes=body.declared_bytes,
            idempotency_key=body.idempotency_key,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except UploadQuotaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="upload_quota_rejected",
        ) from exc
    return SignedUploadResponse(
        reservation_id=reservation.reservation_id,
        storage_bucket=reservation.storage_bucket,
        storage_path=reservation.storage_path,
        expires_at=reservation.effective_capability_expires_at,
        signed_url=None,
        upload_method="supabase_storage_jwt",
    )


@router.post("/uploads/finalize", response_model=FinalizeUploadHttpResponse)
def finalize_upload_route(
    request: Request,
    body: FinalizeUploadHttpRequest,
    caller: CallerContextDep,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> FinalizeUploadHttpResponse:
    """Finalize a reserved quarantine upload.

    Args:
        request: Active request.
        body: Object metadata and attestation.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Document, version, and job identifiers.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"upload-finalize:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    finalize_request = UploadFinalizeRequest(
        reservation_id=body.reservation_id,
        object_name=body.object_name,
        content_hash=body.content_hash,
        actual_bytes=body.actual_bytes,
        media_type=body.media_type,
        declared_category=body.declared_category,
        attestation_policy_version=body.attestation_policy_version,
        idempotency_key=body.idempotency_key,
        document_title=body.document_title,
    )
    try:
        outcome = service.finalize_upload(caller, request=finalize_request)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except UploadFinalizeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="upload_finalize_rejected",
        ) from exc
    return FinalizeUploadHttpResponse(
        reservation_id=outcome.reservation_id,
        document_id=outcome.document_id,
        version_id=outcome.version_id,
        job_id=outcome.job_id,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document_route(
    request: Request,
    document_id: UUID,
    caller: CallerContextDep,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    """Return one ACL-visible document.

    Args:
        request: Active request.
        document_id: Document id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Document summary.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"doc-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        record = service.get(caller, document_id=document_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return DocumentResponse(
        document_id=record.document_id,
        title=record.title,
        visibility=record.visibility,
        current_version_id=record.current_version_id,
        visibility_generation=record.visibility_generation,
        created_at=record.created_at,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_document_route(
    request: Request,
    document_id: UUID,
    caller: CallerContextDep,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Response:
    """Tombstone one document. Owner/admin only.

    Args:
        request: Active request for rate limits.
        document_id: Document id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Empty 204 body.

    Raises:
        HTTPException: 404 when missing or unauthorized; 403 when a visible
            document is not owner/admin-deletable.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"doc-delete:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        service.delete(caller, document_id=document_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
