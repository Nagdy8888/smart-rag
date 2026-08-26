"""Compatibility mixin exporting lifecycle and persist helpers."""

from smart_rag_api.services.sse.answer_persistence import AnswerPersistenceMixin
from smart_rag_api.services.sse.stream_lifecycle import StreamLifecycleMixin


class LangGraphExecutorSupport(StreamLifecycleMixin, AnswerPersistenceMixin):
    """Compatibility mixin: termination, stream close, and post-terminal writes."""
