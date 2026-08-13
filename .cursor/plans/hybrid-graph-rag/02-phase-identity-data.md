---
name: hybrid-graph-rag-phase-02-identity-data
phase: 2
status: complete
depends_on: [1]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 2: Identity and data

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Treat this file as the only implementation scope for Phase 2. Later-phase files may clarify an interface but do not authorize later-phase implementation.
3. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions before editing. This plan describes targets, not proof that a file or API already exists.
4. Load the relevant workspace skill files listed below before implementation.
5. Before every work packet, state the requirement and concrete acceptance checks. Implement the smallest complete packet.
6. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
7. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
8. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Phase 1 must define these commands; later phases must inspect rather than invent them.
9. Update documentation in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
10. Record proof in the exit record. If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR/plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md)

## Relevant workspace skills

- [`.cursor/skills/implement-supabase-security/SKILL.md`](../../../.cursor/skills/implement-supabase-security/SKILL.md)

## Scope lock

**In scope:** Supabase schema, roles, RLS, Auth, MFA, Storage, audit foundations, connection budgets, and embedding qualification.

**Out of scope:** Rich parsing, bulk embeddings, retrieval tuning, LightRAG indexing, query orchestration, and frontend feature work.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] Prove selected Supabase/pgvector and private ParadeDB/`pg_search` BM25 capabilities, then freeze the disjoint embedding/lexical qualification slice before bulk ingestion.
2. [x] Implement expand/contract-safe migrations for canonical data, BM25 projection outbox/version state, jobs, graph mappings, conversations, tools, budgets, audit/read-access events, upload quotas/notifications, and private schemas.
3. [x] Create least-privilege Supabase, Storage, BM25 reader/writer/bootstrap roles, explicit v1 document ACL semantics, server-derived identity propagation, RLS/RPC boundaries, and forged/missing-context tests.
4. [x] Implement asymmetric JWT/JWKS verification and rollover, PKCE Auth, direct-Supabase-Auth rate-limit ownership, invitations, MFA/recovery, session revocation, and upload-capability controls.
5. [x] Create private Storage buckets, enforceable upload/quarantine quotas and TTL cleanup, scan metadata foundations, graph eligibility, and retention structures.
6. [x] Document and prove connection budgets, pooling compatibility, workload-isolation triggers, protected migration credentials, generated types, read/audit-chain integrity, and local admin notifications.

## Cheap-model execution protocol

The six checkboxes above are separate work packets. One model run may execute only one packet, in order. Before editing, the model must quote the active packet, restate its acceptance and negative tests, inspect every target path plus current migration state, and confirm Phase 1 has a user-accepted exit record. This plan expansion does not satisfy that prerequisite.

Use [`docs/development/phase-02-identity-data-evidence.md`](../../../docs/development/phase-02-identity-data-evidence.md) as the canonical packet evidence and exit record. Packet 1 creates it and links it from `docs/README.md`. Every packet appends the requirement, inspected schema/config/version state, primary-documentation links, migrations and generated artifacts changed, exact commands and exit codes, positive and negative test results, measured limits, secrets/roles reviewed, unverified managed checks, rollback, and next-packet handoff.

For Supabase, PostgreSQL, pgvector, ParadeDB/`pg_search`, LightRAG storage, LangGraph persistence, OpenAI embeddings, and every CLI:

1. inspect the repository pin, lockfile, local service version, selected managed target, and command `--help`;
2. fetch current primary documentation for the pinned version;
3. record the exact package/image/extension/Postgres-major combination and immutable digest where applicable;
4. test the actual feature in the environment that will use it;
5. stop if SQL names, configuration keys, CLI flags, provider limits, licensing, or edition capabilities are not verified; and
6. add a real contract test before depending on the behavior.

Never infer an installed extension from an image tag, use `latest`, copy a stale ParadeDB `bm25`/`paradedb`/`pdb` example across versions, invent a Supabase `config.toml` key, rely on a CLI default target, hand-author a migration timestamp, or call generated types authorization evidence. Every Supabase CLI command must explicitly target local, linked, or an approved database URL according to the verified command help.

Use imperative forward migrations as the canonical schema history unless the Phase 1 migration ADR explicitly selected a different single workflow. Do not mix untracked Studio changes, declarative schema diffs, and imperative migrations. Treat generated diffs as drafts: review RLS, grants, roles, function properties, view security, DML, triggers, and destructive changes manually before accepting them.

Security proof uses real least-privilege credentials, never a superuser or `service_role` bypass. Runtime roles must not own tables, have `BYPASSRLS`, create extensions, or receive migration/bootstrap credentials. Exposed tables have RLS plus explicit grants; unexposed private schemas also have explicit revokes. `security definer` functions live in a private schema, use an empty/fixed `search_path`, schema-qualify every object, revoke default `PUBLIC EXECUTE`, and receive only named role grants. Views use `security_invoker` when the selected PostgreSQL version supports it.

The v1 authorization snapshot is a company-wide monotonic `authorization_version` stored in authoritative Supabase state. Role, disabled/session-sensitive membership, upload capability, MFA-required privilege, document ACL, and document visibility changes increment it in the same transaction. FastAPI resolves the current value and passes it to approved private RPCs; every RPC compares it to the current value and returns no evidence for stale context. This deliberately favors broad safe invalidation over a more complex per-resource snapshot at the initial 25-user envelope. A different design requires an ADR and authorization-race tests.

Provider caveats are explicit gates, not implementation details to guess:

- Current Supabase local development does not enforce hosted Auth rate limits. Local tests prove ownership/configuration and must not claim throttling; provider enforcement requires a hosted environment that actually supports it.
- Supabase signed-upload token lifetime may be provider-fixed and longer than the desired 15-minute application admission lease. Packet 5 must qualify the selected upload mechanism and obtain security approval; it must not label a longer provider token as a 15-minute capability.
- Auth Admin operations and broad Storage secret credentials conflict with the ban on general runtime `service_role`. Packets 4–5 require approved isolated privileged-boundary ADRs before implementing any operation that needs such a secret. Never invent a scoped Supabase key that the platform does not provide.
- Recovery codes, local asymmetric signing-key lifecycle parity, selected-tier limits, custom-role pooler compatibility, and ParadeDB edition features remain unverified until current docs and real contract tests prove them.

At most two bounded repair attempts may be made for the same integration failure. A skipped test, empty migration, broad secret, permissive policy, fake email, mock JWKS rollover, or TCP-only health check cannot satisfy a packet.

## Work packet implementation contracts

### Packet 1 — capability and embedding qualification

#### Packet 1 preconditions

- Phase 1 is complete, its exit record is accepted, signed quality targets exist, and its locked local stack starts.
- Inspect pinned Supabase CLI, local PostgreSQL/pgvector, ParadeDB image digest/edition/license, LightRAG/OpenAI packages, and repository-defined verification commands.
- A bounded real OpenAI qualification credential and the selected managed-target compatibility environment are available. If either is unavailable, record the blocker and stop rather than substituting frozen vectors for model selection.

#### Packet 1 allowed outputs

- A migration created through the verified CLI for pgvector compatibility gates and versioned Arabic normalization only.
- Qualification fixtures under `tests/fixtures/embedding_qualification/` and `tests/fixtures/arabic_normalization/`.
- Contract tests under `tests/contract/` for pgvector, ParadeDB, normalization, and embedding dimensions.
- Updates to `docs/retrieval/ARABIC_NORMALIZATION.md`, `docs/adr/ADR-embedding-model-dimension.md`, `docs/evaluation/EMBEDDING_QUALIFICATION_REPORT.md`, and `docs/architecture/07-bm25-projection.md`.
- Initial Phase 2 evidence and docs-index links.

#### Packet 1 forbidden outputs

