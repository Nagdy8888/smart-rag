"""Privileged Auth Admin services (invitations and MFA recovery)."""

from smart_rag_api.auth_admin.settings import (
    PrivilegedAuthSettings,
    load_privileged_auth_settings,
)

__all__ = ["PrivilegedAuthSettings", "load_privileged_auth_settings"]
