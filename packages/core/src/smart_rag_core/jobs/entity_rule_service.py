"""Owner/admin entity-rule RPCs. Suggestions never affect mapping until approved.

This service never writes Hybrid ``search_aliases`` and never patches vendor
``lightrag`` tables. Map invalidation SQL lives in
``entity_rule_invalidation`` / the security-definer RPC.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from smart_rag_core.jobs.entity_rules import (
    EntityRuleDraft,
    validate_entity_rule_draft,
)
from smart_rag_core.jobs.exceptions import GraphEntityRuleError
from smart_rag_core.jobs.extraction_policy import (
    ExtractionPolicySnapshot,
    default_extraction_policy,
    policy_from_row,
)
from smart_rag_core.retrieval.graph_mapping import EntityRuleView

LOGGER = logging.getLogger(__name__)

_REASON_CODES = (
    "forbidden",
    "stale_row_version",
    "alias_cycle",
    "alias_conflict",
    "duplicate_alias",
    "cross_type_alias",
    "unknown_entity_type",
    "do_not_merge_conflict",
    "rule_not_found",
    "already_approved",
    "already_revoked",
    "auto_approval_forbidden",
    "canonical_name_required",
    "invalid_alias_scope",
    "alias_limit",
    "confidence_out_of_range",
    "authorization context rejected",
)


@dataclass(frozen=True, slots=True)
class EntityRuleMutation:
    """Durable identifiers after create, update, approve, or revoke.

    Attributes:
        rule_id: Entity-rule primary key.
        status: ``suggested``, ``approved``, or ``revoked``.
        row_version: Optimistic concurrency token after the write.
        entity_rules_generation: Policy generation after any invalidation.
        rebuild_job_id: Scheduled rebuild job when maps were invalidated.
        repair_job_id: Bounded repair job when maps were invalidated.
        invalidated: True when approved-graph results were suppressed.
    """

    rule_id: UUID
    status: str
    row_version: int
    entity_rules_generation: int
    rebuild_job_id: UUID | None
    repair_job_id: UUID | None
    invalidated: bool


@dataclass(frozen=True, slots=True)
class EntityRuleRecord:
    """One entity-rule row for owner/admin listing.

    Attributes:
        id: Rule primary key.
        entity_type: Application type.
        canonical_name: Canonical name inside the type.
        display_label: Optional UI label.
        aliases: Alias strings.
        do_not_merge: Names that must stay distinct.
        languages: Language scope.
        alias_scope: ``company`` or ``synthetic_eval``.
        relation_label_policy: Directed or symmetric.
        status: Lifecycle status.
        active: True only when status is approved.
        row_version: Optimistic concurrency token.
        source: ``admin``, ``feedback``, or ``model``.
        reason: Curation or suggestion reason.
        confidence: Optional suggestion confidence.
        created_at: Insert timestamp.
        updated_at: Last update timestamp.
    """

    id: UUID
    entity_type: str
    canonical_name: str | None
    display_label: str | None
    aliases: tuple[str, ...]
    do_not_merge: tuple[str, ...]
    languages: tuple[str, ...]
    alias_scope: str
    relation_label_policy: str
    status: str
    active: bool
    row_version: int
    source: str
    reason: str
    confidence: float | None
    created_at: datetime | None
    updated_at: datetime | None


def _reason_from_db(exc: psycopg.Error) -> str:
    """Map a database error to a reason code without copying SQL detail.

    Args:
        exc: Driver error. Diagnostic text is not returned to callers.

    Returns:
        Stable reason code.
    """

    message = str(exc).lower()
    for code in _REASON_CODES:
        if code in message:
            return "forbidden" if code == "authorization context rejected" else code
    return "entity_rule_rejected"


def _as_str_tuple(value: object) -> tuple[str, ...]:
    """Return string items from a JSON/list column.

    Args:
        value: Database array, JSON list, or empty fallback.

    Returns:
        Tuple of stringified items.
    """

    items = cast(Sequence[object], value)
    return tuple(str(item) for item in items)


def _draft_payload(draft: EntityRuleDraft) -> dict[str, object]:
    """Return the JSON payload sent to security-definer RPCs.

    Args:
        draft: Validated draft.

    Returns:
        JSON-serializable mapping. Alias text is application-private.
    """

    return {
        "entity_type": draft.entity_type,
        "canonical_name": draft.canonical_name,
        "display_label": draft.display_label,
        "aliases": list(draft.aliases),
        "do_not_merge": list(draft.do_not_merge),
        "languages": list(draft.languages),
        "alias_scope": draft.alias_scope,
        "relation_label_policy": draft.relation_label_policy,
        "reason": draft.reason,
        "source": draft.source,
        "confidence": draft.confidence,
        "status": draft.status,
        "provenance": {"source": draft.source},
    }


def _mutation_from_row(row: dict[str, Any]) -> EntityRuleMutation:
    """Build a mutation result from an RPC row.

    Args:
        row: Database mapping.

    Returns:
        Typed mutation identifiers.
    """

    rebuild = row.get("rebuild_job_id")
    repair = row.get("repair_job_id")
    return EntityRuleMutation(
        rule_id=UUID(str(row["rule_id"])),
        status=str(row["status"]),
        row_version=int(row["row_version"]),
        entity_rules_generation=int(row.get("entity_rules_generation") or 1),
        rebuild_job_id=UUID(str(rebuild)) if rebuild is not None else None,
        repair_job_id=UUID(str(repair)) if repair is not None else None,
        invalidated=bool(row.get("invalidated")),
    )


def _record_from_row(row: dict[str, Any]) -> EntityRuleRecord:
    """Build a list record from an RPC row.

    Args:
        row: Database mapping.

    Returns:
        Typed rule record.
    """

    aliases = _as_str_tuple(row.get("aliases") or [])
    blocked = _as_str_tuple(row.get("do_not_merge") or [])
    languages = _as_str_tuple(row.get("languages") or [])
    confidence = row.get("confidence")
    return EntityRuleRecord(
        id=UUID(str(row["id"])),
        entity_type=str(row["entity_type"]),
        canonical_name=str(row["canonical_name"])
        if row.get("canonical_name")
        else None,
        display_label=str(row["display_label"]) if row.get("display_label") else None,
        aliases=aliases,
        do_not_merge=blocked,
        languages=languages,
        alias_scope=str(row.get("alias_scope") or "company"),
        relation_label_policy=str(row.get("relation_label_policy") or "directed"),
        status=str(row["status"]),
        active=bool(row.get("active")),
        row_version=int(row["row_version"]),
        source=str(row.get("source") or "admin"),
        reason=str(row.get("reason") or ""),
        confidence=float(confidence) if confidence is not None else None,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def load_extraction_policy(
    connection: psycopg.Connection,
) -> ExtractionPolicySnapshot:
    """Load the singleton extraction policy, or pinned defaults.

    Args:
        connection: Application connection.

    Returns:
        Policy snapshot used by mapping/query generation.
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
              entity_rules_generation,
              extraction_policy_hash,
              allowed_entity_types,
              allowed_languages,
              entity_extract_max_gleaning,
              json_mode,
              relation_label_policy
            FROM app.graph_extraction_policy
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        row = cursor.fetchone()
    if row is None:
        default = default_extraction_policy()
        return ExtractionPolicySnapshot(
            entity_rules_generation=1,
            extraction_policy_hash="",
            allowed_entity_types=default.allowed_entity_types,
            allowed_languages=default.allowed_languages,
            entity_extract_max_gleaning=default.entity_extract_max_gleaning,
            json_mode=default.json_mode,
            relation_label_policy=default.relation_label_policy,
        )
    snapshot = policy_from_row(row)
    if snapshot.entity_rules_generation <= 1:
        return ExtractionPolicySnapshot(
            entity_rules_generation=snapshot.entity_rules_generation,
            extraction_policy_hash="",
            allowed_entity_types=snapshot.allowed_entity_types,
            allowed_languages=snapshot.allowed_languages,
            entity_extract_max_gleaning=snapshot.entity_extract_max_gleaning,
            json_mode=snapshot.json_mode,
            relation_label_policy=snapshot.relation_label_policy,
        )
    return snapshot


