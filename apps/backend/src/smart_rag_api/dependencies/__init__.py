"""FastAPI dependency package (ownership stub for later auth wiring)."""

from __future__ import annotations

from smart_rag_api.dependencies.identity import CallerContextDep, resolve_caller_context

__all__ = ["CallerContextDep", "resolve_caller_context"]
