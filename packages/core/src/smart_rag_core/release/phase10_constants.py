"""Stable identifiers for Phase 10 Packets 1-7.

Packet 1 consumes the accepted Phase 9 promotion freeze. Packet 2 adds GitHub
OIDC, named SSM documents, and Secrets Manager placeholders. Packet 3 asserts
origin/egress/timeout/telemetry policy. Packet 4 classifies JWKS, origin
rotation, CDN SSE, ParadeDB degrade, and Valkey fail-closed. Packet 5 asserts
KMS/S3 Object Lock IaC, alarm routing, SES/OAuth/Storage support, pooling,
and the signed reduced envelope. Packet 6 classifies managed restore,
reconciliation, derived BM25 rebuild, instance rebuild, and skew/rollback.
Packet 7 aggregates Packets 1-6 matrices, records custody/IaC, documents
independent-assessment scope as not run, and writes a no-go Phase 11
manifest. None of these packets imply live AWS apply, managed PITR, EC2
rebuild, CloudFront/Vercel drain, or a completed pentest.
"""

from __future__ import annotations

PHASE10_ARTIFACT_DIR = "docs/deployment/phase-10"
PHASE09_ARTIFACT_DIR = "docs/deployment/phase-09"
INFRA_EC2_DIR = "infra/ec2"
STAGING_COMPOSE_FILE = "infra/ec2/docker-compose.staging.yml"
STAGING_T3MICRO_COMPOSE_FILE = "infra/ec2/docker-compose.t3micro.yml"
STAGING_CADDY_FILE = "infra/ec2/Caddyfile"
STAGING_CADDY_HTTP443_FILE = "infra/ec2/Caddyfile.http443"
INTENDED_TOPOLOGY_FILE = "infra/ec2/intended-topology.json"
VERCEL_PUBLIC_ENV_FILE = "infra/ec2/vercel-public-env.json"
PACKET1_LIVE_AWS_FILE = "docs/deployment/phase-10/packet1-live-aws.json"
PACKET1_LIVE_SCAN_FILE = "docs/deployment/phase-10/packet1-live-network-scan.json"
PACKET1_LIVE_VERCEL_FILE = "docs/deployment/phase-10/packet1-live-vercel.json"
PACKET1_LIVE_SUPABASE_FILE = "docs/deployment/phase-10/packet1-live-supabase.json"
PHASE09_PROMOTION_MANIFEST = (
    "docs/deployment/phase-09/candidate-packet7-promotion-manifest.json"
)
PHASE09_CORPUS_MANIFEST = "docs/deployment/phase-09/candidate-corpus-manifest.json"
PACKET1_MATRIX_NAME = "packet1-gate-matrix.json"
PACKET1_INVENTORY_NAME = "packet1-inventory.json"
PACKET1_IAC_NAME = "packet1-iac-policy.json"
PACKET1_LIVE_NAME = "packet1-live-providers.json"
PACKET1_NEGATIVES_NAME = "packet1-negatives.json"
PACKET2_MATRIX_NAME = "packet2-gate-matrix.json"
PACKET2_INVENTORY_NAME = "packet2-inventory.json"
PACKET2_IAC_NAME = "packet2-iac-policy.json"
PACKET2_LIVE_NAME = "packet2-live-providers.json"
PACKET2_NEGATIVES_NAME = "packet2-negatives.json"
PACKET2_MIGRATION_HASH_NAME = "packet2-migration-hash.json"
PACKET3_MATRIX_NAME = "packet3-gate-matrix.json"
PACKET3_ORIGIN_NAME = "packet3-origin.json"
PACKET3_EGRESS_NAME = "packet3-egress.json"
PACKET3_TIMEOUTS_NAME = "packet3-timeouts.json"
PACKET3_SCANS_NAME = "packet3-scans.json"
PACKET3_NEGATIVES_NAME = "packet3-negatives.json"
PACKET4_MATRIX_NAME = "packet4-gate-matrix.json"
PACKET4_JWKS_NAME = "packet4-jwks.json"
PACKET4_ORIGIN_NAME = "packet4-origin.json"
PACKET4_SSE_NAME = "packet4-sse.json"
PACKET4_PARADEDB_NAME = "packet4-paradedb.json"
PACKET4_VALKEY_NAME = "packet4-valkey.json"
PACKET4_NEGATIVES_NAME = "packet4-negatives.json"
PACKET5_MATRIX_NAME = "packet5-gate-matrix.json"
PACKET5_ANCHORS_NAME = "packet5-anchors.json"
PACKET5_ALARMS_NAME = "packet5-alarms.json"
PACKET5_INTEGRATIONS_NAME = "packet5-integrations.json"
PACKET5_POOL_NAME = "packet5-pool.json"
PACKET5_ENVELOPE_NAME = "packet5-envelope.json"
PACKET5_NEGATIVES_NAME = "packet5-negatives.json"
PACKET6_MATRIX_NAME = "packet6-gate-matrix.json"
PACKET6_INVENTORY_NAME = "packet6-inventory.json"
PACKET6_RECONCILE_NAME = "packet6-reconciliation.json"
PACKET6_REBUILD_NAME = "packet6-rebuild.json"
PACKET6_INSTANCE_NAME = "packet6-instance.json"
PACKET6_SKEW_NAME = "packet6-skew.json"
PACKET6_NEGATIVES_NAME = "packet6-negatives.json"
PACKET7_MATRIX_NAME = "packet7-gate-matrix.json"
PACKET7_SUITE_NAME = "packet7-suite.json"
PACKET7_CUSTODY_NAME = "packet7-custody.json"
PACKET7_ASSESSMENT_NAME = "packet7-assessment.json"
PACKET7_TRACEABILITY_NAME = "packet7-traceability.json"
PACKET7_NEGATIVES_NAME = "packet7-negatives.json"
PHASE10_PHASE11_PROMOTION_MANIFEST = (
    "docs/deployment/phase-10/phase10-phase11-promotion-manifest.json"
)
EXTERNAL_ASSESSMENT_SCOPE = "docs/security/phase-10-external-assessment-scope.md"
PHASE10_EVIDENCE = "docs/development/phase-10-managed-staging-evidence.md"
GITHUB_WORKFLOWS_DIR = ".github/workflows"
SSM_DOCUMENTS_DIR = "infra/ec2/ssm-documents"
MIGRATIONS_DIR = "supabase/migrations"
PHASE09_OLD_API_SMOKE = (
    "docs/deployment/phase-09/candidate-old-api-new-schema-smoke.json"
)