- The full application schema, RLS/roles, Auth configuration, Storage buckets, ingestion/projection workers, retrieval RPCs, HNSW indexes at production scale, LightRAG indexing, or bulk corpus embeddings.
- Installing `pg_search` in Supabase, changing the Phase 1 ParadeDB pin without evidence/ADR, or qualifying by model reputation.
- Golden tests for exact embedding float values.

#### Packet 1 ordered actions

1. Record exact local and managed-target PostgreSQL, pgvector, Supabase CLI, ParadeDB image/extension/Postgres-major, OpenAI API model identifiers, and relevant lockfile versions.
2. Create startup/migration checks that introspect pgvector version and the exact iterative-scan capabilities/GUCs required by the selected version. Prove local behavior and the approved managed target; extension presence alone is insufficient.
3. Verify ParadeDB image and extension version agreement, immutable digest, edition/license, required preload/startup behavior, unique key requirements, Unicode tokenizer, current SQL namespace/access method, and clean restart.
4. Build a frozen qualification slice disjoint from the future launch holdout. Include at least 20 Arabic/mixed-language cases plus representative English semantic, exact identifier/code, and vocabulary-mismatch cases. Record fixture provenance and prohibit later tuning on the final holdout.
5. Write the versioned Arabic raw-to-search fixture before SQL. Cover diacritics, tatweel, alef/hamza variants, ya/alef-maqsura, Arabic/Latin digits, punctuation, whitespace, mixed Arabic/English/codes, already-normalized input, and idempotence. Raw source/citation text and logical offsets never use the search form.
6. Implement one schema-qualified immutable normalization version and matching core/ParadeDB query transformation. Prove byte-identical SQL/core/ParadeDB output for every fixture case and query/index parity.
7. Run ParadeDB contracts for BM25 score/rank, phrase, boolean, filter, field boost, stable key, Unicode/Arabic normalized field, restart, concurrent/clean rebuild mechanism, cancelled-build cleanup, and index-version mismatch degradation. Bind every query to the selected version's docs.
8. Execute live bounded embedding requests for `text-embedding-3-small` at its documented 1536 default, `text-embedding-3-large` at 1536, and `text-embedding-3-large` at 1024. If the live API rejects an identifier/dimension, stop for ADR amendment rather than silently selecting another candidate.
9. Measure per-language Recall@10, MRR, nDCG, cost, latency, output length, finite values, representative index size, process/container peak build RSS, query working set, and storage. Include heap, HNSW, maintenance memory, concurrency, Docker shared memory, and LightRAG's future separate vectors in full-envelope extrapolation.
10. Accept the embedding ADR only when the winner fits the approved quality gates and combined steady-state vector working set below 60% of selected database RAM with maintenance headroom. Otherwise reduce dimensions/envelope, qualify `halfvec`/quantization with the same metrics, or resize through an approved ADR.
11. Append all commands, pins, primary sources, metrics, failures, managed-target evidence, and decisions to the packet evidence.

#### Packet 1 acceptance checks

- Local and managed-target pgvector 0.8+ plus required iterative-scan behavior are proven by introspection and selective-filter tests.
- Arabic normalization is byte-identical and idempotent across SQL, core, and ParadeDB for 100% of fixture cases.
- The pinned ParadeDB contract suite proves startup/restart, current-version BM25 APIs, query semantics, role-independent extension health, rebuild behavior, and version mismatch fallback.
- The disjoint qualification report includes all three required embedding candidates and per-language quality, latency, cost, output dimension, storage, and memory evidence.
- The accepted ADR pins only identifiers and dimensions the live API returned, plus `vector`/`halfvec`, distance operator, index version, rollback, and rebuild trigger.
- No bulk ingestion, retrieval quality tuning, or later-phase implementation was added.

#### Packet 1 negative tests

- Unsupported pgvector/iterative-scan capability fails startup/migration checks.
- SQL/core/ParadeDB normalization drift or projection-version mismatch fails closed.
- ParadeDB public port, runtime extension creation, wrong SQL namespace, unstable key, or unsupported edition feature fails qualification.
- Unsupported embedding dimension returns an explicit contract failure; no alternate is silently substituted.

#### Packet 1 stop routes

- Phase 1 evidence, selected tier, immutable ParadeDB pin/license, managed compatibility target, or bounded OpenAI access is absent.
- Quality/memory gates cannot select a candidate without changing signed targets.
- The pinned ParadeDB or normalization contract fails after bounded repair.

### Packet 2 — expand/contract-safe authoritative schema

#### Packet 2 preconditions

- Packet 1 is complete and the embedding type/dimension/index contract is accepted.
- Inspect the complete current migration history, schema diff, generated types, role bootstrap source, local reset behavior, and Phase 1 expand/contract ADR.
- Verify the exact pinned LangGraph persistence and LightRAG storage initialization contracts before capturing their schemas.

#### Packet 2 allowed outputs

- Forward migrations created by the verified Supabase CLI under `supabase/migrations/`.
- A single idempotent, documented cluster-role bootstrap source when custom roles cannot be safely owned by ordinary schema migrations.
- Versioned private ParadeDB projection migrations under `infra/paradedb/migrations/`.
- Typed domain/schema models and generated Supabase types at Phase 1-defined canonical paths.
- SQL/schema/ERD tests and documentation.

#### Packet 2 forbidden outputs

- RLS policies or broad browser/runtime grants before packet 3, live Auth flows, Storage objects before packet 5, scanner/parser/projection execution, retrieval RPC behavior, or managed deployment credentials.
- Same-release destructive drops, enum removals/renames, narrowing constraints, unbackfilled `NOT NULL`, incompatible function/policy replacement, or direct edits to generated types.
- Hand-authored LightRAG/LangGraph tables that disagree with pinned generated schemas.

#### Packet 2 migration families

Create one concern per migration where practical, in this dependency order:

1. extension compatibility gates and private schema creation;
2. versioned Arabic normalization;
3. `profiles`, singleton `company_settings`, authorization version, allowed domains, invitations, role/upload/MFA policy fields, and private FastAPI degraded-limit buckets;
4. documents, versions, sources, current-version pointer, visibility, ACL grants, source approvals, and scan events;
5. chunks, typed table manifests/columns, search terms, aliases, raw/search-normalized fields, provenance, and embedding columns fixed by packet 1;
6. ingestion, BM25 outbox/index-version, LightRAG index, dead-letter, lease/attempt/idempotency, and notification job foundations;
7. LightRAG source/chunk/evidence maps and entity rules;
8. conversations, messages, runs, citations, and feedback;
9. tool catalog, versions, permissions, and usage;
10. LLM usage, budget reservations, company/user limits, upload quota reservations, and visibility generations;
11. append-only audit events, chain anchors, restricted-read events, and durable admin notifications;
12. controlled LangGraph checkpoint/store and LightRAG storage schemas captured from the exact pinned setup routines;
13. private ParadeDB `bm25_chunks` projection and index-version metadata containing derived canonical IDs/search fields only; and
14. indexes, foreign keys, comments, checks, default privileges, and generated types after object families stabilize.

#### Packet 2 ordered actions

