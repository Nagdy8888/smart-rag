"""Permission-filtered tool catalog search and owner/admin seed writes."""

from __future__ import annotations

from uuid import UUID

import psycopg
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tools import (
    CORE_FORBIDDEN_TOOL_KEYS,
    default_registry,
    get_tool,
    visible_tools,
)
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import ToolDefinition


class ToolHttpService:
    """In-code registry is runtime authority. DB seed is expand-only."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN for admin seed writes.

        Args:
            postgres_url: Postgres URL.
        """

        self._postgres_url = postgres_url

    def search(
        self, caller: CallerContext, *, query: str | None = None
    ) -> tuple[ToolDefinition, ...]:
        """Return tools the live role may see. Rechecks role every call.

        Args:
            caller: Authenticated caller.
            query: Optional case-insensitive substring on key/name/purpose.

        Returns:
            Permission-filtered catalog subset. Unauthorized names are omitted.
        """

        visible = visible_tools(default_registry(), role=caller.role)
        if not query:
            return visible
        needle = query.casefold()
        return tuple(
            item
            for item in visible
            if needle in item.tool_key.casefold()
            or needle in item.short_name.casefold()
            or needle in item.one_line_purpose.casefold()
        )

    def upsert_seed(
        self,
        caller: CallerContext,
        *,
        tool_key: str,
        display_name: str,
        description: str,
        active: bool,
    ) -> UUID:
        """Owner/admin catalog seed. Unknown keys must already be allow-listed.

        Args:
            caller: Authenticated caller.
            tool_key: Catalog key.
            display_name: Display name.
            description: Description.
            active: Seed active flag. Executor still uses in-code ``active``.

        Returns:
            Catalog row id.

        Raises:
            QueryAdmissionError: Forbidden role, core key, or unknown tool.
        """

        self._require_admin(caller)
        if tool_key in CORE_FORBIDDEN_TOOL_KEYS:
            raise QueryAdmissionError("forbidden")
        try:
            get_tool(tool_key, registry=default_registry())
        except ToolError as exc:
            raise QueryAdmissionError("invalid_key") from exc
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT app.upsert_tool_catalog_seed(%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        tool_key,
                        display_name,
                        description,
                        active,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        if row is None:
            raise QueryAdmissionError("database_rejected")
        return UUID(str(row[0]))

    def enable(self, caller: CallerContext, *, tool_key: str, active: bool) -> UUID:
        """Owner/admin enable/disable seed for an allow-listed tool.

        Args:
            caller: Authenticated caller.
            tool_key: Catalog key.
            active: Seed flag.

        Returns:
            Catalog row id.
        """

        tool = self._require_allowlisted(tool_key)
        return self.upsert_seed(
            caller,
            tool_key=tool.tool_key,
            display_name=tool.short_name,
            description=tool.one_line_purpose,
            active=active,
        )

    def set_permission(
        self,
        caller: CallerContext,
        *,
        tool_key: str,
        target_role: UserRole,
        permission: str,
    ) -> UUID:
        """Owner/admin permission seed. Executor rechecks live role.

        Args:
            caller: Authenticated caller.
            tool_key: Catalog key.
            target_role: Role the seed applies to.
            permission: ``none`` / ``read`` / ``execute`` / ``admin``.

        Returns:
            Permission row id.
        """

        self._require_admin(caller)
        self._require_allowlisted(tool_key)
        if permission not in {"none", "read", "execute", "admin"}:
            raise QueryAdmissionError("invalid_key")
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT app.set_tool_permission(%s, %s, %s, %s, %s::app.user_role, %s::app.tool_permission_level)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        tool_key,
                        target_role.value,
                        permission,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        if row is None:
            raise QueryAdmissionError("database_rejected")
        return UUID(str(row[0]))

    def _require_admin(self, caller: CallerContext) -> None:
        """Reject members and viewers.

        Args:
            caller: Authenticated caller.

        Raises:
            QueryAdmissionError: ``forbidden``.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")

    def _require_allowlisted(self, tool_key: str) -> ToolDefinition:
        """Return the in-code tool or fail closed.

        Args:
            tool_key: Catalog key.

        Returns:
            Allow-listed definition.

        Raises:
            QueryAdmissionError: Unknown or core key.
        """

        if tool_key in CORE_FORBIDDEN_TOOL_KEYS:
            raise QueryAdmissionError("forbidden")
        try:
            return get_tool(tool_key, registry=default_registry())
        except ToolError as exc:
            raise QueryAdmissionError("invalid_key") from exc