TOPOLOGY_SCHEMA_VERSION = "phase10-intended-topology-v1"
VERCEL_ENV_SCHEMA_VERSION = "phase10-vercel-public-env-v1"
PACKET1_MATRIX_SCHEMA_VERSION = "phase10-packet1-matrix-v1"
PACKET1_INVENTORY_SCHEMA_VERSION = "phase10-packet1-inventory-v1"
PACKET1_IAC_SCHEMA_VERSION = "phase10-packet1-iac-v1"
PACKET1_LIVE_SCHEMA_VERSION = "phase10-packet1-live-v1"
PACKET1_NEGATIVES_SCHEMA_VERSION = "phase10-packet1-negatives-v1"
PACKET2_MATRIX_SCHEMA_VERSION = "phase10-packet2-matrix-v1"
PACKET2_INVENTORY_SCHEMA_VERSION = "phase10-packet2-inventory-v1"
PACKET2_IAC_SCHEMA_VERSION = "phase10-packet2-iac-v1"
PACKET2_LIVE_SCHEMA_VERSION = "phase10-packet2-live-v1"
PACKET2_NEGATIVES_SCHEMA_VERSION = "phase10-packet2-negatives-v1"
PACKET2_MIGRATION_HASH_SCHEMA_VERSION = "phase10-packet2-migration-hash-v1"
PACKET3_MATRIX_SCHEMA_VERSION = "phase10-packet3-matrix-v1"
PACKET3_ORIGIN_SCHEMA_VERSION = "phase10-packet3-origin-v1"
PACKET3_EGRESS_SCHEMA_VERSION = "phase10-packet3-egress-v1"
PACKET3_TIMEOUTS_SCHEMA_VERSION = "phase10-packet3-timeouts-v1"
PACKET3_SCANS_SCHEMA_VERSION = "phase10-packet3-scans-v1"
PACKET3_NEGATIVES_SCHEMA_VERSION = "phase10-packet3-negatives-v1"
PACKET4_MATRIX_SCHEMA_VERSION = "phase10-packet4-matrix-v1"
PACKET4_JWKS_SCHEMA_VERSION = "phase10-packet4-jwks-v1"
PACKET4_ORIGIN_SCHEMA_VERSION = "phase10-packet4-origin-v1"
PACKET4_SSE_SCHEMA_VERSION = "phase10-packet4-sse-v1"
PACKET4_PARADEDB_SCHEMA_VERSION = "phase10-packet4-paradedb-v1"
PACKET4_VALKEY_SCHEMA_VERSION = "phase10-packet4-valkey-v1"
PACKET4_NEGATIVES_SCHEMA_VERSION = "phase10-packet4-negatives-v1"
PACKET5_MATRIX_SCHEMA_VERSION = "phase10-packet5-matrix-v1"
PACKET5_ANCHORS_SCHEMA_VERSION = "phase10-packet5-anchors-v1"
PACKET5_ALARMS_SCHEMA_VERSION = "phase10-packet5-alarms-v1"
PACKET5_INTEGRATIONS_SCHEMA_VERSION = "phase10-packet5-integrations-v1"
PACKET5_POOL_SCHEMA_VERSION = "phase10-packet5-pool-v1"
PACKET5_ENVELOPE_SCHEMA_VERSION = "phase10-packet5-envelope-v1"
PACKET5_NEGATIVES_SCHEMA_VERSION = "phase10-packet5-negatives-v1"
PACKET6_MATRIX_SCHEMA_VERSION = "phase10-packet6-matrix-v1"
PACKET6_INVENTORY_SCHEMA_VERSION = "phase10-packet6-inventory-v1"
PACKET6_RECONCILE_SCHEMA_VERSION = "phase10-packet6-reconciliation-v1"
PACKET6_REBUILD_SCHEMA_VERSION = "phase10-packet6-rebuild-v1"
PACKET6_INSTANCE_SCHEMA_VERSION = "phase10-packet6-instance-v1"
PACKET6_SKEW_SCHEMA_VERSION = "phase10-packet6-skew-v1"
PACKET6_NEGATIVES_SCHEMA_VERSION = "phase10-packet6-negatives-v1"
PACKET7_MATRIX_SCHEMA_VERSION = "phase10-packet7-matrix-v1"
PACKET7_SUITE_SCHEMA_VERSION = "phase10-packet7-suite-v1"
PACKET7_CUSTODY_SCHEMA_VERSION = "phase10-packet7-custody-v1"
PACKET7_ASSESSMENT_SCHEMA_VERSION = "phase10-packet7-assessment-v1"
PACKET7_TRACEABILITY_SCHEMA_VERSION = "phase10-packet7-traceability-v1"
PACKET7_NEGATIVES_SCHEMA_VERSION = "phase10-packet7-negatives-v1"
PACKET7_PROMOTION_SCHEMA_VERSION = "phase10-phase11-promotion-manifest-v1"

