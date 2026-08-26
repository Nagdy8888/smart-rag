"""ACL blindness disclosure and unauthorized suppression."""

from __future__ import annotations

from smart_rag_core.security.identity import CallerContext, UserRole


def disclose_acl_blindness(
    *,
    caller: CallerContext,
    count: int,
    authorized_visibility: bool,
) -> int | None:
    """Return ACL blindness only for the authorized visibility path.

    Unauthorized callers receive silence, not a zero that reveals existence.

    Args:
        caller: Server-derived caller.
        count: Resolver count for this caller.
        authorized_visibility: True only when this caller's resolver ran.

    Returns:
        The count, or None when suppressed.
    """

    del caller
    if not authorized_visibility:
        return None
    return count


def suppress_unauthorized_blindness(
    *,
    role: UserRole,
    count: int | None,
) -> int | None:
    """Hide injected privileged blindness counts from unauthorized roles.

    Args:
        role: Live profile role.
        count: Candidate count.

    Returns:
        None for viewer when the count did not come from their resolver.
        This helper is used by negative tests that inject a privileged count.
    """

    if count is None:
        return None
    if role is UserRole.VIEWER:
        return None
    return count
