---
title: Documentation index
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
audience: engineering, reviewers, client-approver
---

# Documentation index

Canonical map for Smart RAG docs. Status values: `planned` | `draft` | `proposed` | `accepted` | `verified`.

| Document | Owner | Status | Last reviewed | Audience |
| --- | --- | --- | --- | --- |
| [QUALITY_TARGETS.md](./QUALITY_TARGETS.md) | product-owner | accepted | 2026-08-12 | client, engineering |
| [architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md](./architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md) | engineering-lead | accepted | 2026-08-12 | eng, ops |
| [architecture/01-system-context.md](./architecture/01-system-context.md) | engineering-lead | draft | 2026-08-12 | eng |
| [architecture/02-containers.md](./architecture/02-containers.md) | engineering-lead | draft | 2026-08-14 | eng |
| [architecture/03-components.md](./architecture/03-components.md) | engineering-lead | draft | 2026-08-12 | eng |
| [architecture/04-deployment.md](./architecture/04-deployment.md) | engineering-lead | draft | 2026-08-12 | eng, ops |
| [architecture/05-database-connections.md](./architecture/05-database-connections.md) | engineering-lead | proven | 2026-08-13 | eng, ops |
| [architecture/06-database-workload-isolation.md](./architecture/06-database-workload-isolation.md) | engineering-lead | proven | 2026-08-13 | eng, ops |
| [architecture/08-data-dictionary.md](./architecture/08-data-dictionary.md) | engineering-lead | draft | 2026-08-14 | eng |
| [development/phase-01-foundation-evidence.md](./development/phase-01-foundation-evidence.md) | engineering-lead | accepted | 2026-08-13 | eng, reviewers |
| [development/phase-02-identity-data-evidence.md](./development/phase-02-identity-data-evidence.md) | engineering-lead | accepted | 2026-08-13 | eng, reviewers |
| [development/phase-03-ingestion-evidence.md](./development/phase-03-ingestion-evidence.md) | engineering-lead | accepted | 2026-08-14 | eng, reviewers |
| [development/phase-04-hybrid-rag-evidence.md](./development/phase-04-hybrid-rag-evidence.md) | engineering-lead | pending | 2026-08-14 | eng, reviewers |
| [architecture/07-bm25-projection.md](./architecture/07-bm25-projection.md) | engineering-lead | proven | 2026-08-13 | eng |
| [security/PROTECTED_MIGRATION_CREDENTIALS.md](./security/PROTECTED_MIGRATION_CREDENTIALS.md) | engineering-lead | proven-local | 2026-08-13 | eng, security, ops |
| [security/AUDIT_CHAIN.md](./security/AUDIT_CHAIN.md) | engineering-lead | proven | 2026-08-13 | eng, security |
| [evaluation/EMBEDDING_QUALIFICATION_REPORT.md](./evaluation/EMBEDDING_QUALIFICATION_REPORT.md) | engineering-lead | draft | 2026-08-12 | eng, reviewers |
| [evaluation/DATASET_SPEC.md](./evaluation/DATASET_SPEC.md) | engineering-lead | draft | 2026-08-14 | eng, SME, reviewers |
| [evaluation/QUERY_PROFILE_LABELING.md](./evaluation/QUERY_PROFILE_LABELING.md) | engineering-lead | draft | 2026-08-14 | eng, SME |
| [development/TOOL_VERSIONS.md](./development/TOOL_VERSIONS.md) | engineering-lead | draft | 2026-08-14 | eng |
| [development/CONFIGURATION.md](./development/CONFIGURATION.md) | engineering-lead | draft | 2026-08-14 | eng |
| [development/RISK_REGISTER.md](./development/RISK_REGISTER.md) | engineering-lead | draft | 2026-08-12 | eng, client |
| [development/LOCAL_SETUP.md](./development/LOCAL_SETUP.md) | engineering-lead | draft | 2026-08-12 | eng |
| [development/WORKSPACE_BOUNDARIES.md](./development/WORKSPACE_BOUNDARIES.md) | engineering-lead | draft | 2026-08-12 | eng |
| [development/QUALITY_COMMANDS.md](./development/QUALITY_COMMANDS.md) | engineering-lead | draft | 2026-08-12 | eng |
| [development/CI_TIERS.md](./development/CI_TIERS.md) | engineering-lead | draft | 2026-08-12 | eng |
| [development/DEPENDENCY_UPDATES.md](./development/DEPENDENCY_UPDATES.md) | engineering-lead | draft | 2026-08-12 | eng |
| [adr/README.md](./adr/README.md) | engineering-lead | draft | 2026-08-12 | eng |
| [adr/ADR-hybrid-pilot-release-cut.md](./adr/ADR-hybrid-pilot-release-cut.md) | product-owner | accepted | 2026-08-12 | client, eng |
| [adr/ADR-paradedb-edition-availability.md](./adr/ADR-paradedb-edition-availability.md) | engineering-lead | accepted | 2026-08-12 | eng |
| [adr/ADR-private-service-tls.md](./adr/ADR-private-service-tls.md) | engineering-lead | accepted | 2026-08-12 | eng, security |
| [adr/ADR-expand-contract-migrations.md](./adr/ADR-expand-contract-migrations.md) | engineering-lead | accepted | 2026-08-12 | eng |
| [adr/ADR-api-sse-compatibility.md](./adr/ADR-api-sse-compatibility.md) | engineering-lead | accepted | 2026-08-12 | eng |
| [adr/ADR-vision-captioning.md](./adr/ADR-vision-captioning.md) | product-owner | proposed | 2026-08-12 | client, eng |
| [adr/ADR-embedding-model-dimension.md](./adr/ADR-embedding-model-dimension.md) | engineering-lead | accepted | 2026-08-12 | eng |
| [retrieval/ARABIC_NORMALIZATION.md](./retrieval/ARABIC_NORMALIZATION.md) | engineering-lead | draft | 2026-08-12 | eng |
| [retrieval/HYBRID_RETRIEVAL_CONTRACT.md](./retrieval/HYBRID_RETRIEVAL_CONTRACT.md) | engineering-lead | draft | 2026-08-14 | eng, reviewers |
| [retrieval/HYBRID_TUNING.md](./retrieval/HYBRID_TUNING.md) | engineering-lead | planned | 2026-08-14 | eng |
| [ingestion/CHUNKING_CONTRACT.md](./ingestion/CHUNKING_CONTRACT.md) | engineering-lead | accepted | 2026-08-13 | eng |
| [ingestion/INGESTION_LIMITS.md](./ingestion/INGESTION_LIMITS.md) | engineering-lead | draft | 2026-08-14 | eng, ops |
| [ingestion/JOB_STATE_MACHINE.md](./ingestion/JOB_STATE_MACHINE.md) | engineering-lead | draft | 2026-08-14 | eng |
| [runbooks/CLAMAV_SCAN_AND_PROMOTION.md](./runbooks/CLAMAV_SCAN_AND_PROMOTION.md) | engineering-lead | draft | 2026-08-13 | eng, ops |
| [ingestion/CRAWL_POLICY.md](./ingestion/CRAWL_POLICY.md) | engineering-lead | draft | 2026-08-13 | eng, security |
| [runbooks/CRAWL_EGRESS_AND_PROXY.md](./runbooks/CRAWL_EGRESS_AND_PROXY.md) | engineering-lead | draft | 2026-08-13 | eng, ops |
| [evaluation/QUERY_PROFILE_EVAL.md](./evaluation/QUERY_PROFILE_EVAL.md) | engineering-lead | draft | 2026-08-14 | eng |
| [security/LOCAL_ADMIN_ALERT_CONTRACT.md](./security/LOCAL_ADMIN_ALERT_CONTRACT.md) | engineering-lead | draft | 2026-08-14 | eng, ops |
| [security/AUTHORIZATION_MODEL.md](./security/AUTHORIZATION_MODEL.md) | engineering-lead | draft | 2026-08-12 | eng, security |
| [security/IDENTITY_PROPAGATION.md](./security/IDENTITY_PROPAGATION.md) | engineering-lead | draft | 2026-08-14 | eng, security |
| [security/AUTH_RATE_LIMIT_OWNERSHIP.md](./security/AUTH_RATE_LIMIT_OWNERSHIP.md) | engineering-lead | draft | 2026-08-13 | eng, security |
| [adr/ADR-privileged-auth-administration-boundary.md](./adr/ADR-privileged-auth-administration-boundary.md) | engineering-lead | accepted | 2026-08-13 | eng, security |
| [adr/ADR-upload-capability-and-storage-privilege.md](./adr/ADR-upload-capability-and-storage-privilege.md) | engineering-lead | accepted | 2026-08-13 | eng, security |
| [adr/ADR-parser-isolation.md](./adr/ADR-parser-isolation.md) | engineering-lead | accepted | 2026-08-13 | eng, security, ops |
| [runbooks/SUPABASE_JWKS_ROLLOVER.md](./runbooks/SUPABASE_JWKS_ROLLOVER.md) | engineering-lead | draft | 2026-08-13 | ops, security |
| [security/OPENAI_DATA_GOVERNANCE.md](./security/OPENAI_DATA_GOVERNANCE.md) | product-owner | accepted | 2026-08-13 | client, security |
| [security/SUBPROCESSOR_GOVERNANCE.md](./security/SUBPROCESSOR_GOVERNANCE.md) | product-owner | accepted | 2026-08-13 | client, security |
| [api/openapi.foundation.json](./api/openapi.foundation.json) | engineering-lead | draft | 2026-08-14 | eng |
| [api/GLOSSARY_IMPORT.md](./api/GLOSSARY_IMPORT.md) | engineering-lead | draft | 2026-08-14 | eng, security |
| [runbooks/README.md](./runbooks/README.md) | engineering-lead | draft | 2026-08-12 | ops |
| [reviews/2026-08-12-hybrid-graph-rag-plan-review.md](./reviews/2026-08-12-hybrid-graph-rag-plan-review.md) | engineering-lead | verified | 2026-08-12 | eng |

Back to [root README](../README.md).