AWS_PROVIDER_CONSTRAINT = "~> 5.100"
INTENDED_AWS_REGION = "us-east-1"
INTENDED_SUPABASE_REGION = "us-east-1"
INTENDED_SUPABASE_PLAN = "Pro"
SES_MODE_SANDBOX = "sandbox"
ORIGIN_READ_TIMEOUT_SECONDS = 90
ORIGIN_KEEPALIVE_TIMEOUT_SECONDS = 90
IMDS_HOP_LIMIT = 1
IMDS_HTTP_TOKENS_REQUIRED = "required"
CLOUDFRONT_PREFIX_LIST_NAME = "com.amazonaws.global.cloudfront.origin-facing"
CACHING_DISABLED_POLICY_ID = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
ALL_VIEWER_EXCEPT_HOST_POLICY_ID = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
LIGHTRAG_DEPLOYMENT = "in-process"
ENVELOPE_HYBRID_VERSIONS = 8
ENVELOPE_CHUNKS = 16
ENVELOPE_GRAPH_VERSIONS = 15
SIGNED_FULL_HYBRID_VERSIONS = 10_000
SIGNED_FULL_CHUNKS = 1_000_000

PHASE09_IMAGE_IDS: dict[str, str] = {
    "api": "sha256:a65f1aa43fbf6fd353257a75fa9462e79a5bb187741d75e36a0429216e3633ec",
    "worker": "sha256:e6259d06f129ec14158e90acf1807dbaed0baa040bef9781fac60d46a97fe96e",
    "frontend": "sha256:e47efc373a151c7c79039009fd04f459f997127beafb00747cd91c4a9b96a5c1",
    "crawl-proxy": (
        "sha256:7d78834e21cc87d2ba133d4d131f1aa6d05b2de808d80296bf6658a8e04e62d3"
    ),
    "parser-sandbox": (
        "sha256:f7717ab4ec1e06d8113a19c080a05c1db6050b3b70e3bcfd73d61dd013ed6e0a"
    ),
}

