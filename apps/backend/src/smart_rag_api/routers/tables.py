"""Thin authorized table manifest and bounded analysis routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.untrusted import isolate_untrusted_text
from smart_rag_core.tables.service import StructuredTableError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.fastapi_security import (
    TableAnalyzeRequest,
    TableAnalyzeResponse,
    TableManifestResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.tables_http import TableHttpService

router = APIRouter(prefix="/tables", tags=["tables"])


def get_table_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> TableHttpService:
    """Factory for table HTTP operations.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Table service.
    """

    return TableHttpService(postgres_url)


@router.get("", response_model=list[TableManifestResponse])
def list_table_manifests_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[TableHttpService, Depends(get_table_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> list[TableManifestResponse]:
    """List authorized current-version table manifests. No storage paths.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.
        limit: Page size, max 50.
        offset: Page offset.

    Returns:
        Manifest rows.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"table-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    records = service.list_manifests(caller, limit=limit, offset=offset)
    return [
        TableManifestResponse(
            table_id=item.table_id,
            document_id=item.document_id,
            version_id=item.version_id,
            table_name=item.table_name,
            sheet_name=item.sheet_name,
            row_count=item.row_count,
            column_count=item.column_count,
        )
        for item in records
    ]


@router.post("/analyze", response_model=TableAnalyzeResponse)
def analyze_table_route(
    request: Request,
    body: TableAnalyzeRequest,
    caller: CallerContextDep,
    service: Annotated[TableHttpService, Depends(get_table_service)],
) -> TableAnalyzeResponse:
    """Execute one extra-forbid TableQueryPlan.

    Args:
        request: Active request.
        body: Validated plan.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Deterministic values with escaped cell text.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"table-analyze:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=30,
    )
    try:
        result = service.analyze(caller, plan=body.plan)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except StructuredTableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_plan_rejected",
        ) from exc
    escaped_rows: tuple[dict[str, Any], ...] = tuple(
        {
            str(key): isolate_untrusted_text(value) if isinstance(value, str) else value
            for key, value in row.items()
        }
        for row in result.rows
    )
    return TableAnalyzeResponse(
        table_id=result.table_id,
        version_id=result.version_id,
        document_id=result.document_id,
        rows=escaped_rows,
        source_ranges=result.source_ranges,
    )