def upsert_entity_rule(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    draft: EntityRuleDraft,
    rule_id: UUID | None = None,
    row_version: int | None = None,
    existing: tuple[EntityRuleView, ...] = (),
) -> EntityRuleMutation:
    """Create or update one entity rule as owner/admin.

    Feedback/model drafts cannot be inserted as approved. Approved writes
    invalidate maps and schedule a clean rebuild.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        draft: Validated rule draft.
        rule_id: Existing row when updating.
        row_version: Expected optimistic version when updating.
        existing: Approved views used for local cycle checks.

    Returns:
        Mutation identifiers.

    Raises:
        EntityRuleRejectedError: If local validation fails.
        GraphEntityRuleError: If the RPC rejects the caller or payload.

    Side Effects:
        Writes ``graph_entity_rules``, dual-writes ``rule jsonb``, may
        invalidate maps and enqueue rebuild. Appends an audit event.
        Never writes ``search_aliases``.
    """

    validate_entity_rule_draft(draft, existing=existing)
    return _call_mutation(
        postgres_url,
        function_name="upsert_graph_entity_rule",
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        rule_id=rule_id,
        row_version=row_version,
        payload=_draft_payload(draft),
    )


def suggest_entity_rule(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    draft: EntityRuleDraft,
    existing: tuple[EntityRuleView, ...] = (),
) -> EntityRuleMutation:
    """Store an inactive feedback/model suggestion. Never auto-approves.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        draft: Suggestion draft. Status is forced to ``suggested``.
        existing: Approved views for conflict checks.

    Returns:
        Mutation identifiers with ``invalidated=False``.

    Raises:
        EntityRuleRejectedError: If local validation fails.
        GraphEntityRuleError: If the RPC rejects the caller or payload.
    """

    forced = EntityRuleDraft(
        entity_type=draft.entity_type,
        canonical_name=draft.canonical_name,
        aliases=draft.aliases,
        do_not_merge=draft.do_not_merge,
        display_label=draft.display_label,
        languages=draft.languages,
        alias_scope=draft.alias_scope,
        relation_label_policy=draft.relation_label_policy,
        reason=draft.reason,
        source=draft.source if draft.source in {"feedback", "model"} else "feedback",
        confidence=draft.confidence,
        status="suggested",
    )
    validate_entity_rule_draft(forced, existing=existing)
    return _call_mutation(
        postgres_url,
        function_name="upsert_graph_entity_rule",
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        rule_id=None,
        row_version=None,
        payload=_draft_payload(forced),
    )