PARADEDB_IMAGE = (
    "paradedb/paradedb:pg17@sha256:"
    "dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb"
)
PARADEDB_DIGEST = (
    "sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb"
)
VALKEY_IMAGE = (
    "valkey/valkey:8.1-alpine@sha256:"
    "a038175878d66b9d274fbf8be73c0305e93798b83917647f167e18cef3c71eec"
)
VALKEY_DIGEST = (
    "sha256:a038175878d66b9d274fbf8be73c0305e93798b83917647f167e18cef3c71eec"
)
CLAMAV_IMAGE = (
    "clamav/clamav:stable@sha256:"
    "78810772a92b4a9168115bc6b2e0ffd702640893b9577f8c3d0432762d2655c4"
)

SUPABASE_FEATURES: tuple[str, ...] = (
    "auth_asymmetric_jwt_jwks",
    "no_hs256_fallback",
    "storage_documents-quarantine",
    "storage_documents-originals",
    "storage_web-snapshots",
    "storage_table-artifacts",
    "rls",
    "pgvector",
    "daily_backups",
    "pitr",
    "supavisor_transaction_6543",
    "supavisor_session_5432",
)

VERCEL_PUBLIC_ENV_KEYS: tuple[str, ...] = (
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
)

VERCEL_FORBIDDEN_KEY_FRAGMENTS: tuple[str, ...] = (
    "SERVICE_ROLE",
    "DATABASE_URL",
    "DB_URL",
    "PARADEDB",
    "VALKEY",
    "ORIGIN_HEADER_VALUE",
    "ORIGIN_SECRET",
    "AWS_SECRET",
    "AWS_ACCESS_KEY",
    "JWT_SECRET",
    "PRIVATE_KEY",
    "BOOTSTRAP_PASSWORD",
)

STAGING_REQUIRED_SERVICES: tuple[str, ...] = (
    "api-blue",
    "api-green",
    "worker",
    "caddy",
    "paradedb",
    "valkey-limits",
    "valkey-cache",
    "crawl-proxy",
    "provider-egress-proxy",
    "clamav",
    "parser-sandbox",
)

STAGING_PRIVATE_NO_HOST_PORT_SERVICES: tuple[str, ...] = (
    "paradedb",
    "valkey-limits",
    "valkey-cache",
    "crawl-proxy",
    "provider-egress-proxy",
    "clamav",
    "parser-sandbox",
    "worker",
    "api-blue",
    "api-green",
)

STAGING_ORIGIN_SERVICES: tuple[str, ...] = ("caddy",)