1. Produce a data dictionary before SQL. For every object record owner schema, authority/derived classification, writer/readers, retention, cardinality, bounded query path, deletion behavior, idempotency key, and owning later phase.
2. Use UUID identifiers and UTC timestamps consistently unless an existing Phase 1 contract says otherwise. Audit/ledger rows are immutable and have no ordinary update path.
3. Make `documents.current_version_id` the single canonical visibility pointer. Prevent a version from belonging to another document and document atomic current-version flip semantics.
4. Encode v1 visibility as `company_visible` default or `restricted`; restricted grants are per-user only. Do not add groups or role-wide restricted grants.
5. Add company-wide `authorization_version` and document/BM25 visibility generation fields that can be incremented atomically by later authorization changes.
6. Give durable jobs explicit status, priority, idempotency key, lease owner/expiry, heartbeat, attempt/max-attempt, next-attempt, error category, and payload-reference fields. Large payloads remain in Storage/canonical tables.
7. Make budgets/reservations and BM25 outbox/index versions durable and transactionally linkable; Valkey has no authoritative column/table substitute.
8. Run pinned LangGraph/LightRAG controlled setup only in an isolated bootstrap context, capture/review the generated schema/grants, convert it to the canonical controlled setup/migration artifact, and block runtime auto-DDL.
9. Create the ParadeDB projection schema with no user profile, conversation, raw privileged content, or canonical authority.
10. Apply migration reset from clean state twice, reapply seeds/role bootstrap/bucket setup as applicable, run destructive-change lint, compare schema/type outputs, and prove repeated setup is deterministic.
11. Regenerate types through the pinned CLI and compile strict Python/TypeScript consumers. Never hand-edit generated output.
12. Update ERD/database docs and append file-by-file migration evidence.

#### Packet 2 acceptance checks

- Every table/object named in canonical requirements has one documented authority, lifecycle, owner, writer, reader, and deletion/retention rule.
- Clean reset/setup succeeds twice with identical schema, generated types, role inventory, and private-schema exposure.
- Migration lint proves no same-release destructive or old-code-incompatible change.
- Current-version, ACL, graph-eligibility, outbox/version, budget, queue lease, audit immutability, and authorization-generation invariants are enforceable by schema/transaction boundaries.
- Pinned LangGraph/LightRAG schemas are reviewed, private, runtime-non-DDL, and not browser-accessible.
- ParadeDB contains only rebuildable projection/index-version data.

#### Packet 2 negative tests

- A migration containing managed-Supabase `pg_search`, a same-release drop/narrowing operation, or an unreviewed security-definer function fails static checks.
- Cross-document current-version assignment, duplicate idempotency key, invalid lease state, restricted graph eligibility, or audit mutation fails at the authoritative boundary.
- A second schema workflow, generated-type hand edit, or untracked Studio change is detected and rejected.

#### Packet 2 stop routes

- Packet 1 has not selected the embedding schema.
- Pinned LangGraph/LightRAG schema cannot be captured/reviewed without runtime DDL ambiguity.
- Reset/reapply/type generation is nondeterministic or migration lint cannot exercise real files.

### Packet 3 — least-privilege roles, RLS, ACL, and identity propagation

#### Packet 3 preconditions

- Packet 2 schema/reset/type checks pass.
- Real local credentials exist for each deployable role; tests can connect without superuser or `service_role`.
- The selected pool modes and database driver behavior are documented from current primary sources.

#### Packet 3 allowed outputs

- Idempotent role/bootstrap grants, RLS policies, security-invoker views, private RPCs, triggers/functions needed for authorization atomicity, and Storage-independent database security tests.
- Minimal backend/core identity resolution required to prove server-derived RPC context.
- `docs/security/AUTHORIZATION_MODEL.md`, `docs/security/IDENTITY_PROPAGATION.md`, RLS matrix, and sequence diagrams.

#### Packet 3 forbidden outputs

- General runtime `service_role`, table ownership/BYPASSRLS for API/worker, session-GUC identity on transaction-pooled paths, user-editable metadata authorization, public execution of privileged functions, or browser access to private schemas.
- Full application routers/chat/upload UI, live graph indexing, retrieval generation, or Phase 3 job processing.

#### Packet 3 role boundaries

- Browser `anon`/`authenticated`: Supabase Auth and packet-5 Storage paths only; no direct LightRAG, checkpoint, BM25, audit, budget, job, or private application table access.
- API runtime: execute only named application/RPC functions plus minimum health metadata; no arbitrary canonical writes, DDL, role changes, audit mutation, or LightRAG table access.
- Worker runtime: claim/update authorized jobs and canonical ingestion-owned rows; no arbitrary private conversation read or Auth administration.
- Checkpointer runtime: only its private checkpoint/store schema with session/direct pooling.
- LightRAG runtime: only reviewed private LightRAG schema and canonical mapping interfaces with session/direct pooling.
- Audit writer: insert through one append-only path; no update/delete.
- Migration/bootstrap: DDL/Auth setup only, unavailable to runtime containers.
- ParadeDB bootstrap/writer/reader: extension/DDL, projection mutation, and read-only query separated; no user/browser credentials.

#### Packet 3 ordered actions

1. Revoke default/public privileges, assign object ownership to non-runtime owner roles, and grant the minimum role matrix above.
2. Enable RLS on every exposed table before granting access. Add policies for owner, admin, member, viewer, disabled user, creator-private conversations/runs, explicit audit access, tool permissions, and document ACL.
3. Keep trusted role/capability data in authoritative profile/app metadata, never `user_metadata`; always re-resolve current profile/membership/session state because JWT claims may be stale.
4. Implement `company_visible` default and explicit restricted per-user grants. Only owner/admin can grant/revoke/change visibility; member upload permission never implies ACL control.
5. Implement authorization changes that atomically increment `authorization_version`; document visibility/deletion changes also increment visibility generation and enqueue required BM25/graph update/remove intent.
6. Make `graph_eligible=true` require current company-visible status and universal active-role readability. Reject restricted/non-current/deleted graph jobs. ACL downgrade atomically marks ineligible, emits high-priority `graph_acl_remove`, and prevents canonical resolution immediately.
7. Create only approved private RPCs with typed `caller_user_id`, `caller_role`, and `authorization_version`. Revoke execution from browser roles; API obtains values server-side and RPCs compare current authoritative state. Missing/forged/stale context yields no rows or a sanitized authorization failure, never evidence.
8. Prove transaction-pool safety: no request identity or prepared-statement/session state survives connection reuse. Session/direct paths are separately tested for checkpointer/LightRAG.
9. Test security-definer search-path shadow attacks, security-invoker view RLS, default grants, role ownership, and private schema/Data API exposure.
10. Run the full authorization matrix with real role credentials and append policy/grant/test evidence.

#### Packet 3 authorization matrix

Cover every combination that is meaningful across:

- company role: owner, admin, member without upload, member with upload plus MFA, viewer, disabled;
- document state: current company-visible, current restricted with grant, restricted without grant, non-current, deletion-pending/deleted;
- action: read evidence, preview, download capability, upload intent, mutate metadata, grant/revoke ACL, visibility flip, graph-job intent;
- ownership: own versus another user's conversation/message/run;
- identity context: valid, missing caller, forged user, forged elevated role, stale authorization version, revoked session;
- pool mode: direct/session versus transaction reuse;
- database role: API, worker, checkpointer, LightRAG, audit writer, migration/bootstrap, BM25 reader/writer/bootstrap.

#### Packet 3 acceptance checks

- User A cannot read User B private conversation/run or ungranted restricted document; owner/admin audit behavior matches the explicit policy and is itself audited.
- Viewer/member cannot mutate ACL; member upload permission does not grant administration; missing MFA blocks upload/document mutation.
- Missing/forged/disabled/revoked/stale RPC context returns no protected rows under transaction pooling.
- Restricted/non-current/deleted versions cannot become graph eligible or enqueue normal graph indexing.
- Browser/user JWT cannot reach private schemas; runtime roles are non-owner, non-superuser, non-BYPASSRLS, and cannot bootstrap.
- Security-invoker/search-path/default-grant attacks and concurrent identity reuse tests pass.

#### Packet 3 negative tests

- Modified `user_metadata` or stale `app_metadata` cannot elevate access.
- API role direct table write, audit update/delete, worker private-conversation read, BM25 reader write, BM25 writer extension creation, and browser LightRAG select are denied.
- ACL downgrade during a run increments authorization/visibility generations and invalidates the old snapshot before evidence resolution.

