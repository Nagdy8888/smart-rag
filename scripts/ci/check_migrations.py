"""Expand/contract migration policy checks for Phase 2 schema migrations."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"

ALLOWED_MIGRATION_PREFIXES = (
    "20260812131227_pgvector_gate_and_arabic_norm_v1.sql",
    "20260812135034_app_schemas_enums_job_columns_v1.sql",
    "20260812135038_profiles_company_invitations_v1.sql",
    "20260812135041_documents_sources_acl_v1.sql",
    "20260812135045_document_chunks_tables_search_v1.sql",
    "20260812135049_durable_jobs_v1.sql",
    "20260812135053_lightrag_maps_v1.sql",
    "20260812135056_conversations_messages_runs_v1.sql",
    "20260812135100_tools_catalog_v1.sql",
    "20260812135104_llm_usage_budgets_v1.sql",
    "20260812135107_audit_events_v1.sql",
    "20260812135111_langgraph_lightrag_private_v1.sql",
    "20260812135115_indexes_rls_grants_v1.sql",
    "20260812135916_roles_rls_identity_v1.sql",
    "20260813110152_authorization_acl_pool_safety_v1.sql",
    "20260813110914_auth_recovery_verification_v1.sql",
    "20260813112729_restricted_read_audit_v1.sql",
    "20260813120000_auth_jwks_invitations_v1.sql",
    "20260813140000_storage_quotas_graph_retention_v1.sql",
    "20260813150000_audit_chain_role_timeouts_v1.sql",
    "20260813160000_security_advisor_search_path_v1.sql",
    "20260813170000_job_leases_ledger_claim_v1.sql",
    "20260813180000_quarantine_scan_promotion_v1.sql",
    "20260813190000_crawl_snapshots_provenance_v1.sql",
    "20260813200000_hybrid_embedding_lifecycle_v1.sql",
    "20260814100000_langgraph_checkpoint_v9.sql",
    "20260814101000_retry_ingestion_job_v1.sql",
    "20260814102000_enqueue_approved_website_crawl_v1.sql",
    "20260814103000_document_status_uploading.sql",
    "20260814103100_reserve_uploading_version_v1.sql",
    "20260814103200_finalize_uploading_status_grants_v1.sql",
    "20260814103300_hybrid_ready_requires_bm25_job_v1.sql",
    "20260814103400_app_worker_extensions_usage_v1.sql",
    "20260814120000_glossary_import_v1.sql",
    "20260814130000_hybrid_retrieval_v1.sql",
    "20260814140000_hybrid_rerank_context_v1.sql",
    "20260814150000_structured_table_v1.sql",
    "20260815100000_hybrid_chunk_context_locators_v1.sql",
    "20260816090000_lightrag_vendor_pgtable_v1.sql",
    "20260816090100_graph_workspace_pointer_lease_v1.sql",
    "20260816100000_lightrag_job_heartbeat_budget_v1.sql",
    "20260816120000_graph_mapping_ready_v1.sql",
    "20260816130000_graph_resolver_query_v1.sql",
    "20260816140000_graph_entity_rules_v1.sql",
    "20260816150000_graph_pointer_switch_cleanup_v1.sql",
    "20260816160000_bm25_reconcile_and_ineligible_pointer_v1.sql",
    "20260816170000_query_run_admission_v1.sql",
    "20260816180000_query_memory_routing_v1.sql",
    "20260816190000_fastapi_security_rpcs_v1.sql",
    "20260816200000_query_run_events_v1.sql",
    "20260816210000_query_memory_store_reaper_v1.sql",
    "20260818140000_document_scan_events_worker_rls_v1.sql",
    "20260819100000_ingestion_status_acl_v1.sql",
    "20260819101000_citation_read_recheck_v1.sql",
    "20260819102000_list_pagination_v1.sql",
    "20260819103000_invitation_accept_guard_v1.sql",
    "20260819104000_profiles_update_self_freeze_v1.sql",
    "20260819105000_document_delete_rpc_v1.sql",
    "20260819110000_crawl_enqueue_server_policy_v1.sql",
    "20260819111000_graph_mapping_caller_rpc_v1.sql",
    "20260819120000_lightrag_chunk_map_vendor_chunk_uq_v1.sql",
    "20260824130000_query_run_messages_runtime_v1.sql",
    "20260824140000_remove_mfa_aal2_enforcement_v1.sql",
    "20260825200000_conversation_transcript_v1.sql",
    "20260826190000_conversation_title_v1.sql",
    "20260827120000_feedback_thumbs_polarity_tags_v1.sql",
    "20260827130000_get_visible_document_created_at_v1.sql",
    "20260827140000_tool_admin_catalog_overlay_v1.sql",
    "20260827160000_workspace_member_directory_v1.sql",
    "20260827170000_persist_run_citations_v1.sql",
    "20260827180000_summarize_run_usage_v1.sql",
    "20260827190000_summarize_run_usage_token_pricing_v1.sql",
    "20260827200000_summarize_account_usage_token_pricing_v1.sql",
    "20260909120000_detector_findings_reviews_v1.sql",
    "20260909130000_heading_inventory_v1.sql",
    "20260909140000_dense_candidates_v2.sql",
    "20260909150000_requested_search_scope_v1.sql",
    "20260910120000_list_run_citations_locators_v2.sql",
    "20260910133000_list_run_citations_page_label_v2.sql",
    "20260910140000_list_authorized_eval_passages_v1.sql",
    "20260910150000_eval_quiz_cases_v1.sql",
    "20260910160000_eval_exam_runs_v1.sql",
    "20260913170000_eval_exam_report_read_v1.sql",
    "20260914120000_web_research_evidence_v1.sql",
    "20260915120000_query_run_admission_web_v3.sql",
    "20260915140000_pdf_paragraph_citations_v1.sql",
)

DESTRUCTIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE"),
    (re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE), "DROP COLUMN"),
    (re.compile(r"\bDROP\s+TYPE\b", re.IGNORECASE), "DROP TYPE"),
    # DROP CONSTRAINT of a CHECK is allowed for additive allowed-value widening
    # (Phase 6 query_run). DROP COLUMN / DROP TABLE remain forbidden.
    (
        re.compile(
            r"\bALTER\s+TABLE\b[^;]*\bDROP\s+(?!CONSTRAINT\b)",
            re.IGNORECASE,
        ),
        "ALTER ... DROP",
    ),
    (
        re.compile(
            r"\bALTER\s+COLUMN\b[^;]*\bTYPE\b[^;]*\bUSING\b",
            re.IGNORECASE,
        ),
        "ALTER ... TYPE narrowing",
    ),
    (
        re.compile(r"\bCREATE\s+EXTENSION\b[^;]*\bpg_search\b", re.IGNORECASE),
        "CREATE EXTENSION pg_search on Supabase",
    ),
)

SECURITY_DEFINER_PATTERN = re.compile(
    r"SECURITY\s+DEFINER",
    re.IGNORECASE,
)
SEARCH_PATH_PATTERN = re.compile(
    r"SET\s+search_path\s*=",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    """Remove block and line comments before static policy scanning."""

    without_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", without_block)


def _validate_security_definer(sql: str, path: Path, violations: list[str]) -> None:
    """Require explicit search_path on every SECURITY DEFINER function."""

    for match in SECURITY_DEFINER_PATTERN.finditer(sql):
        start = max(0, match.start() - 400)
        end = min(len(sql), match.end() + 400)
        window = sql[start:end]
        if not SEARCH_PATH_PATTERN.search(window):
            violations.append(
                f"{path.name}: SECURITY DEFINER without SET search_path near offset {match.start()}"
            )


def find_migration_violations(raw_sql: str, path: Path) -> list[str]:
    """Return expand/contract and privileged-function policy violations.

    Args:
        raw_sql: Migration SQL including comments.
        path: Migration path used in bounded diagnostics.

    Returns:
        Ordered policy violations found in the migration.
    """

    sql = _strip_sql_comments(raw_sql)
    violations = [
        f"{path.name}: forbidden {label}"
        for pattern, label in DESTRUCTIVE_PATTERNS
        if pattern.search(sql)
    ]
    _validate_security_definer(sql, path, violations)
    return violations


def main() -> int:
    """Validate Phase 2 migration expand/contract policy.

    Returns:
        ``0`` when all migration files pass policy checks; ``1`` otherwise.
    """

    if not MIGRATIONS.is_dir():
        print("No supabase/migrations directory", file=sys.stderr)
        return 1

    files = sorted(p for p in MIGRATIONS.glob("*.sql") if p.is_file())
    if not files:
        print("No migration files found", file=sys.stderr)
        return 1

    unknown = [
        path.name for path in files if path.name not in ALLOWED_MIGRATION_PREFIXES
    ]
    if unknown:
        print(
            "Unexpected migration files (update allowlist after review): "
            + ", ".join(unknown),
            file=sys.stderr,
        )
        return 1

    violations: list[str] = []
    for path in files:
        raw = path.read_text(encoding="utf-8")
        violations.extend(find_migration_violations(raw, path))

    if violations:
        for item in violations:
            print(item, file=sys.stderr)
        return 1

    print(f"Phase 2 migration policy OK ({len(files)} reviewed files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
