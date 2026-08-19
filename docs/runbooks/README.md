---
title: Runbook backlog
owner: engineering-lead
status: draft
last-reviewed: 2026-08-18
audience: operations
---

# Runbook backlog

Procedures are **not** written for systems that do not exist yet. Each row is a backlog item.

| Runbook | Owner phase | Prerequisites | Status | Verification | Escalation |
| --- | --- | --- | --- | --- | --- |
| Protected migrations / credential rotation | 2/10 | migrations exist | draft | migrate drill / Packet 2 policy | eng-lead |
| JWKS / signing-key rollover | 2/10 | Auth asymmetric keys | draft | application JWKS tests; managed staging dashboard Not Run | security |
| ClamAV engine/signature update | 3 | scanner image | planned | signature freshness test | eng-lead |
| Valkey outage/recovery | 6/9 | Valkey services | planned | degraded-path test | eng-lead |
| ParadeDB projection rebuild/fallback | 4/9/10 | BM25 outbox | draft | Packet 6 bm25-rebuild; live EC2 Blocked | eng-lead |
| Local/in-app admin alerts | 6/8 | alert contract | planned | ack path | eng-lead |
| Origin-secret dual rotation | 10 | CloudFront | draft | Packet 4 policy; live rotation Blocked | eng-lead |
| Staging alert routing | 10 | CloudWatch/SNS | draft | Packet 5 policy; live SNS/ack Blocked | eng-lead |
| Storage/DB restore reconciliation | 10 | backups | draft | Packet 6 policy; live PITR Blocked | eng-lead |
| Derived BM25 projection rebuild | 10 | reconciled Supabase | draft | Packet 6 policy; live EC2 rebuild Blocked | eng-lead |
| Instance rebuild / Caddy drain | 10 | IaC + freeze images | draft | Packet 6 policy; timed rebuild Blocked | eng-lead |
| LightRAG private-schema bootstrap | 5 | Packet 1 pin + Packet 2 migrations | draft | fingerprint + role matrix | eng-lead |
| LightRAG workspace cleanup/rebuild | 5 | Packet 7 pointer/delete | draft | switch + tombstone tests | eng-lead |
| LightRAG snapshot restore / pointer rollback | 5 | Packet 7 isolated copy | draft | same-schema refuse + restore script | eng-lead |
| Embedding parallel rebuild | 2/4 | embedding ADR | planned | dual-index cutover | eng-lead |
| Dead-letter replay | 3 | queues | planned | idempotent replay | eng-lead |
| Conversation deletion verification | 6 | chat schema | planned | delete audit | privacy |
| User offboarding/export/deletion | 2/11 | identity | planned | retention | privacy |
| Backup/restore DB+Storage | 9/10 | backups | draft | Packet 6 reconcile runbook; live PITR Blocked | eng-lead |
| Incident response / rollback | 9–11 | staging | planned | tabletop | eng-lead |
| Staging secrets collection (Free/t3.micro continue) | 10 | gitignored `.env.staging` | draft | names-only listing; no compose up on micro | eng-lead |

[lightrag-schema-bootstrap.md](./lightrag-schema-bootstrap.md) ·
[GRAPH_SNAPSHOT_RESTORE_ROLLBACK.md](./GRAPH_SNAPSHOT_RESTORE_ROLLBACK.md) ·
[PROTECTED_MIGRATION.md](./PROTECTED_MIGRATION.md) ·
[SUPABASE_JWKS_ROLLOVER.md](./SUPABASE_JWKS_ROLLOVER.md) ·
[origin-secret-rotation.md](./origin-secret-rotation.md) ·
[alert-routing.md](./alert-routing.md) ·
[storage-db-reconciliation.md](./storage-db-reconciliation.md) ·
[bm25-rebuild.md](./bm25-rebuild.md) ·
[instance-rebuild.md](./instance-rebuild.md) ·
[phase10-staging-secrets.md](./phase10-staging-secrets.md) ·
[docs index](../README.md)