#### Packet 3 stop routes

- Any test uses bypass credentials, a policy cannot be exercised through the production boundary, or transaction pooling leaks identity.
- An RPC must trust a client-supplied role/ACL or a privileged function requires public exposure.

### Packet 4 — Auth, JWKS, MFA, invitations, and rate-limit ownership

#### Packet 4 preconditions

- Packet 3 profile/invitation/authorization structures and RLS pass.
- Local Supabase Auth and Inbucket run; current selected managed-plan Auth capabilities and limits are documented.
- An ADR resolves the privileged Auth administration boundary for invitation delivery, factor administration, disable/offboarding, and any other Auth Admin call without putting a broad secret in general API/worker/frontend runtime.

#### Packet 4 allowed outputs

- Verified Supabase Auth configuration, minimal backend/core JWKS verifier and current-membership/session checks, invitation/MFA recovery services through the approved privileged boundary, private FastAPI degraded counters, tests, and security/runbook docs.
- `docs/adr/ADR-privileged-auth-administration-boundary.md`, `docs/security/AUTH_RATE_LIMIT_OWNERSHIP.md`, and `docs/runbooks/SUPABASE_JWKS_ROLLOVER.md`.

#### Packet 4 forbidden outputs

- JWT shared-secret verification, HS256 fallback, copied JWT secret, trusting only token role claims, broad `service_role` in general runtime, browser exposure of admin secrets, or pretending sign-out instantly invalidates access tokens.
- Full Next.js Auth UI, SES production SMTP, managed production redirects, or FastAPI counters claimed to protect browser-direct Supabase Auth.

#### Packet 4 ordered actions

1. Verify every Auth/CLI/config key from the pinned local version's docs/help. Configure email/password, PKCE, Google OAuth, allowed local/preview/production redirect policy, password policy, short-lived access tokens, refresh-session behavior, and Inbucket local mail without inventing unsupported fields.
2. Implement initial owner bootstrap as a one-time, race-safe operation with audit, last-owner safeguards, and no public path after completion.
3. Implement single-use 24-hour application invitation records, allowed-domain checks, role/capability assignment, idempotent acceptance, expiry/replay rejection, and audit. The approved Auth Admin boundary owns any provider invite call.
4. Implement asymmetric JWT verification for exact issuer, audience, approved algorithm, signature, expiry, subject, and `kid`. Cache JWKS for at most ten minutes, account for provider/edge cache plus application cache, refresh once on unknown `kid`, and fail closed on fetch/selection failure.
5. Execute a real standby-to-active-to-retired rollover in an environment whose Auth implementation supports it. During overlap old/new tokens verify; retain the prior key for at least maximum access-token lifetime plus all cache margins; after revocation old tokens fail. A synthetic JWKS fixture supplements but does not replace provider lifecycle proof.
6. Re-resolve active membership, `authorization_version`, required AAL/MFA, upload capability, disabled state, and `session_id` for every request. Refresh-session revocation is not treated as immediate access-token revocation.
7. Require MFA for owner/admin and upload/URL/document-mutation-capable members. Qualify current supported factor types and AAL behavior; do not assume recovery codes.
8. Implement lost-factor recovery through an authorized owner/admin actor, out-of-band identity re-verification record, append-only initiation/completion events, admin factor reset through the privileged boundary, all-session revocation, capability suspension, and mandatory re-enrollment. Prevent the last owner from self-removing the only usable factor without a distinct verified recovery actor.
9. Map every Auth operation to its actual rate-limit owner. Hosted browser-direct sign-in/OAuth/reset/MFA uses selected-plan Supabase controls/captcha where supported; local Supabase is documented as not enforcing those limits. FastAPI/Valkey plus private Postgres degraded buckets cover only invitations and FastAPI-mediated upload/crawl/chat/admin mutations.
10. Test email/password, PKCE verifier mismatch/replay, OAuth configuration, invitations, MFA/AAL, disable/downgrade revocation, JWKS failures/rotation, rate ownership, and Inbucket messages. Append redacted evidence.

#### Packet 4 acceptance checks

- No HS256/shared-secret path exists; issuer/audience/algorithm/expiry/subject/`kid`, unknown-key refresh, cache bound, and network failure are tested fail-closed.
- Provider key rollover is proven in a supported environment or packet 4 remains blocked; a mock-only drill cannot close the gate.
- Initial owner, invitation/domain, email/password, Google OAuth configuration, PKCE, Inbucket, session revocation/current-session checks, and last-owner controls work.
- MFA/AAL gates cover owner/admin/upload-capable members; audited lost-factor recovery revokes sessions and requires re-enrollment.
- The Auth Admin secret exists only inside the approved isolated boundary and is absent from frontend, API, worker, logs, images, and general health paths.
- Rate-limit documentation and tests distinguish hosted provider enforcement, local absence, Valkey fast path, and atomic Postgres degraded path.

#### Packet 4 negative tests

- Wrong issuer/audience/algorithm, expired token, unknown `kid` after one refresh, stale membership, revoked `session_id`, disabled user, forged role metadata, invitation replay/expiry, missing MFA, last-owner unsafe recovery, and provider outage all deny.
- Local tests must fail if labeled as proof of hosted Auth throttling.
- General runtime environment scans fail on `service_role`/Auth Admin secrets.

#### Packet 4 stop routes

- Current local/managed Auth cannot prove asymmetric lifecycle, required MFA operation, or selected-plan throttle behavior.
- Privileged Auth administration requires a broad secret but no approved isolation ADR/implementation exists.
- Google OAuth/SMTP external configuration is unavailable and the done gate cannot be exercised honestly.

### Packet 5 — private Storage, quota capabilities, graph eligibility, and retention

#### Packet 5 preconditions

- Packets 3–4 identity, MFA, roles, privileged-boundary, and Storage RLS prerequisites pass.
- Verify selected Supabase Storage upload methods, token lifetime, file limits, bucket restrictions, RLS operations, and cleanup APIs from current docs.
- An ADR resolves worker/admin Storage operations if the platform offers only a broad secret rather than a truly scoped worker credential.

#### Packet 5 allowed outputs

- Private bucket setup/policies, upload admission/quota reservations, signed or JWT upload capability implementation selected by ADR, post-upload actual-size verification hooks, idempotent quarantine cleanup, scan/provenance metadata paths, graph eligibility enforcement, retention/legal-hold structures, durable notifications, tests, and docs.
- `docs/adr/ADR-upload-capability-and-storage-privilege.md`.

#### Packet 5 forbidden outputs

- Public document buckets, browseable quarantine, frontend/admin secrets, direct SQL mutation/deletion of `storage.objects`, invented narrow service tokens, ClamAV/freshclam execution, MIME/archive/parser validation, promotion/parsing/OCR/embedding, crawling, or graph indexing.
- Claiming the 15-minute application admission lease shortens a provider token that remains valid longer.

#### Packet 5 ordered actions

