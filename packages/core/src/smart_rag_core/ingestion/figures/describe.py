"""Deny-by-default figure descriptions with durable send and budget guards."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import psycopg
from smart_rag_core.gateways.openai_figure import execute_figure_description
from smart_rag_core.ingestion.figures.limits import FIGURE_MAX_PNG_BYTES
from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.jobs.ledger import JobOperationLedger
from smart_rag_core.models.env_pins import ANSWER_MODEL_ID
from smart_rag_core.security.external_processing import (
    ExternalProcessingDecisionInput,
    decide_external_processing,
)
from smart_rag_core.settings.base import SharedSettings

# A conservative hold, never represented as a measured provider bill.
FIGURE_RESERVED_USD = Decimal("0.05")


def figure_describer(
    *,
    mock_model_mode: bool,
    governance: ExternalProcessingDecisionInput,
    postgres_url: str,
    job_id: UUID,
    lease_token: str,
    operation_key: str,
) -> Callable[[bytes], str]:
    """Create a policy-gated, at-most-once operation for one leased job.

    Commit an attempted marker and conservative budget hold before sending.
    A crash or uncertain send never automatically retries. Successful descriptions
    and measured token counts replay without a send. Images/captions survive denial.
    """

    def describe(png: bytes) -> str:
        """Describe one bounded image only after durable admission."""
        if (
            mock_model_mode
            or not png
            or len(png) > FIGURE_MAX_PNG_BYTES
            or not decide_external_processing(governance).allowed
        ):
            return ""
        settings = SharedSettings()
        secret = settings.openai_api_key
        if secret is None:
            return ""
        key = f"{operation_key}:figure:{hashlib.sha256(png).hexdigest()}"
        with psycopg.connect(
            postgres_url,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=2000",
        ) as connection:
            connection.execute("SET ROLE app_worker")
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,)
            )
            ledger = JobOperationLedger(connection)
            result = ledger.fetch_result(
                job_table="ingestion_jobs", job_id=job_id, operation_key=key + ":result"
            )
            if result is not None:
                return str(result.get("description", ""))
            if (
                ledger.fetch_result(
                    job_table="ingestion_jobs",
                    job_id=job_id,
                    operation_key=key + ":attempt",
                )
                is not None
            ):
                return ""
            admission = JobAdmissionService(connection)
            reservation = admission.create_ingestion_budget_reservation(
                estimated_cost_usd=FIGURE_RESERVED_USD
            )
            admission.true_up_ingestion_reservation(
                reservation, actual_cost_usd=FIGURE_RESERVED_USD
            )
            ledger.record_completed(
                job_table="ingestion_jobs",
                job_id=job_id,
                operation_key=key + ":attempt",
                lease_token=lease_token,
                result_ref={
                    "state": "send_may_have_occurred",
                    "reserved_usd": str(FIGURE_RESERVED_USD),
                    "cost_basis": "conservative_cap",
                },
            )
            connection.commit()
        usage: dict[str, object] = {}

        def observe(input_tokens: int, output_tokens: int, request_id: str) -> None:
            """Keep measured provider tokens separate from the conservative hold."""
            usage.update(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider_request_id=request_id,
            )

        description = execute_figure_description(
            api_key=secret.get_secret_value(),
            model_id=ANSWER_MODEL_ID,
            image_png=png,
            timeout_seconds=20.0,
            usage_observer=observe,
        )
        with psycopg.connect(
            postgres_url,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=2000",
        ) as connection:
            connection.execute("SET ROLE app_worker")
            JobOperationLedger(connection).record_completed(
                job_table="ingestion_jobs",
                job_id=job_id,
                operation_key=key + ":result",
                lease_token=lease_token,
                result_ref={
                    "description": description,
                    "model_id": ANSWER_MODEL_ID,
                    **usage,
                },
            )
            connection.commit()
        return description

    return describe
