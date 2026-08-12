---
title: Runbook backlog
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: operations
---

# Runbook backlog

Procedures are **not** written for systems that do not exist yet. Each row is a backlog item.

| Runbook | Owner phase | Prerequisites | Status | Verification | Escalation |
| --- | --- | --- | --- | --- | --- |
| Protected migrations / credential rotation | 2/10 | migrations exist | planned | migrate drill | eng-lead |
| JWKS / signing-key rollover | 2/10 | Auth asymmetric keys | planned | rollover drill | security |
| ClamAV engine/signature update | 3 | scanner image | planned | signature freshness test | eng-lead |
| Valkey outage/recovery | 6/9 | Valkey services | planned | degraded-path test | eng-lead |
| ParadeDB projection rebuild/fallback | 4/9 | BM25 outbox | planned | rebuild timing | eng-lead |
| Local/in-app admin alerts | 6/8 | alert contract | planned | ack path | eng-lead |
| Origin-secret dual rotation | 10 | CloudFront | planned | skew test | eng-lead |
| LightRAG workspace cleanup/rebuild | 5/9 | graph ready | planned | quarantine drill | eng-lead |
| Embedding parallel rebuild | 2/4 | embedding ADR | planned | dual-index cutover | eng-lead |
| Dead-letter replay | 3 | queues | planned | idempotent replay | eng-lead |
| Conversation deletion verification | 6 | chat schema | planned | delete audit | privacy |
| User offboarding/export/deletion | 2/11 | identity | planned | retention | privacy |
| Backup/restore DB+Storage | 9/10 | backups | planned | restore drill | eng-lead |
| Incident response / rollback | 9–11 | staging | planned | tabletop | eng-lead |

[docs index](../README.md)
