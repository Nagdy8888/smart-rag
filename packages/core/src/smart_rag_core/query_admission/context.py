"""Server-derived authorized runtime context for the query graph."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Self, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import UserRole


def requested_search_scope_from_row(value: object) -> RequestedSearchScope:
    """Parse a stored or RPC search-scope value.

    Args:
        value: Database text, enum, or null for pre-migration rows.

    Returns:
        Typed requested scope. Null becomes ``AUTO``.

    Raises:
        ValueError: When a non-null value is not a known enum member.
    """

    if value is None:
        return RequestedSearchScope.AUTO
    return RequestedSearchScope(str(value))


class AuthorizedRuntimeContext(BaseModel):
    """Typed context FastAPI/core pass into ``apps/agents`` after durable admit.

    Every field is server-derived. Client JWT role, client budget, Valkey,
    cache, BM25, and graph output cannot populate or enlarge this object.

    Attributes:
        user_id: Authenticated subject from live ``app.profiles``.
        role: Live ``app.profiles.role``, never a JWT claim.
        authorization_version: Live company authorization snapshot.
        session_id: Optional refresh-session id used for revocation checks.
        conversation_id: Conversation that owns the run.
        run_id: Admitted or reconnected run.
        reservation_id: Run-local ``query_run`` reservation.
        reconnect: True when this admit reused an existing paid run.
        route_family: Server-selected envelope family.
        requested_search_scope: Client source preference fixed at admit.
        deadline_at: Absolute UTC deadline for the run.
        recursion_limit: LangGraph superstep cap.
        correction_ceiling: Maximum corrections.
        subquestion_ceiling: Maximum subquestions.
        model_call_ceiling: Maximum counted gateway calls.
        tool_ceiling: Maximum tool executions.
        discovery_ceiling: Maximum optional discovery rounds.
        manifest_ceiling: Maximum optional manifests.
        side_effect_ceiling: Maximum side-effecting tools.
        reserved_amount_usd: Envelope reserved at admit.
        remaining_usd: Remaining reservation USD after consumes.
        remaining_prompt_tokens: Remaining prompt-token hold.
        remaining_completion_tokens: Remaining completion-token hold.
        optimistic_version: Run-local reservation optimistic version.
        heartbeat_at: Last durable heartbeat.
        payload_hash: SHA-256 hex of the canonical request payload.
        status: Durable run status at admit/reconnect time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID
    role: UserRole
    authorization_version: int = Field(ge=1)
    session_id: str | None = None
    conversation_id: UUID
    run_id: UUID
    reservation_id: UUID
    reconnect: bool
    route_family: Phase6RouteFamily
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO
    deadline_at: datetime
    recursion_limit: int = Field(ge=1)
    correction_ceiling: int = Field(ge=0)
    subquestion_ceiling: int = Field(ge=0)
    model_call_ceiling: int = Field(ge=1)
    tool_ceiling: int = Field(ge=0)
    discovery_ceiling: int = Field(ge=0)
    manifest_ceiling: int = Field(ge=0)
    side_effect_ceiling: int = Field(ge=0)
    reserved_amount_usd: Decimal
    remaining_usd: Decimal
    remaining_prompt_tokens: int = Field(ge=0)
    remaining_completion_tokens: int = Field(ge=0)
    optimistic_version: int = Field(ge=1)
    heartbeat_at: datetime
    payload_hash: str = Field(min_length=64, max_length=64)
    status: str

    @classmethod
    def from_mapping(cls, payload: object) -> Self:
        """Validate a mapping into an authorized context.

        Args:
            payload: Mapping produced by FastAPI/core, never client claims.

        Returns:
            Frozen authorized runtime context.

        Raises:
            ValueError: When the payload is missing, not a mapping, or fails
                model validation.
        """

        if not isinstance(payload, dict):
            raise ValueError("authorized_runtime_missing")
        mapping = cast(dict[object, object], payload)
        typed: dict[str, object] = {str(key): value for key, value in mapping.items()}
        return cls.model_validate(typed)