LIGHTRAG_PUBLIC_PORTS: frozenset[int] = frozenset({9621, 9624})
PACKET8_HOST_PORTS: frozenset[int] = frozenset({54329, 13310, 18080})

REGION_FREEZE_NOTE = "Packet 1 intended freeze, not a prior client-signed region"

WRAPPER_RELATIVE = ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging.md"
PACKET1_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "01-provision-isolated-managed-staging.md"
)
PACKET2_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "02-implement-protected-migrations-and-secrets.md"
)
PACKET3_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "03-prove-origin-egress-and-timeouts.md"
)
PACKET4_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "04-exercise-rotations-streaming-and-degradation.md"
)
PACKET5_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "05-exercise-anchors-alerts-and-managed-load.md"
)
PACKET6_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "06-prove-restore-rebuild-skew-and-rollback.md"
)
PACKET7_RELATIVE = (
    ".cursor/plans/hybrid-graph-rag/10-phase-managed-staging/packets/"
    "07-run-release-suite-and-external-assessment.md"
)
ALERT_ROUTING_RUNBOOK = "docs/runbooks/alert-routing.md"
AUDIT_EXPORT_MODULE = "packages/core/src/smart_rag_core/security/audit_export.py"
KMS_S3_AUDIT_TF = "infra/ec2/kms_s3_audit.tf"
ALERTS_TF = "infra/ec2/alerts.tf"
STAGING_BUDGET_USD = 50
OBJECT_LOCK_RETENTION_YEARS = 7
OBJECT_LOCK_MODE = "GOVERNANCE"
KMS_DELETION_WINDOW_MIN_DAYS = 7
KMS_DELETION_WINDOW_MAX_DAYS = 30
STAGING_SYNTHETIC_EMAIL_SUFFIX = "@example.invalid"
PRODUCTION_EMAIL_FRAGMENTS: tuple[str, ...] = (
    "@gmail.com",
    "@googlemail.com",
    "@outlook.com",
    "@hotmail.com",
    "@yahoo.com",
    "@company.com",
    "@prod.",
    "production@",
)
PACKET5_REQUIRED_ALARM_RESOURCES: tuple[str, ...] = (
    "egress_denials",
    "cpu",
    "memory",
    "disk",
    "paradedb_fallback",
    "valkey",
    "audit_anchor_gap",
    "ses_bounce",
    "openai_spend_proxy",
)
PACKET5_RUNBOOK_ALARM_IDS: tuple[str, ...] = (
    "egress_denials",
    "cpu",
    "memory",
    "disk",
    "paradedb_fallback",
    "valkey",
    "audit_anchor_gap",
    "ses_bounce",
    "openai_spend",
    "aws_monthly_budget",
    "aws_data_transfer",
    "supabase_compute",
    "supabase_storage",
    "supabase_egress",
    "supabase_cpu",
    "supabase_io",
    "supabase_connections",
    "supabase_backup",
)
PACKET5_AUDIT_TEST_FILES: tuple[str, ...] = (
    (
        "tests/unit/test_fastapi_security.py"
        "::test_audit_export_detects_mutation_gap_fork_signing_and_passage"
    ),
)
PACKET5_PAUSE_TEST_FILES: tuple[str, ...] = ("tests/unit/test_maintenance_pause.py",)
PACKET5_BUDGET_TEST_FILES: tuple[str, ...] = (
    (
        "tests/contract/test_connection_budgets.py"
        "::test_worst_case_connection_budget_under_seventy_percent"
    ),
)
# Hosted Auth OAuth is dashboard-configured; the local CLI config suite was retired.
PACKET5_OAUTH_TEST_FILES: tuple[str, ...] = ()
PACKET5_CORS_TEST_FILES: tuple[str, ...] = (
    "tests/unit/test_fastapi_security.py::test_cors_reflects_exact_origin_not_wildcard",
    "tests/unit/test_fastapi_security.py::test_wildcard_cors_settings_fail_closed",
)
PHASE09_PACKET4_RESOURCES = "docs/deployment/phase-09/candidate-packet4-resources.json"
PHASE09_PACKET4_POOLS = "docs/deployment/phase-09/candidate-packet4-pools.json"
ORIGIN_ROTATION_RUNBOOK = "docs/runbooks/origin-secret-rotation.md"
ORIGIN_ROTATION_OVERLAP_MAX_MINUTES = 15
CDN_SSE_MIN_DURATION_SECONDS = 50
CDN_SSE_VIA_CLOUDFRONT = "cloudfront"
PHASE09_PACKET5_FAULT = "docs/deployment/phase-09/candidate-packet5-fault-matrix.json"
PHASE09_PACKET6_REBUILD = "docs/deployment/phase-09/candidate-packet6-rebuild.json"
PHASE09_PACKET6_RESTORE = "docs/deployment/phase-09/candidate-packet6-restore.json"
STORAGE_RECONCILE_RUNBOOK = "docs/runbooks/storage-db-reconciliation.md"
BM25_REBUILD_RUNBOOK = "docs/runbooks/bm25-rebuild.md"
INSTANCE_REBUILD_RUNBOOK = "docs/runbooks/instance-rebuild.md"
PROTECTED_MIGRATION_RUNBOOK = "docs/runbooks/PROTECTED_MIGRATION.md"
RTO_TARGET_HOURS = 4
RPO_TARGET_HOURS = 24
OLD_API_PRIOR_DIGEST = (
    "sha256:1d9f569b54c6012c4e9b1087979b409a9e2517ac9cce7c1f81d8917d9870f3d7"
)
REQUIRED_STORAGE_BUCKETS: tuple[str, ...] = (
    "documents-quarantine",
    "documents-originals",
    "web-snapshots",
    "table-artifacts",
)
RECONCILE_RUNBOOK_REQUIRED_TOKENS: tuple[str, ...] = (
    "missing object",
    "hash mismatch",
    "restore_incomplete",
    "hybrid",
    "graph",
    "orphan",
    "quarantine",
    "append-only audit",
    "alert",
    "rebuild only after reconciliation",
    "```mermaid",
)
BM25_REBUILD_RUNBOOK_REQUIRED_TOKENS: tuple[str, ...] = (
    "reconciled authorized current",
    "paradedb snapshot never canonical",
    "empty paradedb",
    "supabase",
    "parity",
    "```mermaid",
)
INSTANCE_REBUILD_RUNBOOK_REQUIRED_TOKENS: tuple[str, ...] = (
    "recreate from iac",
    "phase 9 freeze",
    "empty paradedb",
    "rebuild projection from supabase",
    "host data is not canonical",
    "rto",
    "4 hour",
    "rpo",
    "24 hour",
    "targets, not measurements",
    "drain",
    "active_api_upstream",
    "failed health check leaves the old slot active",
    "```mermaid",
)
REBUILD_BEFORE_RECONCILE_PHRASES: tuple[str, ...] = (
    "rebuild before reconcil",
    "rebuild then reconcil",
    "rebuild first, then reconcil",
)
PACKET6_RESTORE_INCOMPLETE_TEST_FILES: tuple[str, ...] = (
    (
        "tests/unit/test_phase10_packet6.py"
        "::test_restore_incomplete_excludes_hybrid_and_graph"
    ),
    "tests/unit/test_phase10_packet6.py::test_object_orphan_quarantines_and_alerts",
)
PACKET4_JWKS_TEST_FILES: tuple[str, ...] = ("tests/contract/test_jwks_auth.py",)
PACKET4_PARADEDB_TEST_FILES: tuple[str, ...] = (
    "tests/unit/test_hybrid_run.py::test_bm25_degradation_continues_dense_and_term",
    (
        "tests/unit/test_readiness.py"
        "::test_paradedb_down_is_visible_and_does_not_clear_query_ready"
    ),
    (
        "tests/unit/test_hybrid_coverage.py"
        "::test_bm25_degraded_keeps_signal_and_applies_threshold"
    ),
)
PACKET4_VALKEY_TEST_FILES: tuple[str, ...] = (
    "tests/contract/test_auth_rate_limits.py::test_missing_backends_fail_closed",
    (
        "tests/contract/test_auth_rate_limits.py"
        "::test_valkey_unset_cost_mutation_uses_postgres_not_fail_open"
    ),
    (
        "tests/contract/test_auth_rate_limits.py"
        "::test_dual_valkey_postgres_outage_fail_closed"
    ),
    (
        "tests/contract/test_auth_rate_limits.py"
        "::test_valkey_fast_path_enforces_ttl_counter"
    ),
    (
        "tests/contract/test_auth_rate_limits.py"
        "::test_low_risk_read_emergency_limiter_is_audited"
    ),
    (
        "tests/contract/test_auth_rate_limits.py"
        "::test_local_auth_throttling_not_claimed_as_hosted_proof"
    ),
)
PACKET4_SSE_SUPPORT_TEST_FILES: tuple[str, ...] = (
    "tests/unit/test_sse_protocol.py::test_heartbeat_interval_is_fifteen_seconds",
    "tests/contract/test_streaming_timeout_contract.py",
)
ORIGIN_RUNBOOK_REQUIRED_TOKENS: tuple[str, ...] = (
    "generate and store the pending value",
    "origin_header_value_current",
    "origin_header_value_previous",
    "custom_header",
    "wait for distribution",
    "direct-origin",
    "15-minute overlap",
    "abort or rollback keeps at least one valid value",
    "every rotation is audited",
)
PROVIDER_EGRESS_CADDY_FILE = "infra/ec2/provider-egress/Caddyfile"
PROVIDER_EGRESS_ALLOWLIST_FILE = "infra/ec2/provider-egress/allowlist.txt"
PACKET3_CRAWL_TEST_FILES: tuple[str, ...] = (
    "tests/unit/test_crawl_policy.py",
    "tests/contract/test_crawl_ssrf.py",
)
WAF_RULE_METRIC_NAMES: tuple[str, ...] = (
    "common",
    "bad-inputs",
    "ip-reputation",
    "rate",
)
WAF_ACL_METRIC_SUFFIX = "-waf"
WAF_RATE_LIMIT_COMMITTED = 2000
WAF_RATE_LIMIT_MAX = 10_000
CADDY_MAX_HEADER_BYTES = 16 * 1024
CADDY_MAX_HEADER_BYTES_LIMIT = 32 * 1024
CADDY_REQUEST_BODY_BYTES = 16 * 1024 * 1024
CADDY_REQUEST_BODY_BYTES_LIMIT = 16 * 1024 * 1024
CADDY_MAX_CONNS_PER_HOST = 32
CADDY_READ_HEADER_TIMEOUT_SECONDS = 15
EGRESS_DENIAL_LOG_GROUP = "/smart-rag/staging/egress-denials"
EGRESS_DENIAL_METRIC_NAME = "ProviderEgressDenials"
DIRECT_ORIGIN_DENIAL_METRIC_NAME = "DirectOriginDenials"
TELEMETRY_NAMESPACE = "SmartRag/Staging"
EGRESS_DENIAL_FILTER_PATTERN = "provider egress denied"
DIRECT_ORIGIN_DENIAL_FILTER_PATTERN = "direct origin denied"

