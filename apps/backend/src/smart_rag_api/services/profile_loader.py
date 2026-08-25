"""Re-export profile snapshot helpers from core.

FastAPI identity keeps importing this module. The implementation lives in
``smart_rag_core.security.profile_snapshot`` so Studio live can reuse it
without importing the backend package.
"""

from __future__ import annotations

from smart_rag_core.security.profile_snapshot import (
    ProfileSnapshot,
    build_caller_context,
    is_session_revoked,
    load_profile_snapshot,
)

__all__ = [
    "ProfileSnapshot",
    "build_caller_context",
    "is_session_revoked",
    "load_profile_snapshot",
]