1. Create exactly the private buckets and versioned path contracts in the canonical requirements. Bucket setup is reproducible and generated by the approved local setup/migration procedure.
2. Define browser/user and privileged-operation matrices for list/read/insert/update/delete/move/copy. Quarantine uploads are user-scoped and non-browseable; originals/snapshots/table artifacts/exports remain private.
3. Select the upload mechanism through ADR. Record provider token/session lifetime, replay/revocation behavior, object-size and method limits, RLS semantics, large/resumable upload behavior, and operational load. Keep the application admission/quota reservation at a provisional 15 minutes, but label the effective upload capability with the provider's actual lifetime.
4. If the provider's fixed signed-upload token exceeds the approved exposure, choose and prove a user-JWT RLS/resumable or backend-mediated alternative, or obtain explicit security acceptance of the longer token. Do not silently weaken the TTL.
5. Before capability issuance, atomically reserve declared bytes against durable per-user rolling-byte and company quarantine caps where enforceable, bind reservation to user/session/path/idempotency key, and expire/release it idempotently. Provider plan/global/bucket limits are separate checks.
6. After upload, compare actual object metadata/size to reservation and limits. Over-limit, wrong-path, never-finalized, or expired objects remain quarantined and are deleted through the Storage API with append-only audit; metadata-table deletion alone is prohibited.
7. Implement the default 24-hour never-finalized quarantine cleanup as bounded, idempotent work. Use a controllable test clock and prove retries do not double-decrement quotas or orphan provider bytes.
8. Create scan-event/provenance write foundations with object hash, declared category, uploader/session, engine/database version fields, timestamps, result, and network/source approval provenance. Phase 3 remains the only producer of genuine malware/validation success.
9. Enforce current-version/company-visible/universally-readable graph eligibility and restricted ACL removal atomicity. No restricted or non-current version can create a normal graph job.
10. Add retention/legal-hold/offboarding structures using signed Phase 1 defaults. Implement only Phase 2-owned quarantine cleanup and authorization/session effects; later purge workflows remain planned.
11. Add durable anomaly/admin notification fixtures for byte/rate spikes, quarantine accumulation, repeated scan failures, and unusual crawl domains. Local email goes through Inbucket and never auto-approves content.
12. Test bucket/operation/identity/quota/cleanup/graph/audit boundaries and append effective capability lifetime plus privileged-credential evidence.

#### Packet 5 acceptance checks

- Every bucket is private; quarantine cannot be listed; user uploads only to the reserved own path; cross-user and wrong-bucket operations deny.
- Effective upload capability lifetime is truthful and approved, with provider limit provenance and no claim that a 15-minute reservation revokes a longer token.
- Declared and actual bytes, per-user/company caps, reservation expiry, over-limit purge, and quota reconciliation are durable/idempotent.
- Storage deletion uses the API and removes provider bytes; cleanup retries are safe.
- Scan records cannot be represented as clean without Phase 3 evidence.
- Restricted/non-current/deleted documents cannot become graph eligible; ACL downgrade emits removal intent atomically.
- Restricted evidence/preview/download/capability events and anomaly notifications enter append-only audit/admin channels without raw long-retention content.

#### Packet 5 negative tests

- Cross-user upload, bucket listing, token reuse beyond documented behavior, capability after role/MFA/ACL downgrade, size mismatch, reservation replay, cleanup crash/retry, broad worker bucket access, restricted graph job, and direct metadata deletion all fail safely.
- Runtime secret scan rejects broad Storage secrets outside the approved isolated boundary.

#### Packet 5 stop routes

- The required 15-minute effective exposure cannot be met and the user has not accepted the documented provider duration or alternate proxy cost.
- Worker/admin Storage behavior requires an unapproved broad secret.
- Quota or cleanup behavior cannot be proven against actual Storage bytes.

### Packet 6 — connection isolation, protected credentials, audit integrity, and exit

#### Packet 6 preconditions

- Packets 1–5 pass with final role/schema/type state.
- The selected Supabase tier hard connection limit and each custom role's Supavisor/direct compatibility are proven from docs and real connections.
- Inspect actual container process/worker counts and pool defaults; do not calculate from planned values alone.

#### Packet 6 allowed outputs

- `docs/architecture/05-database-connections.md`, `06-database-workload-isolation.md`, final `07-bm25-projection.md`, `docs/security/PROTECTED_MIGRATION_CREDENTIALS.md`, `docs/security/AUDIT_CHAIN.md`, final generated types, role settings, audit-chain implementation/tests, notifications proof, and completed Phase 2 evidence.

#### Packet 6 forbidden outputs

- AWS Secrets Manager/GitHub OIDC/KMS/S3 Object Lock implementation, read-replica provisioning, production pool changes, load claims, SES/on-call routing, or Phase 9/10 evidence.
- Runtime bootstrap credentials, audit writer update/delete, unbounded pools/work memory, or connection math copied from provisional caps without validating process multiplicity.

#### Packet 6 ordered actions

1. Inventory every process, replica, pool, connection mode, maximum, overflow, health/operations connection, and selected-tier hard limit. Compute worst-case Supabase total and require it below 70%, including two reserved operations connections.
2. Start with provisional caps only as candidates: API transaction 10, API/checkpointer session/direct 4, API LightRAG session/direct 4, worker transaction 6, worker LightRAG session/direct 4, and operations 2. Reduce or resize through ADR if process multiplication breaches the threshold.
3. Prove transaction mode for stateless API RPC traffic and session/direct mode for checkpointer/LightRAG using real custom roles/drivers. Disable assumptions about prepared statements or session GUCs in transaction mode.
4. Apply and introspect role-specific `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`, bounded `work_mem`, pool caps, query tags, and maintenance concurrency-one rules.
5. Document foreground p95/CPU/IO pause thresholds and the isolation ladder. Read replicas remain future candidate generation only; primary authorization recheck remains mandatory.
6. Compute ParadeDB's independent pool/resource budget from actual containers and provisional read 4/write 2/operations 1. Record statement timeout, CPU/memory/disk bounds, encrypted-volume decision, no-public-port proof, and 70%/lag/rebuild triggers.
7. Implement append-only hash-chained audit events with deterministic canonical serialization, previous hash, actor/resource/event/purpose identifiers, and redaction. Audit writer cannot update/delete. Anchoring remains Phase 10, but local tamper verification is real.
8. Prove restricted evidence/preview/download, upload/source approval, Auth recovery, ACL, session, and admin events enter the chain; mutation/reordering/deletion tests are detected.
9. Document local migration/bootstrap custody and the managed protected one-shot OIDC/secret-manager design without provisioning it. General runtime containers and health paths cannot access bootstrap credentials.
10. Regenerate final types, run clean reset/reapply, role/RLS/Auth/Storage/ParadeDB/normalization/embedding/connection/audit tests, and map every `Done when` clause to evidence.
11. Request explicit user acceptance. Do not mark the phase complete or begin Phase 3 in the same run.

#### Packet 6 acceptance checks

- Supabase worst-case connections remain below 70% of the selected hard limit with process multiplication and reserved operations capacity shown.
- Custom roles work in their assigned pool modes; transaction reuse leaks no identity/session state.
- Role timeouts/memory/query tags are applied and introspected; maintenance pause/isolation triggers are documented.
- ParadeDB pool/resource/network budget is independent, bounded, and linked to signed target responses.
- Audit-chain mutation, deletion, and reordering are detected; audit writer cannot update/delete; sensitive payload redaction passes.
- Bootstrap/Auth Admin/Storage privileged credentials are absent from general runtime/frontend/images/logs and managed custody is clearly unverified until Phase 10.
- Final generated types match clean schema; every Phase 2 done item has reproducible evidence and explicit managed-only limitations.

#### Packet 6 negative tests

- Pool multiplication above 70%, wrong pool mode, session-GUC reliance, prepared-statement assumption in transaction mode, timeout absence, runtime bootstrap secret, audit mutation, or generated-type drift fails the gate.
- A read-replica or ParadeDB result cannot bypass primary canonical ACL/current-version validation in documented future paths.

#### Packet 6 stop routes

- Selected tier or real pool compatibility is unknown, connection math exceeds 70% without approved resize, or audit tamper proof fails.
- Any `Done when` item depends on a skipped provider, managed, security, or real-role test.

## Cross-packet invariants