GITHUB_REPOSITORY = "Nagdy8888/Demo_Project_3"
GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_AUDIENCE = "sts.amazonaws.com"
STAGING_OIDC_SUB = f"repo:{GITHUB_REPOSITORY}:environment:staging"
PRODUCTION_OIDC_SUB = f"repo:{GITHUB_REPOSITORY}:environment:production"
STAGING_MIGRATE_WORKFLOW = "staging-migrate.yml"
STAGING_DEPLOY_WORKFLOW = "staging-deploy.yml"
PRODUCTION_MIGRATE_WORKFLOW = "production-migrate.yml"
STAGING_MIGRATE_DOCUMENT = "SmartRagStagingMigrate"
STAGING_DEPLOY_DOCUMENT = "SmartRagStagingDeploy"
PRODUCTION_MIGRATE_DOCUMENT = "SmartRagProductionMigrate"
STAGING_SECRET_PREFIX = "smart-rag/staging/"  # noqa: S105 - name prefix, not a value
PRODUCTION_SECRET_PREFIX = "smart-rag/production/"  # noqa: S105 - name prefix, not a value
SECRET_ROTATION_MAX_DAYS = 90
CHECKOUT_ACTION_PIN = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
CONFIGURE_AWS_CREDENTIALS_SHA = "7474bc4690e29a8392af63c5b98e7449536d5c3a"
CONFIGURE_AWS_CREDENTIALS_RELEASE = "v4.3.1"
CONFIGURE_AWS_CREDENTIALS_PIN = (
    f"aws-actions/configure-aws-credentials@{CONFIGURE_AWS_CREDENTIALS_SHA}"
)
LONG_LIVED_WORKFLOW_FRAGMENTS: tuple[str, ...] = (
    "AWS_ACCESS_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "aws-access-key-id",
    "aws-secret-access-key",
    "secrets.AWS_",
)

