---
title: ADR index and backlog
owner: engineering-lead
status: draft
last-reviewed: 2026-09-09
audience: engineering
---

# ADR index

| ADR | Status | Phase | Path |
| --- | --- | --- | --- |
| Hybrid Pilot release cut | accepted | 1 | [ADR-hybrid-pilot-release-cut.md](./ADR-hybrid-pilot-release-cut.md) |
| Allow-listed long-document Hybrid profile | proposed | 4/6 overlay | [ADR-hybrid-long-document-profile.md](./ADR-hybrid-long-document-profile.md) |
| Detector findings and hash-bound reviews | accepted | 3 overlay | [ADR-detector-finding-reviews.md](./ADR-detector-finding-reviews.md) |
| Phase 4 engineering close | accepted | 4 | [ADR-phase4-engineering-close.md](./ADR-phase4-engineering-close.md) |
| ParadeDB edition/availability | accepted | 1 | [ADR-paradedb-edition-availability.md](./ADR-paradedb-edition-availability.md) |
| Private service TLS | accepted | 1 | [ADR-private-service-tls.md](./ADR-private-service-tls.md) |
| Expand/contract migrations | accepted | 1 | [ADR-expand-contract-migrations.md](./ADR-expand-contract-migrations.md) |
| API/SSE compatibility | accepted | 1 | [ADR-api-sse-compatibility.md](./ADR-api-sse-compatibility.md) |
| Vision captioning trigger | proposed | 1 | [ADR-vision-captioning.md](./ADR-vision-captioning.md) |
| Embedding model/dimension | accepted | 2 gate | [ADR-embedding-model-dimension.md](./ADR-embedding-model-dimension.md) |
| Privileged Auth administration boundary | accepted | 2 | [ADR-privileged-auth-administration-boundary.md](./ADR-privileged-auth-administration-boundary.md) |
| Upload capability / Storage privilege | accepted | 2 | [ADR-upload-capability-and-storage-privilege.md](./ADR-upload-capability-and-storage-privilege.md) |
| CVE pin patch (lxml/Pillow; pyarrow advisory) | accepted | 4 | [ADR-cve-pin-patch-2026-08.md](./ADR-cve-pin-patch-2026-08.md) |
| Alpine application bases (Trivy Criticals) | accepted | 9 | [ADR-alpine-application-bases-trivy.md](./ADR-alpine-application-bases-trivy.md) |
| Phase 9 local candidate envelope reduce | accepted | 9 | [ADR-phase9-local-envelope-reduce.md](./ADR-phase9-local-envelope-reduce.md) |
| Phase 10 hosted Supabase reuse (not local) | accepted | 10 | [ADR-phase10-hosted-supabase-reuse.md](./ADR-phase10-hosted-supabase-reuse.md) |
| Phase 10 live EC2 Free Tier instance type | accepted | 10 | [ADR-phase10-free-tier-ec2.md](./ADR-phase10-free-tier-ec2.md) |
| Demo local ingest / AWS ask later | accepted | 10 demo | [ADR-demo-local-ingest-aws-ask.md](./ADR-demo-local-ingest-aws-ask.md) |
| Stitch-first production UX | accepted | 8 UX | [ADR-stitch-first-ux.md](./ADR-stitch-first-ux.md) |
| Frontend functional overhaul | accepted | 8 remediation | [ADR-frontend-functional-overhaul.md](./ADR-frontend-functional-overhaul.md) |
| Verified-answer paced reveal and custom progress | accepted | 6/8 amendment | [ADR-verified-answer-paced-reveal.md](./ADR-verified-answer-paced-reveal.md) |
| Ink & Indigo visual refresh | accepted | 8 UX | [ADR-ink-indigo-visual-refresh.md](./ADR-ink-indigo-visual-refresh.md) |
| General-chat strict split | accepted | 6/8 amendment | [ADR-general-chat-strict-split.md](./ADR-general-chat-strict-split.md) |
| LightRAG identical-content collapse | superseded | 5 | [ADR-lightrag-identical-content-collapse.md](./ADR-lightrag-identical-content-collapse.md) |
| Identity-bound LightRAG source envelope | accepted | 5 | [ADR-graph-source-identity-envelope.md](./ADR-graph-source-identity-envelope.md) |
| Canonical-passage LightRAG sources | accepted | 5 | [ADR-canonical-passage-lightrag-sources.md](./ADR-canonical-passage-lightrag-sources.md) |
| Async LightRAG embeddings / batched isolated sources | accepted | 5 | [ADR-lightrag-async-embed-batched-sources.md](./ADR-lightrag-async-embed-batched-sources.md) |
| LightRAG runtime attach without DDL | accepted | 5 | [ADR-lightrag-runtime-attach-without-ddl.md](./ADR-lightrag-runtime-attach-without-ddl.md) |
| Graph eligibility / ACL isolation | documented (canonical) | 2/5 | [AUTHORIZATION_MODEL.md](../security/AUTHORIZATION_MODEL.md) · [WORKSPACE_LIFECYCLE.md](../graph/WORKSPACE_LIFECYCLE.md) — restricted never `graph_eligible`; resolver rechecks ACL/current/deletion. No separate ADR unless the CHECK or ACL contract changes. |
| PGTableGraphStorage | accepted with identity envelope | 5 | [LIGHTRAG_CONTRACT.md](../graph/LIGHTRAG_CONTRACT.md) · [ADR-graph-source-identity-envelope.md](./ADR-graph-source-identity-envelope.md) |
| Canonical vs inference grounding | documented (canonical) | 5 | [RETRIEVAL.md](../graph/RETRIEVAL.md) · [GRAPH_MAPPING_CONTRACT.md](../graph/GRAPH_MAPPING_CONTRACT.md) · [MAPPING.md](../graph/MAPPING.md) — LightRAG prose and BM25 snippets are leads/search forms, not citations; resolver maps to canonical chunk UUIDs. Implemented; do not open a new ADR unless the resolver contract changes. |
| Structured-table execution | documented (canonical) | 4 | [STRUCTURED_TABLE.md](../retrieval/STRUCTURED_TABLE.md) — sandboxed DuckDB, no HTTP table route, no catalog discovery. Packet 9 table Parquet eval is `not_run`. |
| Reserve-once durable budgets | planned | 6 | TBD |
| Database workload isolation | documented (canonical) | 2/10 | [06-database-workload-isolation.md](../architecture/06-database-workload-isolation.md) — role timeouts/`work_mem`/`application_name` applied; replica/dedicated LightRAG Postgres remain later-phase options. |
| Egress enforcement | planned | 3/10 | TBD |
| Multi-host availability | planned | trigger | see availability doc |

Availability/RTO triggers: [../architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md](../architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md)

[docs index](../README.md)
