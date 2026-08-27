"""Budgeted conversation summary generation and checkpoint compaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import cast
from uuid import UUID

import psycopg

from smart_rag_core.memory.payload import (
    memory_store_namespace,
    validate_memory_store_payload,
)
from smart_rag_core.models.env_pins import OPENAI_CHAT_MODEL_ID
from smart_rag_core.query_admission.ceilings import usage_kind_caps
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.security.identity import CallerContext

SUMMARY_WRITTEN = "written"
SUMMARY_DEFERRED = "summary_deferred"
SUMMARY_SKIPPED = "skipped"
SUMMARY_STORE_KEY = "summary"
_USAGE_KIND = "summary"


@dataclass(frozen=True, slots=True)
class SummaryOutcome:
    """Result of one budgeted summary attempt.

    Attributes:
        status: ``written``, ``summary_deferred``, or ``skipped``.
        summary_chars: Stored summary length when written.
        usage_id: Immutable ``llm_usage`` id when a counted call ran.
    """

    status: str
    summary_chars: int = 0
    usage_id: UUID | None = None


def compact_query_state(state: Mapping[str, object]) -> dict[str, object]:
    """Replace nested source copies with hashes/counts for checkpoints.

    Args:
        state: Query graph state mapping.

    Returns:
        A new mapping without raw ``citation_text``, ``passage``, ``snippet``,
        ``html``, or ``source`` string bodies. Files are never stored.

    Side Effects:
        None. Historical messages are not rewritten.
    """

    return cast(dict[str, object], _compact_value(state))


def maybe_generate_conversation_summary(
    connection: psycopg.Connection | None,
    *,
    caller: CallerContext,
    run_id: UUID,
    reservation_id: UUID,
    expected_version: int,
    remaining_model_calls: int,
    remaining_usd: Decimal,
    conversation_id: UUID,
    user_id: str,
    memory_records: tuple[Mapping[str, object], ...],
    send: Callable[[], str] | None = None,
    store_put: Callable[[tuple[str, str, str], str, dict[str, object]], None]
    | None = None,
) -> SummaryOutcome:
    """Generate one compact summary when the run envelope can afford it.

    Args:
        connection: ``app_api`` connection for counted consume, or None.
        caller: Server-derived run owner.
        run_id: Admitted run.
        reservation_id: Run-local reservation.
        expected_version: Optimistic reservation version.
        remaining_model_calls: Remaining counted gateway calls.
        remaining_usd: Remaining reservation USD.
        conversation_id: Conversation that owns the thread.
        user_id: Creator UUID string used in the store namespace.
        memory_records: Bounded untrusted message mappings (IDs/roles only
            are hashed; source documents are never passed).
        send: Optional summary producer. Default returns a mock compact line.
        store_put: Optional LangGraph store writer. When None, the counted
            call still runs so usage accounting is proven.

    Returns:
        Outcome. ``summary_deferred`` when the envelope cannot cover the
        summary cap. Never enlarges ceilings.

    Raises:
        StorePayloadError: When the produced payload includes source keys.

    Side Effects:
        May consume the run-local reservation with ``usage_kind=summary``
        and write one compact store item.
    """

    usd_cap, _, _ = usage_kind_caps(_USAGE_KIND)
    if remaining_model_calls < 1 or remaining_usd < usd_cap:
        return SummaryOutcome(status=SUMMARY_DEFERRED)
    if connection is None:
        return SummaryOutcome(status=SUMMARY_DEFERRED)

    producer = send if send is not None else _default_summary_text
    try:
        text, _consumed, usage_id = execute_counted_model_call(
            connection,
            caller=caller,
            run_id=run_id,
            reservation_id=reservation_id,
            expected_version=expected_version,
            usage_kind=_USAGE_KIND,
            model_id=OPENAI_CHAT_MODEL_ID,
            provider_attempt_id=f"summary:{run_id}",
            send=producer,
        )
    except (QueryBudgetError, QueryCeilingError):
        return SummaryOutcome(status=SUMMARY_DEFERRED)

    payload = validate_memory_store_payload(
        {
            "summary": str(text)[:2000],
            "memory_record_count": len(memory_records),
            "preferences": {},
        }
    )
    if store_put is not None:
        namespace = memory_store_namespace(
            company_id=None,
            user_id=user_id,
            conversation_id=str(conversation_id),
        )
        store_put(namespace, SUMMARY_STORE_KEY, payload)
    return SummaryOutcome(
        status=SUMMARY_WRITTEN,
        summary_chars=len(str(payload.get("summary", ""))),
        usage_id=usage_id,
    )


def put_validated_store_item(
    put: Callable[[tuple[str, str, str], str, dict[str, object]], None],
    *,
    namespace: tuple[str, str, str],
    key: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate then write one store item.

    Args:
        put: Store writer.
        namespace: Company/user/conversation namespace.
        key: Store key such as ``summary``.
        payload: Candidate mapping.

    Returns:
        The validated payload that was written.

    Raises:
        StorePayloadError: When the payload is not compact memory.

    Side Effects:
        Invokes ``put``.
    """

    compact = validate_memory_store_payload(payload)
    put(namespace, key, compact)
    return compact


def _default_summary_text() -> str:
    """Return a compact mock summary. No OpenAI call.

    Returns:
        Short preference/summary sentence.
    """

    return "Compact conversation summary; preferences only; no source copies."


def _compact_value(value: object) -> object:
    """Recursively replace source-document fields with hashes and counts.

    Args:
        value: Nested state value.

    Returns:
        Compacted value.
    """

    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        compact: dict[str, object] = {}
        for key, child in mapping.items():
            lowered = key.lower()
            if lowered in {"citation_text", "passage", "snippet", "html", "source"}:
                if isinstance(child, str) and child:
                    compact[f"{key}_sha256"] = sha256(
                        child.encode("utf-8")
                    ).hexdigest()[:16]
                    compact[f"{key}_chars"] = len(child)
                else:
                    compact[key] = child
                continue
            compact[key] = _compact_value(child)
        return compact
    if isinstance(value, list):
        return [_compact_value(item) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return tuple(_compact_value(item) for item in cast(tuple[object, ...], value))
    if isinstance(value, MutableMapping):
        return _compact_value(dict(cast(MutableMapping[str, object], value)))
    return value
