"""Security primitives shared across API, worker, and contract tests."""

from smart_rag_core.security.identity import CallerContext, UserRole

__all__ = ["CallerContext", "UserRole"]