USER_ACCEPTANCE_REQUEST = (
    "Request for user acceptance: Phase 10 remains status pending with "
    "packets 2-7 unchecked. The honest recommendation is no-go for Phase 11 "
    "until remaining managed staging proof and an independent external "
    "security assessment close. Please accept this pending/no-go state; do "
    "not promote production."
)
PHASE11_NO_GO_RECOMMENDATION = (
    "no-go for Phase 11 until live AWS/managed staging proof and an "
    "independent external security assessment close"
)
PHASE11_ROLLBACK = (
    "Keep the Phase 9 freeze identities. Do not advertise 10k/1M. Do not "
    "apply Terraform from this clone. Do not open holdout. Do not promote "
    "production."
)
ASSESSMENT_SCOPE_REQUIRED_TOKENS: tuple[str, ...] = (
    "auth/jwks",
    "rls/acl",
    "identity",
    "private bm25",
    "signed url",
    "quarantine",
    "ssrf",
    "egress",
    "injection",
    "origin bypass",
    "rate ownership",
    "storage",
    "synthetic",
    "no long-lived",
    "retest",
    "critical",
    "high",
    "medium",
    "dated adr",
    "owner",
    "not run",
    "trivy is image scan, not packet 7-c",
    "does not claim critical=0",
)
FAKE_ASSESSMENT_PASS_PHRASES: tuple[str, ...] = (
    "independent assessment passed",
    "independent pentest passed",
    "external assessment passed",
    "penetration test passed",
    "pentest passed",
    '"assessment_status": "passed"',
    '"pentest_status": "passed"',
    '"critical_open": 0',
    '"high_open": 0',
    "trivy is the independent assessment",
    "trivy as pentest",
    "p10-07-c passed",
)
FULL_SCALE_ENVELOPE_PHRASES: tuple[str, ...] = (
    '"qt-cap-001-p9": 10000',
    '"qt-cap-002-p9": 1000000',
)
PACKET7_LIVE_BLOCKED_KEYS: tuple[str, ...] = (
    "live_apply",
    "live_oidc_assume",
    "live_ssm_migrate",
    "live_secret_rotation",
    "live_cdn_requests",
    "live_port_scan",
    "live_denial_alert",
    "live_cdn_sse",
    "live_origin_rotation",
    "live_paradedb_kill",
    "live_valkey_kill",
    "live_kms_object_lock",
    "live_sns_ack",
    "live_ses_send",
    "live_managed_pool",
    "live_managed_resources",
    "live_managed_pitr",
    "live_reconciliation",
    "live_ec2_rebuild",
    "live_instance_rebuild",
    "live_drain",
)
PACKET7_LIVE_NOT_RUN_KEYS: tuple[str, ...] = ("live_managed_jwks",)
PACKET3_ORIGIN_ARTIFACT = "docs/deployment/phase-10/packet3-origin.json"
PACKET7_FAKE_HTTP_STATUSES: frozenset[int] = frozenset({200, 403})
