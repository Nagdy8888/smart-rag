"""Idempotent external-operation helper. Ambiguous sent rows never retry."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from smart_rag_core.web_research.exceptions import WebResearchError
from smart_rag_core.web_research.ports import WebOperationStore

T = TypeVar("T")


def run_recorded_operation(
    store: WebOperationStore,
    *,
    operation_key: str,
    kind: str,
    request_hash: str,
    worker: Callable[[], T],
) -> T | None:
    """Begin, mark sent, run ``worker``, and complete.

    Replayed successful operations skip ``worker`` and return ``None`` so
    the caller can continue from already-persisted sources. Ambiguous
    ``sent`` rows fail closed without a second provider call.

    Args:
        store: Persistence port.
        operation_key: Stable per-run key.
        kind: ``search``, ``contents``, or ``fetch``.
        request_hash: SHA-256 of the request body.
        worker: Provider call. Must not log secrets.

    Returns:
        Worker result, or ``None`` on successful replay.

    Raises:
        WebResearchError: Ambiguous or conflicting durable state.
        Exception: Worker failures after ``complete(ok=False)``.
    """

    begun = store.begin(
        operation_key=operation_key,
        kind=kind,
        request_hash=request_hash,
    )
    if begun.status == "ambiguous":
        raise WebResearchError("web_operation:ambiguous")
    if begun.replayed and begun.status == "succeeded":
        return None
    if begun.status == "succeeded":
        return None
    sent = store.mark_sent(operation_id=begun.operation_id)
    if sent.status == "ambiguous":
        raise WebResearchError("web_operation:ambiguous")
    try:
        result = worker()
    except Exception as exc:
        reason = getattr(exc, "reason", None)
        safe = reason if isinstance(reason, str) else "web_search_transport_failed"
        store.complete(
            operation_id=begun.operation_id,
            ok=False,
            failure_reason=safe[:64],
        )
        raise
    store.complete(operation_id=begun.operation_id, ok=True)
    return result
