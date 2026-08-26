"""Compatibility composition of SSE persist, settlement, and cancel helpers."""

from smart_rag_api.services.sse.event_append import EventAppendMixin
from smart_rag_api.services.sse.replay_cancel import ReplayCancelMixin
from smart_rag_api.services.sse.run_settlement import RunSettlementMixin


class SsePersistMixin(EventAppendMixin, RunSettlementMixin, ReplayCancelMixin):
    """Compatibility mixin: durable append, resume replay, and reservation true-up."""
