"""Counted verifier gateway bridge."""

from __future__ import annotations

from typing import Any, cast

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.assembly import assemble_source_records
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AtomicLink, VerifierPayload
from smart_rag_core.query_answer.versions import (
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
        AnswerError: If the gateway is unbound.
    """

    from smart_rag_core.gateways.model import VerifierModelRequest

    typed_tables = tuple(
        item
        if isinstance(item, TableEvidenceRecord)
        else TableEvidenceRecord.model_validate(item)
        for item in tables
    )
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
        VerifierPayload.model_validate(response.payload),
        prompt_tokens,
        completion_tokens,
    )