- Canonical Supabase state and authorization always outrank derived ParadeDB/LightRAG/cache data.
- Managed Supabase never installs `pg_search`; ParadeDB never becomes canonical and has no browser/user JWT path.
- Raw source/citation text is preserved; search normalization is versioned, byte-identical, idempotent, and never used for display offsets.
- Runtime roles are distinct, non-owner, non-BYPASSRLS, and cannot bootstrap; general runtime/frontend never receives `service_role`.
- Browser-direct Auth limits belong to Supabase where supported; FastAPI counters cover only traffic FastAPI receives.
- Every authorization-affecting change increments authoritative version/generation and invalidates stale contexts atomically.
- Only current company-visible universally readable versions may be graph eligible. Restricted evidence never enters LightRAG.
- Storage provider bytes are managed through the Storage API; metadata SQL is not an object-deletion mechanism.
- Budgets, jobs, quota reservations, audit, notifications, idempotency, and security state are durable; Valkey is never authority.
- Generated types, schema diffs, successful SQL, process liveness, and mock tests do not replace negative authorization/provider contract proof.
- Each packet appends evidence and stops on unverifiable provider behavior. Phase 2 remains pending until packet 6 evidence is accepted.

## Phase sequence requirement

Program sequence item 2 covers local Supabase, migrations, per-deployable roles, connection-budget/workload-isolation proof, asymmetric signing/JWKS rollover, Storage/Auth/upload-MFA/invitations/RLS/graph-eligibility, disjoint Arabic/mixed embedding bake-off plus model/dimension memory ADR, protected migration-credential design, retention/audit-chain foundations, and Inbucket tests.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update the phase evidence document specified by the repository documentation index with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

