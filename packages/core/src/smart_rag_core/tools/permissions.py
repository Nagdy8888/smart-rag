"""Role and feature filtering that never leaks unauthorized catalog metadata."""

from __future__ import annotations

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.models import ToolDefinition

_ROLE_RANK: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.MEMBER: 1,
    UserRole.ADMIN: 2,
    UserRole.OWNER: 3,
}


def features_for_role(role: UserRole) -> frozenset[str]:
    """Return v1 features implied by the live role.

    Viewer has no optional-tool features. Member gains export/feedback.
    Admin and owner gain administration.

    Args:
        role: Live ``app.profiles.role``.

    Returns:
        Feature tokens used as required_features checks.
    """

    if role is UserRole.VIEWER:
        return frozenset()
    if role is UserRole.MEMBER:
        return frozenset({"export", "feedback"})
    if role is UserRole.ADMIN:
        return frozenset({"export", "feedback", "admin"})
    return frozenset({"export", "feedback", "admin", "owner"})


def is_authorized(
    tool: ToolDefinition,
    *,
    role: UserRole,
    features: frozenset[str] | None = None,
) -> bool:
    """Return whether the live caller may see or execute ``tool``.

    Disabled, undiscoverable, and under-privileged tools return False.
    Callers must not learn names or counts of unauthorized tools.

    Args:
        tool: Registry definition.
        role: Live role.
        features: Optional explicit features. Default is role-implied.

    Returns:
        True only when the tool is active, discoverable, and permitted.
    """

    if not tool.active or not tool.catalog_discoverable:
        return False
    granted = features if features is not None else features_for_role(role)
    if _ROLE_RANK[role] < _ROLE_RANK[tool.required_role]:
        return False
    needed = frozenset(tool.required_features)
    return needed <= granted


def visible_tools(
    registry: tuple[ToolDefinition, ...],
    *,
    role: UserRole,
    features: frozenset[str] | None = None,
) -> tuple[ToolDefinition, ...]:
    """Return authorized active tools only.

    Args:
        registry: Full in-code catalog.
        role: Live role.
        features: Optional explicit features.

    Returns:
        Filtered tuple. Order is the registry order among survivors.
    """

    return tuple(
        item for item in registry if is_authorized(item, role=role, features=features)
    )
