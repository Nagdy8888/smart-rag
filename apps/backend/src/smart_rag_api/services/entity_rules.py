"""HTTP adapter for owner/admin graph entity-rule RPCs."""

from __future__ import annotations

from uuid import UUID

from smart_rag_core.jobs.entity_rule_service import (
    EntityRuleMutation,
    approve_entity_rule,
    list_entity_rules,
    revoke_entity_rule,
    suggest_entity_rule,
    upsert_entity_rule,
)
from smart_rag_core.jobs.entity_rules import EntityRuleDraft

from smart_rag_api.schemas.entity_rules import (
    EntityRuleListItem,
    EntityRuleListResponse,
    EntityRuleMutationResponse,
    EntityRuleSuggestRequest,
    EntityRuleUpsertRequest,
)


def _draft_from_upsert(body: EntityRuleUpsertRequest) -> EntityRuleDraft:
    """Map an HTTP upsert body to a core draft.

    Args:
        body: Validated HTTP payload.

    Returns:
        Core entity-rule draft.
    """

    return EntityRuleDraft(
        entity_type=body.entity_type,
        canonical_name=body.canonical_name,
        aliases=tuple(body.aliases),
        do_not_merge=tuple(body.do_not_merge),
        display_label=body.display_label,
        languages=tuple(body.languages),
        alias_scope=body.alias_scope,
        relation_label_policy=body.relation_label_policy,
        reason=body.reason,
        source=body.source,
        confidence=body.confidence,
        status=body.status,
    )


def _draft_from_suggest(body: EntityRuleSuggestRequest) -> EntityRuleDraft:
    """Map an HTTP suggestion body to a core draft.

    Args:
        body: Validated HTTP payload.

    Returns:
        Inactive suggestion draft.
    """

    return EntityRuleDraft(
        entity_type=body.entity_type,
        canonical_name=body.canonical_name,
        aliases=tuple(body.aliases),
        do_not_merge=tuple(body.do_not_merge),
        display_label=body.display_label,
        languages=tuple(body.languages),
        alias_scope=body.alias_scope,
        relation_label_policy=body.relation_label_policy,
        reason=body.reason,
        source=body.source,
        confidence=body.confidence,
        status="suggested",
    )


def _mutation_response(outcome: EntityRuleMutation) -> EntityRuleMutationResponse:
    """Convert a core mutation into an HTTP response.

    Args:
        outcome: Durable mutation identifiers.

    Returns:
        HTTP mutation body. Alias text is omitted.
    """

    return EntityRuleMutationResponse(
        rule_id=outcome.rule_id,
        status=outcome.status,  # type: ignore[arg-type]
        row_version=outcome.row_version,
        entity_rules_generation=outcome.entity_rules_generation,
        rebuild_job_id=outcome.rebuild_job_id,
        repair_job_id=outcome.repair_job_id,
        invalidated=outcome.invalidated,
    )


def create_or_update_entity_rule(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    body: EntityRuleUpsertRequest,
    rule_id: UUID | None = None,
) -> EntityRuleMutationResponse:
    """Create or update one entity rule through the core jobs service.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        body: HTTP upsert body.
        rule_id: Existing row when updating.

    Returns:
        Mutation identifiers.
    """

    return _mutation_response(
        upsert_entity_rule(
            postgres_url,
            caller_user_id=caller_user_id,
            caller_role=caller_role,
            caller_authorization_version=caller_authorization_version,
            draft=_draft_from_upsert(body),
            rule_id=rule_id,
            row_version=body.row_version,
        )
    )


def create_entity_rule_suggestion(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    body: EntityRuleSuggestRequest,
) -> EntityRuleMutationResponse:
    """Store an inactive suggestion. Maps are not invalidated.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        body: HTTP suggestion body.

    Returns:
        Mutation identifiers with ``invalidated=False``.
    """

    return _mutation_response(
        suggest_entity_rule(
            postgres_url,
            caller_user_id=caller_user_id,
            caller_role=caller_role,
            caller_authorization_version=caller_authorization_version,
            draft=_draft_from_suggest(body),
        )
    )


def approve_entity_rule_http(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    rule_id: UUID,
    row_version: int,
) -> EntityRuleMutationResponse:
    """Approve a suggestion through the core jobs service.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        rule_id: Suggestion identifier.
        row_version: Expected optimistic version.

    Returns:
        Mutation identifiers.
    """

    return _mutation_response(
        approve_entity_rule(
            postgres_url,
            caller_user_id=caller_user_id,
            caller_role=caller_role,
            caller_authorization_version=caller_authorization_version,
            rule_id=rule_id,
            row_version=row_version,
        )
    )


def revoke_entity_rule_http(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    rule_id: UUID,
    row_version: int,
) -> EntityRuleMutationResponse:
    """Revoke a rule through the core jobs service.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        rule_id: Rule identifier.
        row_version: Expected optimistic version.

    Returns:
        Mutation identifiers.
    """

    return _mutation_response(
        revoke_entity_rule(
            postgres_url,
            caller_user_id=caller_user_id,
            caller_role=caller_role,
            caller_authorization_version=caller_authorization_version,
            rule_id=rule_id,
            row_version=row_version,
        )
    )


def list_entity_rules_http(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
) -> EntityRuleListResponse:
    """List rules for owner/admin.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.

    Returns:
        Rule listing including inactive suggestions.
    """

    records = list_entity_rules(
        postgres_url,
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
    )
    return EntityRuleListResponse(
        rules=tuple(
            EntityRuleListItem(
                id=item.id,
                entity_type=item.entity_type,
                canonical_name=item.canonical_name,
                display_label=item.display_label,
                aliases=item.aliases,
                do_not_merge=item.do_not_merge,
                languages=item.languages,
                alias_scope=item.alias_scope,
                relation_label_policy=item.relation_label_policy,
                status=item.status,  # type: ignore[arg-type]
                active=item.active,
                row_version=item.row_version,
                source=item.source,  # type: ignore[arg-type]
                reason=item.reason,
                confidence=item.confidence,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in records
        )
    )
