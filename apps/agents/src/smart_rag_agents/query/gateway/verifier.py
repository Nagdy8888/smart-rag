"""Counted verifier gateway bridge."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from pydantic import ValidationError
from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.assembly import assemble_source_records
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AtomicLink, VerifierPayload
from smart_rag_core.query_answer.versions import (
    MAX_VERIFIER_LINKS,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.query_routing.preparation import caller_from_runtime

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    attempt_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.answer_attempts import ANSWER_ATTEMPT_CAP_SECONDS
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response

_VERIFIER_REASON_MAX = 128


class VerifierAttemptError(TimeoutAfterSendError):
    """Conservatively charged uncertain attempt with a safe cause code."""

    def __init__(self, reason: str) -> None:
        """Keep a stable provider failure code, never an exception message."""
        super().__init__(reason)
        self.reason = reason


def parse_verifier_payload(raw: object) -> VerifierPayload:
    """Parse one provider verifier JSON object into ``VerifierPayload``.

    Extra keys are dropped. Blank reasons become ``unspecified``. Reasons
    longer than 128 characters are truncated so a real verdict is kept.
    Support flags are never invented when the payload is garbage.

    Args:
        raw: Provider JSON object.

    Returns:
        Validated verifier batch.

    Raises:
        AnswerError: When the payload cannot be coerced into
            ``VerifierPayload`` without inventing support verdicts.
    """

    if not isinstance(raw, dict):
        raise AnswerError("verifier_schema_invalid")
    typed_raw = {
        str(key): value for key, value in cast(dict[object, object], raw).items()
    }
    verdicts_raw = typed_raw.get("link_verdicts")
    if not isinstance(verdicts_raw, list):
        raise AnswerError("verifier_schema_invalid")
    verdicts_list = cast(list[object], verdicts_raw)
    if len(verdicts_list) > MAX_VERIFIER_LINKS:
        raise AnswerError("verifier_batch_cap")
    cleaned: list[dict[str, object]] = []
    for item in verdicts_list:
        if not isinstance(item, dict):
            raise AnswerError("verifier_schema_invalid")
        typed_item = {
            str(key): value for key, value in cast(dict[object, object], item).items()
        }
        link_id = typed_item.get("link_id")
        if not isinstance(link_id, str) or not link_id.strip():
            raise AnswerError("verifier_schema_invalid")
        reason = str(typed_item.get("reason") or "").strip()
        if not reason:
            reason = "unspecified"
        cleaned.append(
            {
                "link_id": link_id,
                "supported": typed_item.get("supported"),
                "reason": reason[:_VERIFIER_REASON_MAX],
            }
        )
    try:
        return VerifierPayload.model_validate({"link_verdicts": cleaned})
    except ValidationError as exc:
        raise AnswerError("verifier_schema_invalid") from exc


def gateway_verifier(
    deps: QueryGraphDeps,
    *,
    links: tuple[AtomicLink, ...],
    fusion: FusionResult,
    tables: tuple[object, ...],
    context: AuthorizedRuntimeContext | None,
    on_consumed: Callable[[ReservationConsumeResult], None] | None = None,
) -> tuple[VerifierPayload, int, int]:
    """Run one async gateway verifier call from the sync graph.

    Args:
        deps: Bound gateway and prompt.
        links: At most six atomic links.
        fusion: Canonical evidence.
        tables: Table records.
        context: Admitted run context used for the live deadline timeout.
        on_consumed: Update the run's optimistic reservation snapshot.

    Returns:
        ``VerifierPayload`` plus provider prompt and completion tokens.

    Raises:
        AnswerError: If the gateway is unbound or the provider payload
            cannot be parsed as ``VerifierPayload``.
    """

    from smart_rag_core.gateways.model import VerifierModelRequest

    try:
        typed_tables = tuple(
            item
            if isinstance(item, TableEvidenceRecord)
            else TableEvidenceRecord.model_validate(item)
            for item in tables
        )
    except ValidationError as exc:
        raise AnswerError("verifier_schema_invalid") from exc
    # Only cited records can support this batch. Unrelated retrieval hits add
    # latency and distract the checker without supporting any selected claim.
    chunk_ids = {chunk_id for link in links for chunk_id in link.chunk_ids}
    table_ids = {link.table_id for link in links if link.table_id}
    selected_fusion = fusion.model_copy(
        update={
            "evidence": tuple(
                item for item in fusion.evidence if item.chunk_id in chunk_ids
            )
        }
    )
    records = assemble_source_records(
        selected_fusion,
        tuple(item for item in typed_tables if item.table_id in table_ids),
    )
    timeout_seconds = attempt_timeout_seconds(context, ANSWER_ATTEMPT_CAP_SECONDS)
    request = VerifierModelRequest(
        prompt_version=VERIFIER_PROMPT_VERSION,
        prompt_sha256=VERIFIER_PROMPT_SHA256,
        prompt_text=str(deps.verifier_prompt_text or "verifier"),
        source_records=records or " ",
        links=tuple(
            cast(dict[str, object], item.model_dump(mode="json")) for item in links
        ),
        remaining_deadline_seconds=timeout_seconds,
    )
    gateway = deps.model_gateway
    if gateway is None:
        raise AnswerError("model_gateway_unbound")

    def send() -> object:
        """Invoke once; conservatively account an uncertain sent attempt."""
        try:
            return run_coro(
                lambda: cast(Any, gateway).generate_verifier(request),
                cancel_check=deps.cancel_check,
                timeout_seconds=request.remaining_deadline_seconds,
            )
        except Exception as exc:
            # The gateway may fail after the provider accepted the request,
            # including response parsing. Do not record this as free work.
            allowed = {
                "verifier_timeout",
                "verifier_provider_error",
                "verifier_budget_denied",
                "verifier_schema_invalid",
                "verifier_incomplete",
                "verifier_output_limit",
                "verifier_content_filter",
                "verifier_refusal",
                "verifier_empty_output",
                "verifier_unknown_usage",
            }
            reason = (
                exc.reason
                if isinstance(exc, (OpenAIAnswerError, AnswerError))
                and exc.reason in allowed
                else "verifier_gateway_failed"
            )
            raise VerifierAttemptError(reason) from exc

    def usage(response: object) -> tuple[int, int, Decimal | None]:
        """Read actual provider tokens before validating semantic output."""
        prompt, completion = tokens_from_gateway_response(response)
        return prompt, completion, None

    if context is not None:
        if deps.connection is None:
            raise AnswerError("verifier_accounting_unavailable")
        response, consumed, _usage_id = execute_counted_model_call(
            deps.connection,
            caller=caller_from_runtime(context),
            run_id=context.run_id,
            reservation_id=context.reservation_id,
            expected_version=context.optimistic_version,
            usage_kind="verifier",
            model_id=request.model_id,
            provider_attempt_id=str(uuid4()),
            send=send,
            usage_from_result=usage,
        )
        if on_consumed is not None:
            on_consumed(consumed)
    else:
        # Unbound deterministic tests/Studio never receive a paid runtime.
        response = run_coro(
            lambda: cast(Any, gateway).generate_verifier(request),
            cancel_check=deps.cancel_check,
            timeout_seconds=request.remaining_deadline_seconds,
        )
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return (
        parse_verifier_payload(getattr(response, "payload", None)),
        prompt_tokens,
        completion_tokens,
    )
