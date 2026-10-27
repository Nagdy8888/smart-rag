"""Owner/admin overview; no model calls or private conversation exports."""

from enum import IntEnum
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Request, Response
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import UserRole

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.overview import OverviewResponse
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.documents_http import raise_document_error
from smart_rag_api.services.http_errors import raise_admission_http


class OverviewPeriod(IntEnum):
    """Explicit query periods; integer coercion accepts normal URL parameters."""

    WEEK = 7
    MONTH = 30
    QUARTER = 90


router = APIRouter(prefix="/admin", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def admin_overview(
    request: Request,
    response: Response,
    caller: CallerContextDep,
    postgres_url: Annotated[str, Depends(get_postgres_url)],
    days: OverviewPeriod = OverviewPeriod.MONTH,
) -> OverviewResponse:
    """Return bounded anonymous totals and currently authorized maintenance tasks."""
    response.headers["Cache-Control"] = "private, no-store"
    enforce_rate_limit(
        request,
        bucket_key=f"overview:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=60,
    )
    try:
        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET LOCAL ROLE app_api")
            connection.execute("SET LOCAL statement_timeout='10s'")
            row = connection.execute(
                "SELECT app.admin_overview(%s,%s,%s,%s)",
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    int(days),
                ),
            ).fetchone()
        if row is None:
            raise QueryAdmissionError("database_rejected")
        return OverviewResponse.model_validate(row[0])
    except psycopg.Error as exc:
        raise_document_error(exc)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
