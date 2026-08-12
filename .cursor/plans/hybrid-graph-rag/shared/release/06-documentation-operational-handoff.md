---
name: hybrid-graph-rag-documentation-operational-handoff
status: active
applies_to: phase-11
source_phase: ../../11-phase-production.md
---

# Documentation and operational handoff

## Documentation quality contract

Create C4-aligned documentation and prevent documentation drift:

- Treat documentation as a required deliverable in every implementation change.
- Every authored Python module, class, function, async function, and method has a Google-style docstring; generated or vendor code is the only explicit exclusion.
- Public or exported TypeScript functions, hooks, components, server actions, and non-obvious types use TSDoc or JSDoc.
- Function documentation covers purpose, parameters, return or yield, exceptions, side effects, authorization, idempotency, retries and timeouts, units and provenance, and examples where relevant.
- LangGraph nodes additionally document state input and output, durable writes, external or model calls, budgets and deadlines, and failure or fallback routing.

The root `README.md` remains a concise onboarding and index page. `docs/README.md` is the complete maintained documentation map with owner, status, last-reviewed date, reciprocal links, and links to every final API, version, configuration, provider-governance, BM25 architecture/rebuild, ADR, deployment, security, evaluation, retention/deletion, and runbook document.

Detailed documentation is split by audience and concern under `docs/architecture`, `development`, `api`, `ingestion`, `retrieval`, `graph`, `agent`, `frontend`, `security`, `evaluation`, `deployment`, `runbooks`, and `adr`. Use one primary topic per file and split documents that mix concerns or grow beyond roughly 300 lines.

## Diagram contract

- Architecture, component, trust-boundary, data-flow, authentication, ingestion, retrieval, agent-routing, state-machine, deployment, database, and operational-workflow documents contain Mermaid source diagrams.
- Use `flowchart`, `sequenceDiagram`, `stateDiagram-v2`, or `erDiagram` as appropriate.
- Diagrams supplement rather than replace detailed prose, contracts, limits, or failure behavior.
- Keep diagrams small enough to review.
- Split dense views by concern.
- Use stable descriptive IDs and quoted labels.
- Avoid hard-coded styling and colors.
- Update diagrams in the same change as the represented flow or schema.

## Required content and canonical links

Every document includes applicable prerequisites, contracts, data flow, limits, security implications, failure or degraded behavior, examples, verification commands, troubleshooting, and links to canonical code, schema, or API sources. Planned or externally unverified content is labeled explicitly.

Document every public API, environment variable, migration, queue, job, state machine, provider integration, prompt or model policy, configuration default, deployment change, and user-visible workflow in the same change that introduces or changes it. Prefer links to one canonical explanation over copied sections.

Required canonical documents include:

- `docs/architecture/01-system-context.md`: actors, external systems, and trust boundaries.
- `docs/architecture/02-containers.md`: Vercel, EC2 and ParadeDB services, Supabase, OpenAI, LangSmith, and SES.
- `docs/architecture/03-components.md`: backend, worker, graphs, BM25 projection and retrieval, fusion, and registry components.
- `docs/architecture/04-deployment.md`: local, staging, and production nodes, ports, and state.
- `docs/ingestion/CHUNKING_CONTRACT.md`: typed elements, format cleaning, size, overlap, atomic-unit rules, parent reconstruction, deduplication, provenance, versions, and acceptance fixtures.
- `docs/retrieval/ARABIC_NORMALIZATION.md`: raw versus search text, exact normalization mappings and version, canonical Supabase field plus ParadeDB projection/query parity, limitations, and BM25 ablations.
- `docs/retrieval/HYBRID_TUNING.md`: immutable configuration profiles, candidate, rerank, MMR, RRF, and coverage search space, per-query-class curves, selected values, and rollback.
- `docs/evaluation/QUERY_PROFILE_EVAL.md`: field labels, metrics, confidences, failure attribution, few-shot promotion, split isolation, and signed thresholds.

OpenAPI and Pydantic field descriptions are the canonical API schema. Frontend types are generated from it.

Phase 1 enables Ruff pydocstyle plus an AST-based test for all required Python docstrings, Markdown lint and link validation, Mermaid syntax and render validation, and CI checks that public API, configuration, or environment changes include corresponding documentation.

## Required governance and ADR set

Maintain ADRs for:

- graph eligibility and ACL isolation;
- custom Hybrid plus ParadeDB BM25 plus LightRAG responsibilities;
- ParadeDB Community/Enterprise licensing and same-host availability/fallback;
- `PGTableGraphStorage`;
- canonical and inference grounding;
- structured-table execution;
- reserve-once durable budgets;
- embedding model, dimension, index, and memory;
- database workload isolation and replica consistency;
- parser shared-kernel acceptance and upgrade triggers;
- egress enforcement;
- ParadeDB and Valkey TLS decisions;
- availability, RTO/RPO, and growth triggers;
- expand/contract migrations;
- additive API and SSE compatibility;
- optional-tool disclosure;
- fetch streaming;
- private-service-only BM25 and LightRAG access; and
- vision-captioning promotion.

`docs/security/OPENAI_DATA_GOVERNANCE.md` and `docs/security/SUBPROCESSOR_GOVERNANCE.md` are the canonical signed governance packet. Do not duplicate signed provider decisions as separate ADRs.

## Required runbooks

Maintain runbooks for:

- protected migrations and credential rotation;
- Supabase signing-key and JWKS rollover;
- ClamAV engine and signature update, staleness, and re-scan;
- Valkey outage and recovery;
- ParadeDB projection replay, clean rebuild, version switch, and fallback;
- origin-secret dual rotation;
- alert routing;
- LightRAG workspace upgrades, replacement, reconciliation, deletion, and bulk-onboarding ETA;
- embedding-model parallel rebuild;
- re-embedding after metadata edits;
- dead-letter replay;
- conversation-deletion verification;
- user offboarding, export, and deletion;
- retention and legal hold;
- audit-chain and anchor verification;
- alias and feedback curation;
- key and session rotation;
- instance rebuild;
- staging promotion;
- Supabase database plus Storage backup, restore, and reconciliation;
- incident response; and
- rollback.

Every operational procedure includes prerequisites, authorization, bounded impact, rollback, verification, escalation, and evidence location.

## Default retention policy

Retention is configurable only through an owner-approved policy:

- Disable departed users and revoke sessions immediately.
- Remove team access immediately.
- Export only on approved request.
- Purge or pseudonymize profile and private-conversation data after 30 days unless legal hold applies.
- Retain undeleted conversations and messages for 90 days after last activity.
- Retain undeleted run event payloads and checkpoints for 30 days.
- Retain user feedback for 12 months.
- Retain aggregated usage for 24 months.
- Retain LangSmith traces for 30 days with payload redaction.
- Retain audit events for seven years in write-once export.
- User-requested conversation deletion follows the Phase 6 privacy contract immediately and does not wait for retention windows.
- Document deletion excludes retrieval immediately through Supabase authority.
- BM25 projection and other derived indexes are targeted for purge within 24 hours.
- Encrypted provider backups expire under the documented backup schedule.

The owner publishes the production retention and legal-hold policy before user access.

## Engine and operational handoff

Reserve one to two engineer-days per quarter for ParadeDB/`pg_search` and LightRAG dependency and schema qualification, BM25 projection/rebuild and graph deletion drills, and source-map health review.

The owner receives:

- both engine pins and exit criteria;
- the ParadeDB image digest, `pg_search` version, BM25 schema/index/normalization versions, and measured rebuild and projection-lag limits;
- the LightRAG graph workspace version, graph survival, current-only temporal limitation, per-language mapping health, onboarding ETA, and cost limits;
- known limitations;
- a tested BM25-outage dense-plus-term path; and
- a tested graph disable-to-Hybrid-only procedure.

The handoff dashboard and runbooks keep the global availability and database/BM25-isolation triggers visible with a named owner. Crossing a trigger creates a dated architecture-review action instead of merely raising an alarm. The review records whether to resize, move ParadeDB to dedicated Enterprise, BYOC, or other approved BM25 infrastructure, isolate Supabase reads or LightRAG, or start the multi-host design.

## Required evidence and failure routes

Evidence belongs in `docs/development/phase-11-production-evidence.md` and links every required document and runbook with owner, status, last-reviewed date, verification result, and unresolved risk.

- A missing, stale, contradictory, unowned, or broken-linked required document blocks handoff.
- Missing Mermaid source or render proof for a required diagram blocks the documentation gate.
- Missing owners, acknowledgement and escalation routes, retention approval, quarterly capacity, or tested BM25/graph disable paths block user access.
- A planned or externally unverified statement must be labeled and routed to an owner; it cannot be represented as production proof.
- Documentation does not replace executable evidence. Every runbook named as tested must link to its actual staging or production-safe execution record.