def approve_entity_rule(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    rule_id: UUID,
    row_version: int,
) -> EntityRuleMutation:
    """Explicitly approve a suggestion. Invalidates maps and schedules rebuild.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        rule_id: Suggestion identifier.
        row_version: Expected optimistic version.

    Returns:
        Mutation identifiers.

    Raises:
        GraphEntityRuleError: If approval is unauthorized or stale.
    """

    return _call_mutation(
        postgres_url,
        function_name="approve_graph_entity_rule",
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        rule_id=rule_id,
        row_version=row_version,
        payload={},
    )


def revoke_entity_rule(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    rule_id: UUID,
    row_version: int,
) -> EntityRuleMutation:
    """Revoke a rule. Approved revocations invalidate maps and schedule rebuild.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        rule_id: Rule identifier.
        row_version: Expected optimistic version.

    Returns:
        Mutation identifiers.

    Raises:
        GraphEntityRuleError: If revocation is unauthorized or stale.
    """

    return _call_mutation(
        postgres_url,
        function_name="revoke_graph_entity_rule",
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        rule_id=rule_id,
        row_version=row_version,
        payload={},
    )


def list_entity_rules(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
) -> tuple[EntityRuleRecord, ...]:
    """List entity rules for owner/admin. Members are rejected by the RPC.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.

    Returns:
        Rule records including inactive suggestions.

    Raises:
        GraphEntityRuleError: If the caller is unauthorized.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM app.list_graph_entity_rules(
                      %s::uuid, %s::text, %s::bigint
                    )
                    """,
                    (caller_user_id, caller_role, caller_authorization_version),
                )
                rows = cursor.fetchall()
            connection.commit()
    except psycopg.Error as exc:
        raise GraphEntityRuleError(_reason_from_db(exc)) from exc
    return tuple(_record_from_row(dict(row)) for row in rows)


def _call_mutation(
    postgres_url: str,
    *,
    function_name: str,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    rule_id: UUID | None,
    row_version: int | None,
    payload: dict[str, object],
) -> EntityRuleMutation:
    """Invoke one security-definer mutation and map errors to reason codes.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        function_name: ``upsert_graph_entity_rule``, approve, or revoke.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        rule_id: Target row when required.
        row_version: Expected optimistic version when required.
        payload: JSON body for upsert.

    Returns:
        Mutation identifiers.

    Raises:
        GraphEntityRuleError: If the RPC rejects the caller or payload.

    Side Effects:
        Persists the rule mutation and optional invalidation/rebuild.
    """

    sql_by_function: dict[str, LiteralString] = {
        "upsert_graph_entity_rule": """
            SELECT *
            FROM app.upsert_graph_entity_rule(
              %s::uuid, %s::text, %s::bigint, %s::uuid, %s::bigint, %s::jsonb
            )
        """,
        "approve_graph_entity_rule": """
            SELECT *
            FROM app.approve_graph_entity_rule(
              %s::uuid, %s::text, %s::bigint, %s::uuid, %s::bigint, %s::jsonb
            )
        """,
        "revoke_graph_entity_rule": """
            SELECT *
            FROM app.revoke_graph_entity_rule(
              %s::uuid, %s::text, %s::bigint, %s::uuid, %s::bigint, %s::jsonb
            )
        """,
    }
    sql = sql_by_function.get(function_name)
    if sql is None:
        raise GraphEntityRuleError("entity_rule_rejected")
    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    sql,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        rule_id,
                        row_version,
                        Json(payload),
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        LOGGER.info(
            "entity rule mutation rejected",
            extra={
                "event": "graph.entity_rules.rejected",
                "reason": _reason_from_db(exc),
            },
        )
        raise GraphEntityRuleError(_reason_from_db(exc)) from exc
    if row is None:
        raise GraphEntityRuleError("entity_rule_rejected")
    return _mutation_from_row(dict(row))