The following requirements are redistributed from the original comprehensive plan. They remain normative. Legacy section numbers are preserved so cross-references still resolve through the [section map](../hybrid-graph-rag_ab5281ef.plan.md#legacy-section-map).

## 4. Supabase schema, Auth, roles, and Storage

> **Phase 2 ownership note:** Implement the authoritative Supabase schema, BM25 projection schema/outbox/bootstrap, roles, RLS/Auth/MFA/JWKS contracts, Storage buckets/policies, scan/provenance data model, graph-eligibility enforcement, connection budgets, and security tests. Phase 3 owns the running ClamAV/freshclam pipeline, object validation/promotion, parsing, crawling, embeddings, and idempotent BM25 projection lifecycle; Phase 4 owns BM25 candidate querying/fusion quality; Phase 5 owns real LightRAG indexing and graph cleanup. Phase 2 must make those later operations least-privilege and testable without faking them.
>
> **Canonical migration ownership:** Phase 2 exclusively owns the pgvector 0.8+/iterative-scan compatibility gate, the exact ParadeDB/`pg_search` image/extension qualification, and the versioned Arabic-normalization SQL migration plus cross-runtime conformance fixture. Phase 4 consumes those artifacts to build retrieval RPCs/BM25 queries and prove behavioral quality; it must not create a competing normalizer or postpone compatibility discovery.

Create migrations for:

- `profiles`, singleton `company_settings`, `team_invitations`, allowed-email-domain configuration, and private `auth_rate_limit_buckets` for the Valkey-down degraded path.
- `documents`, `document_versions`, `document_sources`, `document_chunks`, `document_tables`, `document_table_columns`, `document_search_terms`, `search_aliases`, `document_acl`, `source_approval_requests`, and `document_scan_events`.
- `ingestion_jobs`, `bm25_index_jobs`, `bm25_index_versions`, `lightrag_index_jobs`, `lightrag_source_map`, `lightrag_chunk_map`, `graph_evidence_map`, `graph_entity_rules`, and `dead_letter_jobs`.
- `conversations`, `messages`, `runs`, `citations`, and `user_feedback`.
- `tool_catalog`, `tool_versions`, `tool_permissions`, and `tool_usage_events`.
- `llm_usage`, `budget_reservations`, `audit_events`, `audit_chain_anchors`, and configurable company/user limits.
- LangGraph checkpoint/store objects in a private schema, initialized once through a controlled setup step rather than per request.
- A private LightRAG schema holding the exact tables required by the pinned LightRAG version for `PGTableGraphStorage`, `PGVectorStorage`, `PGKVStorage`, and `PGDocStatusStorage`.

Run ParadeDB as a separate private self-hosted PostgreSQL service because managed Supabase does not provide arbitrary `pg_search` installation or `shared_preload_libraries`. Phase 2 pins the exact Postgres-compatible ParadeDB image digest and `pg_search` version from current primary documentation, records license/Community-versus-Enterprise acceptance, and contract-tests Unicode tokenization, BM25 scoring, phrase/boolean queries, field boosts, filters, stable key fields, extension startup, and clean rebuild. The service contains a derived `bm25_chunks` projection and index-version metadata only. It uses separate bootstrap, `bm25_writer`, and read-only `bm25_reader` roles; runtime roles cannot create extensions or bypass the adapter, and no user/browser JWT connects to ParadeDB.

Enable RLS on every exposed table and add explicit policies for the four roles. Documents and approved tools are shared across active company users according to role/ACL; conversations, messages, and runs are private to their creator unless an owner/admin is explicitly permitted to audit them. Authorization uses the server-controlled profile role or trusted `app_metadata`; never use editable `user_metadata`. Views use `security_invoker`, privileged functions live in a private schema with a fixed `search_path`.

Identity propagation from FastAPI to Postgres is explicit and transaction-pool safe. FastAPI verifies the JWT, resolves the active membership and MFA/session state server-side, and passes only server-derived `caller_user_id`, `caller_role`, and a monotonic authorization-snapshot/version as typed arguments to approved application/retrieval RPCs. Client-supplied role, user ID, ACL, or snapshot claims are never trusted. RPCs filter on those arguments plus current-version/deletion predicates and return zero rows for missing, forged, revoked, disabled, or stale context. Transaction-pooled API paths must not depend on session GUCs such as `set_config('request.jwt.claims', ...)`; any future session-local path uses a documented session/direct pool and dedicated contract test. Negative tests cover user-A credentials with user-B document IDs, ACL downgrade during a run, disabled users, and omitted caller context.

The v1 document ACL model has two visibility states. `company_visible` is the default for new uploads and is readable by every active company role; `restricted` uses explicit per-user grants in `document_acl` and is Hybrid-only. Owner/admin may grant, revoke, or change visibility; members—even upload-capable members—cannot change ACLs; viewers may receive read-only grants. Groups and role-wide restricted grants are deferred. Every RLS/RPC/citation/download path applies the same model, and only company-visible current versions may become graph eligible.

The LightRAG eligibility rule is non-negotiable in v1: `graph_eligible=true` requires a current, company-visible document version readable by every active member/viewer. Job creation rejects graph indexing for ACL-restricted versions. Restricting a graph-indexed version atomically marks it ineligible and writes a high-priority `graph_acl_remove` job; the canonical resolver rejects that version before the ACL transaction becomes visible. The workspace becomes `filtered_dirty` while targeted cleanup and a batched clean rebuild proceed. If stable source references or resolver verification are unavailable, quarantine the graph and degrade Combined to Hybrid. Security tests prove restricted entity/relation text never appears in Combined or graph inspection. Per-ACL LightRAG workspaces are explicitly deferred.

LightRAG tables are never queried by the browser or user JWT. Define schema-scoped roles: API role for approved application functions/tables, query/checkpointer role for its private checkpoint schema, worker role for jobs/canonical writes plus LightRAG, append-only audit writer with no update/delete grant, and migration/bootstrap role for DDL/Auth administration. Runtime API/worker containers do not receive the Supabase `service_role` key. Browser uploads use the user's JWT plus Storage RLS. Do not assume Supabase provides a first-class narrowly scoped worker Storage token: qualify the current platform contract and, if only a broad secret can perform required worker operations, isolate it behind the user-approved privileged Storage boundary in `ADR-upload-capability-and-storage-privilege` rather than placing it in the general worker. Operations requiring the Supabase Auth Admin API similarly use the approved isolated boundary in `ADR-privileged-auth-administration-boundary`; the general API, worker, frontend, and health paths never receive that secret. The migration/bootstrap credential is environment-specific, stored only in AWS Secrets Manager for managed environments, never a long-lived GitHub secret, unavailable to runtime containers, and usable only by the protected migration procedure in Sections 13–14.

Pin LightRAG exactly, capture/review its generated schema, run `initialize_storages()` as a controlled migration/bootstrap job, cap its pool, and block unreviewed runtime schema changes during normal API startup. Phase 2 creates [`docs/architecture/05-database-connections.md`](../../../docs/architecture/05-database-connections.md) with the selected Supabase tier's hard limit and explicit per-service budgets. API request/RPC traffic may use transaction pooling, but LangGraph checkpointer and LightRAG must use Supavisor session mode or direct connections; they are never assumed compatible with transaction mode. Provisional caps are API transaction 10, API/checkpointer session/direct 4, API LightRAG session/direct 4, worker transaction 6, worker LightRAG session/direct 4, and two reserved operations connections. Before implementation, Phase 2 must prove these fit below 70% of the selected tier; otherwise upgrade the tier or reduce process/pool counts. Phase 9 revalidates all paths and HNSW build/query memory under load.

ParadeDB has an independent same-host connection/resource budget documented in [`docs/architecture/07-bm25-projection.md`](../../../docs/architecture/07-bm25-projection.md): provisional API read pool 4, worker writer pool 2, one operations connection, bounded statement timeout, hard CPU/memory/container limits, encrypted volume, and no public port/provider egress. These do not consume Supabase connections. If BM25 index memory/CPU breaches 70% of its allocation, p95 top-75 exceeds the signed target, projection lag exceeds five minutes, or clean rebuild misses the signed window, reduce the envelope or move the `Bm25Retriever`/projection service to dedicated ParadeDB Enterprise/BYOC or another approved BM25 backend through an ADR.

Connection caps are not workload isolation. Phase 2 also creates [`docs/architecture/06-database-workload-isolation.md`](../../../docs/architecture/06-database-workload-isolation.md) and applies role-specific `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`, bounded `work_mem`, pool caps, and query tags. HNSW creation/reindex and clean LightRAG rebuilds run one at a time in approved maintenance windows and pause automatically when user-query p95 breaches its gate or database CPU/IO exceeds 70%. After query/index tuning and vertical sizing, sustained CPU/IO above 70% for three 15-minute windows in a week, cache-hit degradation below the signed target, or three p95 breaches triggers the isolation ladder: first move read-heavy Hybrid candidate generation to a qualified Supabase read replica when reads dominate, monitor asynchronous lag, and revalidate every selected ID/current-version/ACL against the primary before use; if graph rebuild/storage dominates or replica lag cannot meet deletion/ACL semantics, move LightRAG storage behind `GraphRetriever` to dedicated managed Postgres instead. No replica result bypasses primary canonical authorization.

Role baseline:

- Owner: company configuration, billing/budgets, members, all documents/tools.
- Admin: members, documents, ingestion, graph rebuilds, tool configuration, audit access.
- Member: chat and feedback; upload/manage capability is a separately grantable permission that requires enrolled MFA.
- Viewer: chat and read-only document/citation access.

Configure Supabase Auth with PKCE, email/password, Google OAuth, short-lived access tokens, refresh cookies, allowed Vercel production/preview redirects, and SES custom SMTP. Offer MFA to every account; require it for owner/admin and for any member granted upload, URL-source, or document-mutation permission. Use single-use invitation tokens with a 24-hour TTL, enforce a documented password policy, and revoke refresh sessions when a user is disabled or their privileged/upload role is downgraded.

Auth rate-limit ownership follows the network boundary. Browser-direct email/password sign-in, Google OAuth, password reset, and Supabase MFA enrollment/challenge use explicitly documented Supabase Auth built-in rate limits and captcha/bot controls when supported by the selected hosted plan; FastAPI/Valkey does not claim to throttle requests it never receives. Current Supabase local development does not enforce hosted Auth rate limits, so local tests verify configuration/ownership and explicitly must not claim provider-throttle proof. A hosted environment that implements the selected controls must exercise enforcement before this acceptance item is checked. FastAPI Valkey plus the private Postgres degraded bucket owns invitation acceptance and FastAPI-mediated upload, crawl, chat, and administration mutations. Tests verify the boundaries independently and prove that a provider-owned Auth limit is not silently replaced by an application counter.

MFA recovery is a server policy, not only a UI screen. Recovery-code or self-service behavior exists only if the pinned Supabase Auth version and a real contract test prove it; do not assume recovery codes. A lost-factor reset for an owner/admin or upload-capable user requires an authorized owner/admin actor through the isolated privileged Auth boundary, documented out-of-band identity re-verification, append-only audit events for initiation/completion, refresh-session revocation, current-session rejection, capability suspension, and mandatory re-enrollment before privileged/upload actions. The last owner cannot remove their own only usable factor without a separately verified recovery actor/procedure.

Asymmetric Supabase JWT signing keys and JWKS verification are mandatory in local qualification and every managed environment; legacy HS256 shared-secret verification is prohibited in production and no JWT secret is copied into FastAPI. Phase 2 verifies issuer/audience/approved algorithm/signature/expiry/subject and `kid` selection against Supabase JWKS, caps the application JWKS cache at ten minutes, refreshes once on an unknown `kid`, and fails closed if no valid key exists. Rotation creates a standby key, waits until provider/edge and application caches can observe it, tests old/new token verification, activates it, retains the previous key for at least the maximum access-token lifetime plus the combined provider/application cache margin, then revokes it. A synthetic JWKS fixture does not prove provider key-lifecycle parity; if the pinned local Auth stack cannot execute the lifecycle, the packet remains blocked pending an approved real environment. Staging proves rollover without authentication outage before production. The frontend uses `@supabase/ssr`; FastAPI additionally resolves current membership, MFA/upload permission, authorization version, `session_id` revocation, and disabled state for every request because sign-out/revocation does not invalidate an already-issued access token before expiry by itself.

Use private Supabase Storage buckets for originals and URL snapshots. Select a user-JWT RLS, signed-upload, resumable, or backend-mediated upload mechanism only after qualifying the pinned Storage contract in `ADR-upload-capability-and-storage-privilege`; the browser never receives privileged credentials. The desired application admission/quota reservation expires after a provisional maximum 15 minutes, but the effective upload capability lifetime is the provider token/session lifetime. If the provider fixes signed-upload tokens at a longer lifetime and does not support revocation, do not describe the capability as 15 minutes: prove an approved alternate mechanism or obtain explicit security acceptance of the longer exposure. Declared size is advisory before upload. Enforce selected-plan global/bucket/object/method limits, durable per-user rolling-byte quota, and company quarantine-byte cap before capability issuance where enforceable; after upload, verify actual size and purge/audit over-limit objects before parsing or promotion. A scheduled idempotent cleanup deletes never-finalized quarantine objects after a configurable default 24 hours through the Storage API; direct deletion of `storage.objects` metadata is not object deletion. Validate actual MIME signature, archive structure, parser limits, and malware status before promotion. Pin and patch the ClamAV engine image, but update digitally signed malware databases with `freshclam` at least daily. Record engine version, functionality level, signature database versions/timestamps, result, and object hash in `document_scan_events`. Production readiness fails when signatures are older than 24 hours or incompatible with the engine; the frozen signature fixture is CI-only. Detected, unscannable, stale-signature, or over-limit objects remain quarantined and never parse/index. Re-scan a quarantined object before promotion whenever its prior scan is older than 24 hours or the active signature version changed. Signed download URLs are short-lived according to the qualified provider contract and authorization is rechecked before issuance.

Every corpus write records uploader user/session, source/hash, declared data category, approval, scan version, and network provenance in append-only audit events. Restricted-document evidence inclusion, restricted preview access, and signed-download URL issuance are also always audited with actor, document/version, run/citation or purpose, and expiry identifiers but no full passage or raw long-retention IP payload. Members submit URL sources as pending requests; an owner/admin approves the domain/start URL before the crawl job exists. Configurable anomaly detectors alert admins on upload-rate/byte spikes, quarantine accumulation, repeated scan failures, unusual/new crawl domains, or abrupt corpus-write patterns; they do not silently auto-approve or label content as trustworthy. Before managed alert routing exists, alerts write a durable in-app admin notification and send development email through Inbucket; Phase 10 extends this to SES/on-call routing while preserving the in-app fallback.

### Exact file-storage layout

Files are never committed to Git and are not permanently stored in the FastAPI or worker containers.

- `documents-quarantine`: the browser uploads new files here through a short-lived signed URL. Users cannot browse this bucket directly.
- `documents-originals`: accepted, validated originals are promoted here. A versioned path such as `documents/{document_id}/versions/{version_id}/{safe_filename}` prevents name collisions.
- `web-snapshots`: downloaded HTML/text snapshots from approved URL crawls, grouped by source ID and crawl version.
- `table-artifacts`: versioned Parquet files generated from CSV/XLSX sheets, with typed schema, source sheet/range mapping, and no public access.
- `exports`: optional generated exports. Objects expire automatically unless the user explicitly keeps them.

In local development these buckets are provided by the local Supabase Docker stack and their bytes live in Docker-managed development volumes, outside the repository. In production the same logical buckets live in managed Supabase Storage. Database rows store the bucket name, object path, hash, media type, size, status, and version; application code passes IDs/paths rather than file bytes between stages.

The canonical text extracted from accepted files is stored as `document_chunks`; Hybrid embeddings/trigram/search terms, normalized projection text, BM25 outbox rows, and active BM25 index version live in Supabase. ParadeDB stores a rebuildable projection keyed by canonical chunk/version IDs with searchable title/heading/alias/body fields, language/date/tag/authority metadata, current/visibility generation, and opaque ACL scope IDs. Typed spreadsheet data is private Parquet plus a manifest with workbook/sheet/cell provenance. LightRAG keeps independent chunks/vectors, so `lightrag_source_map` maps documents, `lightrag_chunk_map` maps internal chunks, and `graph_evidence_map` maps graph objects to thresholded canonical passages. Before answer generation, every BM25 and graph candidate must resolve through a batched authoritative Supabase current-version/deletion/ACL check to surviving canonical chunks/original files.

Phase 2 migration/startup checks fail if local or managed Supabase exposes pgvector below 0.8 or lacks the required iterative-scan setting; do not defer this compatibility discovery until retrieval implementation.

The Arabic normalization migration ships a conformance fixture of raw→search-form pairs covering diacritics, tatweel, alef/hamza, ya/alef-maqsura, digits, mixed Arabic/English/codes, punctuation, and already-normalized idempotence. Index-time and query-time SQL must return byte-identical normalized forms locally and on managed Supabase; raw text, offsets, and citation display never use the search-only form.

The core query normalizer and ParadeDB projection must produce byte-identical output to the Phase 2 SQL fixture for every case before BM25 qualification. ParadeDB uses its verified Unicode word tokenizer over that normalized search-only field; no English stemmer is applied to Arabic. Query-time normalization version must match the active projection version or BM25 fails closed/degrades rather than querying an incompatible index.

All migrations follow [`docs/adr/ADR-zero-downtime-migrations.md`](../../../docs/adr/ADR-zero-downtime-migrations.md): expand, deploy backward-compatible code/backfill, then contract in a later release. Static checks reject same-release destructive drops, narrowing constraints, enum removals, or incompatible RLS/function changes without an approved multi-release path. The old API image must remain compatible with every expansion migration during its drain window.

## Phase deliver, review, and done gate

### Phase 2 — Identity and data

- Deliver: expand/contract-safe migrations and lint policy, pgvector 0.8+/iterative-scan plus private ParadeDB/`pg_search` compatibility gates, BM25 projection/outbox/version schema and separate roles, disjoint embedding/lexical qualification slice with at least 20 Arabic/mixed cases, small-1536 versus large-1536/reduced-large report, pinned embedding model/dimension/index ADR with full-envelope memory math, deployable-specific DB/Storage roles, typed server-derived identity propagation, explicit company-visible/restricted per-user ACL model, Supabase and BM25 connection/resource budgets plus workload-isolation ladder, asymmetric Auth signing/JWKS rollover, Supabase-Auth/FastAPI rate-limit ownership, MFA/recovery including upload-capable members, owner bootstrap, OAuth/email, invitations/session revocation, enforceable upload quotas/quarantine cleanup, Storage/RLS, graph eligibility, read/write hash-chained audit foundation, local admin notifications, protected migration-credential/OIDC design, retention schema, and generated types.
- Review: exact role/ACL grant permissions and default visibility, ParadeDB pin/digest/license/private-network/reader-writer grants, BM25 Unicode/Arabic/index-version contract, forged/missing identity context under transaction pooling, signing-key cache/rotation and HS256 prohibition, direct Supabase Auth versus FastAPI rate ownership, upload permission/MFA recovery, private conversations, upload/quarantine quota mechanics, restricted read auditing, Supabase/ParadeDB pool caps/timeouts, per-language embedding and BM25 Recall@K/MRR/nDCG versus memory/cost/latency, holdout separation, workload split triggers, migration compatibility/custody, offboarding, and retention.
- Done when: local and managed-target pgvector 0.8+/iterative-scan compatibility, byte-identical SQL/core/ParadeDB Arabic-normalization conformance, and pinned ParadeDB `pg_search` startup/BM25 score/phrase/boolean/filter/field/key contract tests are proven; no `pg_search` installation is attempted in managed Supabase; the disjoint Arabic/mixed embedding/lexical qualification, candidate comparison, pinned model/dimension/index ADR, peak-build/working-set HNSW memory math, and BM25 projection resource estimate justify selections before bulk ingestion; expand/contract lint, repeatable migration reset/reapply, BM25 outbox/version schema, old-code compatibility expectations, and generated types match the documented schema; deployable-specific Supabase/Storage/BM25 roles, typed identity propagation, RLS/RPCs, private schemas, explicit ACL grants/defaults, graph eligibility, private conversations, and negative tests return zero unauthorized rows for forged/missing/disabled/revoked/stale context under transaction pooling; ParadeDB has no public/browser access and runtime roles cannot bootstrap extensions; asymmetric JWKS verification and a real supported-environment standby→active→retired rollover work without HS256 fallback; initial owner bootstrap, email/password, Google OAuth, invitation/allowed-domain flows, Inbucket email inspection, hosted provider-owned Auth throttle qualification without false local claims, FastAPI degraded buckets, MFA plus audited lost-factor recovery, current-session rejection, offboarding, and upload-permission downgrade work; the Auth Admin and Storage privileged boundaries are approved and broad secrets are absent from general runtime; per-user/company quotas, truthful effective upload-capability lifetime, actual-size enforcement, Storage-API cleanup, and never-finalized quarantine cleanup are proven; restricted evidence/preview/download events enter the append-only chain and anomaly fixtures create durable in-app/Inbucket admin notifications; Supabase plus ParadeDB connection/resource budgets and isolation triggers fit approved caps; graph-ineligible documents cannot create LightRAG jobs; audit-chain mutations are detectable; and protected migration credentials, retention, Storage policies, and generated types are reviewed without exposing bootstrap credentials to runtime containers.
