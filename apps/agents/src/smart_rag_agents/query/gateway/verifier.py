"""Counted verifier gateway bridge."""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
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

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    gateway_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response

_VERIFIER_REASON_MAX = 128


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
) -> tuple[VerifierPayload, int, int]:
    """Run one async gateway verifier call from the sync graph.

    Args:
        deps: Bound gateway and prompt.
        links: At most six atomic links.
        fusion: Canonical evidence.
        tables: Table records.
        context: Admitted run context used for the live deadline timeout.

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
    records = assemble_source_records(fusion, typed_tables)
    timeout_seconds = gateway_timeout_seconds(context)
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
    response = cast(
        Any,
        run_coro(
            lambda: cast(Any, gateway).generate_verifier(request),
            cancel_check=deps.cancel_check,
            timeout_seconds=request.remaining_deadline_seconds,
        ),
    )
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return (
        parse_verifier_payload(getattr(response, "payload", None)),
        prompt_tokens,
        completion_tokens,
    )
