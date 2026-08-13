"""Isolated privileged Storage administration boundary.

Worker/admin list/delete/move/copy operations that require a broad Supabase
Storage credential live only under this package. General API, worker, frontend,
and SharedSettings must never load ``SUPABASE_STORAGE_ADMIN_SECRET``.
"""

from smart_rag_api.storage_admin.settings import (
    PrivilegedStorageSettings,
    load_privileged_storage_settings,
)

__all__ = [
    "PrivilegedStorageSettings",
    "load_privileged_storage_settings",
]
