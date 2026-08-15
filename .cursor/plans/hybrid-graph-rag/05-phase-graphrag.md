---
name: hybrid-graph-rag-phase-05-graphrag
phase: 5
status: pending
depends_on: [1, 2, 3, 4]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 5: GraphRAG

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Treat this file as the only implementation scope for Phase 5. Later-phase files may clarify an interface but do not authorize later-phase implementation.
3. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions before editing. This plan describes targets, not proof that a file or API already exists.
4. Load the relevant workspace skill files listed below before implementation.
5. Before every work packet, state the requirement and concrete acceptance checks. Implement the smallest complete packet.
6. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
7. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
8. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Phase 1 must define these commands; later phases must inspect rather than invent them.
9. Update documentation in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
10. Record proof in the exit record. If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR/plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md)

## Relevant workspace skills

- [`.cursor/skills/implement-lightrag-graph/SKILL.md`](../../../.cursor/skills/implement-lightrag-graph/SKILL.md)

## Scope lock

**In scope:** Pinned LightRAG adapters and storages, serialized graph lifecycle, precomputed keywords and evidence maps, resolver enforcement, entity curation, versioning, cleanup, inspection, fallback, and GraphRAG evaluation.

**Out of scope:** Final query-agent orchestration, optional-tool discovery, full API surface, frontend integration, and deployment.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] Pin and contract-test the exact LightRAG version, storage/schema behavior, structured identifier/source semantics, and precomputed-keyword bypass.
2. [ ] Initialize reviewed private PostgreSQL storages through controlled bootstrap and confine all LightRAG access to project adapters.
3. [ ] Implement concurrency-one insert/delete/rebuild with durable status, advisory locking, budgets, backlog ETA, and safe workspace states.
4. [ ] Build document, internal-chunk, entity/relation/statement, path-edge, and canonical-passage mappings before Graph Ready.
5. [ ] Implement bounded query-time resolver joins that recheck workspace, current version, deletion, graph eligibility, and authorization.
6. [ ] Implement approved entity alias/type/do-not-merge rules, invalidation, clean rebuild, and inactive suggestions.
7. [ ] Implement atomic version switching, ACL downgrade/deletion cleanup, quarantine, upgrade qualification, and disable-to-Hybrid behavior.
8. [ ] Prove per-language mapping thresholds, no hidden keyword call, no N-per-statement search, resolver survival/fallback, historical/ACL limitation signals, bounded inspection, and the seven-day rebuild envelope; hand Combined answer-quality proof to Phase 6.

## Cheap-model execution protocol

The eight checkboxes above are separate work packets. One model run may execute only one packet, in order. Before editing, the model must quote the active packet, state its positive and negative acceptance checks, inspect every target path plus the accepted Phase 1–4 exit records, and prove all prerequisites. This expanded plan does not satisfy those prerequisites.

Use [`docs/development/phase-05-graphrag-evidence.md`](../../../docs/development/phase-05-graphrag-evidence.md) as the canonical packet evidence and exit record. Packet 1 creates it and links it from `docs/README.md`. Every packet appends inspected migrations/schema/pins, dated primary-source links, exact commands and exit codes, artifact/config/dataset hashes, authorization/idempotency/failure/crash tests, measured mapping/latency/cost/resources, unresolved assumptions, rollback, and next-packet handoff.

Create and maintain:

- [`docs/graph/LIGHTRAG_CONTRACT.md`](../../../docs/graph/LIGHTRAG_CONTRACT.md) for exact package/commit/artifact hashes, transitive dependency constraints, public/private API shapes, generated schema fingerprint, source/ID semantics, callbacks, query/delete/status behavior, and rejected assumptions;
- [`docs/graph/WORKSPACE_LIFECYCLE.md`](../../../docs/graph/WORKSPACE_LIFECYCLE.md) for jobs, durable leases, advisory locks, workspace/pointer states, admission, budgets, crash recovery, cleanup, rebuild, upgrade, rollback, and disablement; and
- [`docs/graph/GRAPH_MAPPING_CONTRACT.md`](../../../docs/graph/GRAPH_MAPPING_CONTRACT.md) for canonical entity keys, application statement IDs, map methods, thresholds, per-language gates, resolver joins, repair jobs, survival, limitations, and citations.

As of 2026-08-12, the first released qualification candidate that provides the required plain-PostgreSQL backend is `lightrag-hku==1.5.6`, release commit `b33c6b0812cddf39206e48a9810112e51f025274`, with published wheel SHA-256 `81b8aa8b09c11e446f94b53dbbef8d6becd900a7a44685fca95ff59cf5c8e457`. Packet 1 must independently verify the registry/release signature or hashes, install by immutable lock/hash, and re-run every contract test. Do not float to `main`, a branch, or a newer release. A newer immutable release requires the same qualification plus an approved version change; `PGGraphStorage`/Apache AGE, Neo4j, or another engine is not an automatic fallback.

For LightRAG/PostgreSQL/Supabase/OpenAI:

1. inspect the exact locked source and generated schema rather than relying on current `main` documentation;
2. run real contract tests against local Supabase-compatible PostgreSQL using intended roles/search paths/connection mode;
3. record exact versions, artifact hashes, schema/config fingerprints, source URL/date, supported behavior, warnings, and limitations;
4. select operational bounds from signed targets plus representative measurement on supported hardware; and
5. stop rather than guessing a vendor table, method, identifier, workspace rule, callback, timeout, retry, migration, deletion, or query behavior.

The implementation must preserve these verified candidate caveats unless the final pin proves otherwise:

- `PGTableGraphStorage` is plain-table PostgreSQL; `PGGraphStorage` requires AGE and is forbidden.
- `initialize_storages()` is mandatory for the candidate and can create extensions/tables/indexes, alter/migrate legacy data, and continue after some warnings. It is not a harmless connection initializer or fail-fast migration guarantee.
- LightRAG uses schema-unqualified table names and a process-wide PostgreSQL pool. A private schema depends on a qualified controlled `search_path`; the first initialized vector configuration constrains later instances, and default pool/retry values must be overridden.
- The vendor schema-migration advisory lock serializes schema work only. It does not serialize document insert/delete/rebuild or application workspace switching.
- `ainsert()` accepts IDs/file paths/track ID but uses LightRAG fixed-token chunking. Its returned track ID is monitoring metadata, not idempotency or proof of terminal success.
- A caller-supplied document ID is stable, but internal chunk identity depends on text/chunker/tokenizer/config; entities are normalized names, relations are endpoint pairs rather than opaque relation IDs, and generated content hashes may be MD5. Application integrity uses canonical SHA-256 and application-owned IDs.
- `file_path` may be reduced to a basename and combined; never require verbatim internal URI round-trip. Pass a unique opaque non-secret basename token and map it through canonical document ID/application data.
- Entity/relation `source_id` may be a delimiter-joined scalar with bounded source retention. Pin the delimiter and source-limit policy; truncation or ambiguous parsing makes the object unavailable for evidence.
- Identical normalized content under different canonical IDs may be deduplicated or share graph contributions. Independent source attribution/deletion must pass a real contract test; otherwise stop for an approved input/provenance design rather than pretending independence.
- `aquery_data()` is the preferred structured lead API. Human-rendered `only_need_context` text, descriptions, relationship keywords, file paths, and query-local reference ordinals are not stable evidence identifiers or citations.
- Providing non-empty keyword lists bypasses keyword extraction in the candidate, but query embeddings, vector retrieval, and optional reranking still cost work. For graph `hybrid`, provide both `hl_keywords` and `ll_keywords` and spy on callbacks.
- LightRAG has no native contract for this plan's three hops, six paths, 12 candidates, resolver ACL, or hard operation deadline; application adapters/SQL/timeouts enforce them.
- Insert/delete span multiple persisted effects. Timeout/cancellation/connection loss is not rollback. Deletion is resumable/irreversible, and privacy cleanup must explicitly request LLM-cache deletion where the pin supports it.
- A second workspace isolates data but not global vendor schema migrations. Version upgrades qualify on a restored database/schema copy; an embedding/config rebuild may use a parallel workspace only after schema compatibility is already established.

LightRAG is an unauthenticated lead generator behind project protocols. Vendor descriptions, summaries, entity names, relation keywords, query context prose, scores, and references are never final evidence. The resolver exposes only canonical authorized current Supabase passages and application-owned relationship/path objects reconstructed from those passages.

The application uses two layers of writer serialization:

- one durable graph-writer lease/job row with heartbeat, expiry, reclaim, operation/idempotency key, expected workspace generation, and reconciliation status; and
- one dedicated session-level PostgreSQL advisory lock held for each LightRAG mutation/rebuild. Connection loss releases the lock, so the worker detects lease/connection loss, stops new effects, marks the workspace `quarantined`, and reconciles before retry. Do not hold a database transaction open across model extraction.

Short pointer/status transactions use a transaction advisory lock plus `SELECT ... FOR UPDATE` and compare-and-swap generation. LightRAG's own schema lock is never counted as either application lock.

The Phase 4 immutable launch holdout remains inaccessible to Phase 5 tuning. Mapping/extraction/entity/resolver parameters use Phase 4 development data and confirm on qualification data. Phase 5 exports frozen graph configuration and interfaces; Phase 6 performs the final Combined answer-quality holdout and the required 10-percentage-point improvement proof. Aggregate Phase 4 baseline reports do not authorize reading holdout labels.

At most two bounded repair attempts may target the same integration failure. Mocked LightRAG boundaries, ignored initialization warnings, runtime DDL, unreviewed private-table patching, `Graph Ready` after insertion alone, human-prose parsing, N-per-statement searches, hidden callbacks, unsafe cleanup, or unmeasured seven-day claims cannot close a packet.

## Work packet implementation contracts

### Packet 1 — immutable LightRAG pin and complete contract qualification

#### Packet 1 preconditions

- Phases 1–4 are complete and accepted; the Phase 4 continue-to-Phase-5 decision is explicitly approved.
- The monorepo, exact-lock/hash tooling, local Supabase-compatible PostgreSQL, shared model/embedding/budget gateway, Phase 4 profile/Reranker/fixtures, docs index, and repository verification commands exist.
- Signed governance permits the synthetic qualification content and any live provider callbacks.

#### Packet 1 allowed outputs

- Exact dependency/artifact lock updates, LightRAG contract document, adapter protocols/qualification harness, redacted schema/API fixtures, Phase 5 evidence, and an ADR only if the candidate is rejected/disabled.
- `GraphRetriever`/`GraphIndexer` protocols may be defined; production storage/mutation wiring waits for later packets.

#### Packet 1 forbidden outputs

- Floating Git/main/newest dependencies, AGE/`PGGraphStorage`, direct application dependency on LightRAG classes, production indexing, invented vendor tables, parsing human context prose, or weakening a failed contract.
- Treating source text hashes, track IDs, file paths, reference ordinals, normalized entity names, or endpoint pairs as application integrity/idempotency/citation IDs.

#### Packet 1 ordered actions

1. Inspect the repository lock, Python/PostgreSQL/pgvector/OpenAI/asyncpg constraints, selected release, package metadata, wheel/sdist/commit hashes, license, advisories, and primary source.
2. Install the exact artifact by hash in the approved workspace and record its full dependency resolution. Reject incompatible transitive ranges rather than overriding blindly.
3. Assert import and round-trip contracts for `PGTableGraphStorage`, `PGVectorStorage`, `PGKVStorage`, `PGDocStatusStorage`, `LightRAG`, `QueryParam`, initialization/finalization, insertion, status, structured query, and document deletion APIs.
4. Bootstrap an empty disposable private schema and capture tables/columns/types/defaults/indexes/constraints/extensions/functions/migration fingerprints, warnings, and attempted DDL. Compare a second initialization and fail on unexplained drift/warnings.
5. Prove workspace isolation across graph, KV, status, cache, and model/dimension-suffixed vector storage; test constructor workspace versus environment override and reject unexpected collapse.
6. Round-trip explicit canonical document IDs and unique opaque basename source tokens. Record actual path normalization and source delimiter/limit behavior.
7. Test duplicate ID, duplicate basename, identical content/different IDs, changed chunker/tokenizer/text/config, and source-count-limit behavior. Independent deletion/attribution is a hard gate.
8. Instrument every LightRAG LLM/embedding/rerank callback. Supply both precomputed keyword lists and prove zero keyword/query-answer callbacks while accounting for expected embedding/optional-rerank calls.
9. Validate exact `aquery_data()` structure. Accept only qualified machine fields such as chunk ID, entity name, relation endpoints, parsed source IDs, and mode/keyword metadata. Reject descriptions/keywords/file paths/reference ordinals/rendered context as stable evidence.
10. Exercise `ainsert` enqueue/processing/status, timeout/cancellation/retry, and `adelete_by_doc_id` result/recovery/cache options. Track ID never acts as idempotency.
11. Prove adapter-owned token/candidate/hop/path/deadline limits can wrap the pin, and that all provider HTTP attempts/cost are bounded/accounted by one retry layer.
12. Record every pass/fail and either approve the immutable pin or set GraphRAG disabled with a blocker/ADR. Do not partially accept.

#### Packet 1 acceptance checks

- Exact artifact/hash/source and all required public APIs qualify against real PostgreSQL; PGTable needs no AGE.
- Schema/bootstrap, workspace, pool/finalization, ID/source/duplicate, callback, structured query, status, cancellation, deletion, and bounds tests pass without parsing prose or relying on undocumented fields.
- Both keyword lists produce zero keyword-extraction and answer-generation calls; all remaining calls pass through the shared gateway.
- Identical-content sources remain independently attributable/deletable, or GraphRAG is disabled pending approved design.

#### Packet 1 negative tests

- Hash/version mismatch, missing class/API, hidden callback, runtime-prose parser, source-token ambiguity/truncation, duplicate-source collapse, schema warning/drift, unbounded provider retry, unsupported deletion result, or main-only behavior fails qualification.

#### Packet 1 stop routes

- Any prerequisite is absent, released PGTable artifact cannot satisfy private PostgreSQL/stable structured provenance/precomputed keyword contracts, or a safe workaround changes data/security/cost semantics without approval.

#### Packet 1 required evidence

- Lockfile/artifact/commit/license/advisory record, primary-source links, dependency tree, API matrix, schema fingerprints/diffs/warnings, workspace/duplicate/source/callback/query/status/delete results, provider attempts/cost, rejected assumptions, disable/ADR decision, and exact commands.

### Packet 2 — controlled private storage bootstrap and adapter-only access

#### Packet 2 preconditions

- Packet 1 approves the exact pin; Phase 2 private schemas/application mapping tables/roles/connection budgets/workload controls and protected migration procedure are accepted.
- Disposable bootstrap and intended runtime credentials are available locally; no user/browser credential has vendor-table access.

#### Packet 2 allowed outputs

- Reviewed bootstrap/migration procedure, vendor schema fingerprint/manifest, private-schema grants/search-path configuration, adapter factory, bounded pool/finalization lifecycle, import-boundary tests, and docs.
- Additive application-owned migrations may record workspace/pointer/lease/config/schema fingerprints; vendor DDL is captured, not manually reimplemented from memory.

#### Packet 2 forbidden outputs

- `initialize_storages()` on normal API/worker health/startup with migration credentials, DDL/admin privileges in runtime containers, direct LightRAG imports outside the core adapter, vendor tables in exposed schemas, `PUBLIC`/`anon`/`authenticated`/browser/service-role access, or hand-edited vendor rows.
- Treating successful initialization as proof when warnings/postconditions show incomplete migration.

#### Packet 2 ordered actions

1. Inspect Phase 2 schemas/roles/search paths/pool caps/timeouts and the packet-1 vendor manifest before changing migrations.
2. Create an environment-scoped protected bootstrap job that sets the exact private `search_path`, validates database/extension/version preconditions, runs initialization, captures every warning/DDL/postcondition, then finalizes connections.
3. Verify all vendor objects live only in the intended private schema and match the approved fingerprint. Fail on objects in `public`, unexpected extensions, legacy migrations, owner drift, or unqualified resolution outside the controlled path.
4. Revoke schema/object/default privileges from `PUBLIC`, `anon`, `authenticated`, service-role-facing paths, and unrelated roles. Grant the narrow bootstrap role DDL and dedicated graph runtime role only qualified DML/sequence/function access needed by contract.
5. Test whether the exact runtime role can construct/use/finalize the adapter against an already-bootstrapped schema without attempted DDL, migration warning, or schema mutation. If the library requires DDL rights at runtime, reject the integration or obtain approval for an upstream/reviewed adapter strategy.
6. Configure direct/Supavisor-session endpoint, SSL/search path, statement cache compatibility, pool/retry/timeout limits, and query tags. Override vendor defaults so total Phase 2 connection budgets remain below the signed ceiling.
7. Prove the process-wide pool's first vector model/dimension configuration is deterministic and compatible across the only allowed instances; incompatible workspace/model instances run in isolated processes during qualification/rebuild.
8. Implement core adapter factory/lifecycle and ensure `finalize_storages()` releases references on shutdown/cancellation.
9. Enforce import boundaries so application/agents/workers use only `GraphRetriever`/`GraphIndexer`; migration/bootstrap is the only separate vendor entry point.
10. Run fresh bootstrap, repeat bootstrap, runtime startup, cross-role, exposed-schema, pool exhaustion/leak, cancellation, and schema-drift tests; append evidence.

#### Packet 2 acceptance checks

- Fresh and repeat bootstrap yield the reviewed private schema fingerprint with no ignored warning/postcondition failure.
- Runtime role performs qualified DML/query only, cannot DDL/migrate, and can initialize its runtime objects without schema drift; all browser/user/service-role-facing paths deny vendor tables.
- Pool/search path/model/dimension/finalization behavior stays inside connection/workload budgets.
- Repository import scan proves vendor classes are confined to the adapter/bootstrap modules.

#### Packet 2 negative tests

- Wrong search path, environment workspace override, runtime DDL, public object, bootstrap credential in runtime, direct user read, incompatible vector config, pool leak, initialization warning, unfinalized shutdown, or forbidden import fails.

#### Packet 2 stop routes

- Phase 2 role/connection contracts are missing, runtime least privilege cannot coexist with the pin, generated schema cannot be isolated/reproduced, or connection caps exceed the signed tier.

#### Packet 2 required evidence

- Bootstrap runbook/logs, before/after schema fingerprints and diffs, warning/postcondition report, grants/default privileges/search-path tests, runtime DDL denial, role matrix, pool/finalization metrics, import scan, rollback, and exact commands.

### Packet 3 — durable single writer, insertion, budgets, states, and backlog ETA

#### Packet 3 preconditions

- Packets 1–2 pass; Phase 3 `lightrag_index_jobs` handoff/lease/idempotency, graph eligibility, budget/usage, document-version, and deletion/ACL job contracts are accepted.
- Phase 2 application workspace/pointer/lease tables and maintenance reserve exist; Phase 4 frozen profile/model/quality targets are available.

#### Packet 3 allowed outputs

- `GraphIndexer` implementation, durable graph-writer lease and reconciliation, application advisory lock wrapper, insertion/status polling, callback gateway integration, admission/budgets, workspace states, backlog/throughput/ETA/cost service, and tests/docs.
- No query resolver/mapping success until packets 4–5.

#### Packet 3 forbidden outputs

- Concurrent LightRAG mutations, vendor schema lock counted as writer lock, transaction held across model calls, process-memory/Valkey writer authority, track ID as idempotency, `Graph Ready` after vendor processing only, default callbacks/retries/pools, or normal jobs consuming maintenance reserve.

#### Packet 3 state and job invariants

- Durable application states are `building`, `active`, `updating`, `filtered_dirty`, `quarantined`, `disabled`, and `retired`; only one verified workspace generation is active.
- A normal insert changes active workspace to `updating`; Combined/inspection are unavailable and Phase 6 sees Hybrid fallback. Insert success returns `active` only after packet-4 maps verify.
- Targeted delete/ACL success yields `filtered_dirty`; failure/interruption/lock loss/unverifiable status yields `quarantined`.
- Rebuild occurs in a separate `building` workspace; only a short verified pointer transaction changes it to `active`.
- Each operation has stable idempotency key, source/version/config hash, expected generation, lease owner/token/expiry, vendor track/status, reservation, attempt, heartbeat, and terminal/reconciliation state.

#### Packet 3 ordered actions

1. Define the application state diagram, job types/priorities, writer lease, lock key derivation, recovery matrix, admission, callback/retry, and metrics in `WORKSPACE_LIFECYCLE.md`.
2. Claim/reclaim graph jobs with the Phase 3 lease discipline. Acquire the dedicated session advisory lock on a bounded graph connection; verify lock/lease before each new vendor/provider/application effect.
3. Do not hold a transaction across extraction. On connection/advisory-lock or durable-lease loss, cancel bounded work, prevent new writes, persist `quarantined`, and schedule reconciliation.
4. Revalidate current company-visible graph eligibility, canonical hash, `Hybrid Ready`, governance, active pin/config, and expected workspace generation before insertion.
5. Pass normalized version text to exact qualified `ainsert` with `ids=[document_version_id]`, unique opaque source token, and fresh monitoring track ID. Pin fixed chunker/tokenizer/size/overlap/config and record them.
6. Route extraction, embedding, cache, and optional rerank calls through the shared gateway with per-role durable reservations, exact model snapshots, timeouts, one retry layer, provider response/usage ledger, and true-up. Timeout-after-send remains possibly billed.
7. Poll qualified vendor status APIs until terminal success/failure/deadline; vendor `PROCESSED` only authorizes packet-4 mapping and never `Graph Ready`.
8. Reconcile duplicate ID/basename/content, partial status, callback/cache failure, cancellation, worker crash, and replay without duplicate canonical source-map readiness.
9. Enforce normal daily ingestion budget/per-file estimate/default 100 pending; pause new graph admission when pending handoffs exceed 50 while Hybrid ingestion continues. Maintenance delete/ACL/rebuild/upgrade jobs use and outrank the separate reserve.
10. Compute rolling documents/hour only from mapping-verified `Graph Ready`, backlog count/oldest age, ETA with confidence/insufficient-sample state, attempted/settled cost, and remaining estimated cost. Bulk onboarding requires owner-approved window/reservation.
11. Test two workers, lock/lease loss, crash schedules, budget/backpressure, status reconciliation, and exact metrics; append evidence.

#### Packet 3 acceptance checks

- Competing workers never mutate simultaneously; the durable lease plus application advisory lock—not vendor schema lock—enforces one writer.
- Replay/crash/cancel converges to one logical source operation or quarantines visibly; no partial vendor success becomes Graph Ready.
- Every model/embedding call is reserved/accounted and bounded; normal/maintenance budgets never mix.
- Queue/backlog/ETA/cost metrics are derived from durable rows and mapping-verified completions.

#### Packet 3 crash tests

- Before/after lease claim, advisory lock, `ainsert` enqueue, provider response, cache write, chunk write, extraction merge, vendor terminal status, mapping start, application status write, lease/connection loss, and worker shutdown.

#### Packet 3 stop routes

- Phase 3 jobs/budgets are missing, independent duplicate-source semantics failed packet 1, writer serialization/reconciliation cannot be proven, or provider attempts/cost cannot be bounded.

#### Packet 3 required evidence

- State/job/lock diagrams, schema/lease rows, concurrency/crash traces, vendor status transitions, callback/reservation/usage ledgers, duplicate/replay reconciliation, backpressure/budget tests, throughput/ETA/cost calculations, and exact commands.

### Packet 4 — canonical graph evidence mapping and Graph Ready

#### Packet 4 preconditions

- Packets 1–3 pass; vendor terminal processing is verified for representative `Graph Pending` versions.
- Phase 3 canonical chunks/locators/hash/version and application map/repair schemas exist.
- Phase 4 scoped per-document Hybrid RPC, OpenAI-only `Reranker`, development/qualification relation labels, entity-key policy, and signed language gates are frozen.

#### Packet 4 allowed outputs

- `lightrag_source_map`, `lightrag_chunk_map`, `graph_evidence_map`, application entity/statement/path-edge records, bounded mapping/repair jobs, per-language telemetry, and `Graph Ready` transition.
- Adapter-owned qualified reads of the exact pinned storage structures; no browser/public/vendor-prose interface.

#### Packet 4 forbidden outputs

- `lightrag_source_map` alone as evidence, parsing rendered context, treating file path/reference ordinal/description/keyword as stable ID, assuming a native predicate/relation ID, cross-document/version support, N Hybrid/model calls per relation, query-time support search, or aggregate-only language gates.

#### Packet 4 mapping identities

- Canonical source identity is the application `document_version_id` plus SHA-256/config generation, not vendor hash/path.
- LightRAG internal chunk key is qualified only with its workspace/config/source link and is never a cross-version application ID.
- Application canonical entity key comes from versioned type/alias/do-not-merge rules; unresolved/ambiguous entities remain separate/unavailable.
- `graph_statement_id` is a stable application hash of workspace graph-pipeline version, canonical subject key, canonical object key, and a versioned normalized relation-label key derived from qualified structured relation fields. It does not claim that generated relation description/keywords are a canonical predicate.
- Path-edge IDs derive from ordered application statement IDs plus direction/version; native prose is never embedded in an evidence ID.

#### Packet 4 ordered actions

1. Verify terminal vendor status and exact canonical source token/document ID. Enumerate internal chunks and source joins only through adapter queries qualified in packet 1, including document-chunk and entity/relation-source association structures.
2. Parse source-ID lists only with the pinned delimiter/escaping/source-limit contract. Any truncated, malformed, ambiguous, cross-workspace, or cross-version source set makes the object unavailable and creates repair/quarantine diagnostics.
3. Map each internal chunk to its canonical version, then try versioned normalized-text SHA-256, exact span, and bounded overlap matching to canonical chunks. Preserve method, source/target hashes, spans, config/version, score, and provenance.
4. Batch all unresolved internal chunks and relation leads for one document into one bounded scoped Hybrid RPC restricted to that document version. Never call Hybrid per statement/chunk.
5. Apply one bounded Phase 4 support rerank to the document batch. Validate supplied canonical IDs/set equality and record budget/usage; no local model.
6. Derive application entity keys, statement IDs, and path-edge IDs. Store accepted chunk/entity/statement/path support to one or more canonical chunks with method/score/version/provenance.
7. Calibrate on development and confirm on qualification data. Start support at `>=0.80`; require every queryable relation/path edge to have accepted support, overall mapping coverage at least 90%, and signed English/Arabic/mixed extraction/mapping gates. Provisional Arabic/mixed mapping coverage is at least 85%.
8. Record numerator/denominator/exclusions separately by language, document, object type, method, source-count truncation, and failure reason. English-heavy aggregate success cannot hide another language failure.
9. In one application transaction, upsert idempotent mappings/source readiness, verify canonical current/eligibility/config, and mark `Graph Ready` only when every gate passes. Lower/unmapped objects remain unavailable and repairable; a document missing its language gate remains `Graph Pending`/failed per policy.
10. Add repair jobs keyed by workspace/object/map/config generation. Repair never performs query-time ad hoc retrieval and cannot silently lower thresholds.
11. Test replay, stale/cross-version maps, unsupported relation, duplicate-content source, ambiguous entity, language failure, source truncation, and mapping budget; append evidence.

#### Packet 4 acceptance checks

- Every Graph Ready document has complete source/chunk/entity/statement/path map rows with accepted canonical passage support, overall and signed per-language gates, and reproducible config/provenance.
- One document causes at most one scoped Hybrid mapping retrieval and one bounded support rerank batch, not N calls.
- Unmapped/stale/ambiguous/truncated/below-threshold objects are unavailable plus repair diagnostics and cannot contribute to Graph Ready/query.
- Replay yields stable application IDs and no duplicate mapping/source readiness.

#### Packet 4 negative tests

- Vendor `PROCESSED` only, aggregate-pass/language-fail, unsupported relation, human prose/reference ID citation, native description as predicate, cross-version support, source cap loss, threshold bypass, or query-time repair search fails.

#### Packet 4 stop routes

- Structured vendor provenance cannot be queried safely, Phase 4 mapping dependencies/labels are absent, duplicate source attribution is ambiguous, or signed per-language/extraction/mapping gates cannot pass.

#### Packet 4 required evidence

- Mapping identity/schema/version docs, qualified storage query fingerprints, per-method rows, one-batch call counts/cost, threshold calibration/qualification by language/type, Graph Ready transaction proof, repair/stale/replay/source-limit tests, and exact commands.

### Packet 5 — structured graph retrieval, authoritative resolver, survival, and inspection

#### Packet 5 preconditions

- Packet 4 Graph Ready maps exist; Phase 4 frozen `QueryProfile` provides both keyword lists and authorization/canonical resolver interfaces.
- Active workspace/pointer, signed query/inspection deadlines, mapping/support versions, and real ACL/current/deletion fixtures are available.

#### Packet 5 allowed outputs

- `GraphRetriever` local/graph-hybrid/global-steering adapter, structured `aquery_data()` parsing, application-owned candidate/path expansion, canonical resolver joins, survival/partial-readiness/limitation signals, bounded inspection backend, and tests/docs.
- Phase 6 later orchestrates routes/answers/streams; Phase 5 may expose deterministic retrieval result interfaces.

#### Packet 5 forbidden outputs

- `aquery(... only_need_context)` rendered prose as data, native descriptions/summaries/keywords/file paths/references as evidence, vendor answer generation, `naive`/`mix` as application Hybrid, hidden keyword/query callback, native rerank without qualification, per-statement Hybrid search, or unauthorized/restricted counts.

#### Packet 5 ordered actions

1. Revalidate active workspace state/generation, current-only graph policy, profile/config versions, caller authorization snapshot, and remaining deadline before vendor query.
2. Use `aquery_data()` with `only_need_context` semantics, no streaming/answer generation, both non-empty precomputed keyword lists, bounded `top_k`/`chunk_top_k`/entity/relation/total tokens, and explicit local or graph-hybrid mode. Use `enable_rerank=false` unless a separate approved qualification proves mapped-ID preservation/cost and includes it in budgets.
3. Instrument callbacks and assert zero keyword/query-answer calls. Bound expected embedding/vector/optional-rerank work with outer async timeout, database statement timeouts, and cancellation cleanup.
4. Parse only the qualified structured fields. Convert entity names/relation endpoint pairs/source chunk IDs into application candidate IDs through the active workspace maps; ignore human descriptions/keywords/path/file/reference ordinals for evidence.
5. Enforce application maximum 12 graph candidates, three hops, six paths, stable tie-breaks, token/row/deadline bounds. Native engine settings do not replace these controls.
6. Resolve all required entities/statements/path edges through `graph_evidence_map`/`lightrag_chunk_map`, then batch recheck active workspace, source eligibility, transactional current pointer, deletion, ACL, support threshold, mapping/config generation, and canonical passage existence.
7. Drop the whole relationship/path candidate if any required mapping/support is missing, stale, unauthorized, below threshold, or no longer survives. Enqueue one bounded repair job; never run ad hoc Hybrid/model search.
8. Fetch canonical Supabase passages/locators directly and return only supported application IDs, bounded paths/relationships, canonical chunk IDs, confidence/support, limitations, and diagnostics. User-facing relationship prose is reconstructed later from passages.
9. Record `graph_survival_ratio=supported_resolved/returned_graph_candidates`, null when none. Below 0.50 emits requested Combined/effective Hybrid and `graph_survival_below_threshold`; rolling below 0.80 over 20 Combined queries/source-map spikes alerts.
10. Detect relevant authorized Hybrid hits from company-visible versions not Graph Ready and emit bounded recent-document partial-readiness count. For authorized ACL-restricted graph-ineligible hits emit the authorized-only blindness count/message; unauthorized users receive no count/name/existence.
11. Emit `temporal_graph_limitation` for explicit `as_of` or historical relationship/multi-hop; never query superseded paths.
12. Treat global results as at most three topic/entity steering expansions that re-enter canonical Hybrid in Phase 6; global output is never evidence.
13. Implement graph inspection through the identical resolver with SQL-level depth three, 200 rows, three-second statement timeout, 10-second end-to-end deadline, role/scope controls, and no native prose.
14. Test stale/ACL/deletion/version races, survival thresholds, partial readiness, historical, empty graph, timeout/cancel, global steering, no hidden call, and inspection limits; append evidence.

#### Packet 5 acceptance checks

- Resolver returns only authorized current canonical IDs/locators and application relationship/path objects; every native lead either survives all checks or is dropped wholly.
- Candidate/path/hop/token/row/time limits are application-enforced, deterministic, and tested independently of vendor defaults.
- Survival, partial readiness, authorized-only ACL blindness, historical limitation, outage/quarantine, and global steering emit exact typed signals without information leakage.
- Query-time counters prove zero per-statement support searches and zero hidden keyword/answer model calls.

#### Packet 5 negative tests

- Prose/reference/path as citation, stale map, current-pointer race, deleted/ACL-restricted source, unauthorized count disclosure, native over-limit result, hidden callback, query-time repair search, historical path, inspection bypass, timeout leak, or low survival labeled Combined fails.

#### Packet 5 stop routes

- Real authoritative resolver/ACL boundary cannot be exercised, structured output shape drifts, application bounds cannot contain vendor work, or any native prose is required to establish evidence.

#### Packet 5 required evidence

- Query/config/callback traces, structured-field parser contract, candidate/path resolver rows, authorization/race negatives, survival/alert windows, limitation/blindness payloads, no-N-search counters, inspection plans/timeouts, global steering leads, cancellation cleanup, and exact commands.

### Packet 6 — entity curation, extraction policy, invalidation, and rebuild scheduling

#### Packet 6 preconditions

- Packets 1–5 pass; Phase 2 `graph_entity_rules` schema/admin authorization/audit exists; Phase 4 development/qualification entity collision labels are available.
- Extraction model/prompt/entity types/languages/JSON mode/gleaning/record caps are pinned and budgeted.

#### Packet 6 allowed outputs

- Owner/admin entity-rule service, approved aliases/display labels/types/do-not-merge rules, inactive suggestions, versioned canonical-key/extraction policy, invalidation/repair/rebuild scheduling, and tests/docs.
- Rule application occurs at clean rebuild; no direct unsafe vendor-graph mutation.

#### Packet 6 forbidden outputs

- Auto-approving model/feedback suggestions, copying LightRAG native names into Hybrid aliases, silent merge/split, user-editable metadata authorization, in-place mutation claiming complete correction, or using entity rules to make ACL-restricted content graph eligible.

#### Packet 6 ordered actions

1. Define versioned canonical entity-key normalization, allowed entity types/languages, alias scope/effective dates, display labels, directed/symmetric relation-label policy, and do-not-merge precedence.
2. Require owner/admin authorization, MFA/reauth where inherited, optimistic versioning, reason/source, audit, and conflict/cycle/duplicate/cross-type validation for active rules.
3. Store feedback/model candidates as inactive suggestions with provenance/confidence; no suggestion affects extraction/mapping/retrieval until approved.
4. Apply rules to the application extraction prompt/canonicalization before a clean parallel rebuild. Preserve distinct keys for collisions such as `PROJECT::ATLAS` and `PRODUCT::ATLAS`.
5. Rule changes bump entity/extraction/graph-pipeline versions, immediately invalidate affected application mappings/query availability, enqueue bounded repair plus clean rebuild, and retain prior workspace active where safe until verified switch.
6. Never seed Phase 4 Hybrid aliases from native LightRAG outputs automatically. A separate SME owner/admin import remains required.
7. Test aliases, multilingual variants, homonyms, acronyms, type collisions, do-not-merge, suggested inactive, approval/revocation, concurrent edits, invalidation, and rebuild handoff.
8. Append rule/prompt/model/budget/authorization/invalidation evidence.

#### Packet 6 acceptance checks

- Approved rules deterministically affect canonical keys/extraction on rebuild; ambiguous/do-not-merge entities never silently merge.
- Suggested/revoked rules cannot affect active graph results; changes invalidate mappings and schedule versioned clean rebuild.
- Rule CRUD is authorized/audited and cannot broaden graph eligibility or Hybrid aliases.

#### Packet 6 negative tests

- Member/viewer mutation, stale concurrent update, cross-type alias, cycle, auto-approval, inactive suggestion use, direct vendor patch, native-to-Hybrid alias copy, or rule change without invalidation/rebuild fails.

#### Packet 6 stop routes

- Admin/audit/rule schema is missing, extraction policy cannot honor rules deterministically, or corrections require unsafe in-place vendor surgery.

#### Packet 6 required evidence

- Rule/canonical-key schema and versions, authorization/audit tests, multilingual/collision fixture outputs, prompt/model/config hashes, inactive suggestion proof, invalidation/map suppression/rebuild jobs, and exact commands.

### Packet 7 — atomic version switching, deletion/ACL cleanup, upgrade, rollback, and disablement

#### Packet 7 preconditions

- Packets 1–6 pass; Phase 3 replacement/deletion/ACL/BM25 handoffs and retention/tombstone semantics are accepted.
- Separate build workspace, maintenance reserve, restored database/schema copy for upgrade tests, snapshot/restore runbook, and pointer generation schema exist.

#### Packet 7 allowed outputs

- Version/pointer switch transaction, targeted document deletion with cache cleanup, ACL downgrade reconciliation, clean rebuild/switch, tombstones, quarantine/disable, version/embedding upgrade qualification, rollback commands/runbooks, and tests.

#### Packet 7 forbidden outputs

- In-place mixed embeddings/configs, testing vendor schema upgrade only in a second workspace, long pointer transaction across model/rebuild work, destructive entity/relation delete for ordinary document lifecycle, re-enabling canonical deleted data, ACL expansion auto-indexing, or continuing Combined/inspection after unverifiable cleanup.

#### Packet 7 version switch actions

1. Consume Phase 3 new canonical/vector/term/BM25 version with `is_current=false` and graph retrieval eligibility off.
2. Insert into the target workspace and build all mappings with the exact frozen graph configuration; verify canonical/BM25/graph/language/survival/cost gates.
3. Begin a short application transaction, acquire transaction advisory lock, lock pointer/source rows `FOR UPDATE`, compare expected generation/current version/workspace, and recheck deletion/ACL.
4. Atomically flip `documents.current_version_id`, old/new Hybrid visibility, BM25 visibility generation, graph source-map eligibility, active workspace/source generation as applicable, and audit. Commit exposes exactly one authoritative version.
5. After commit, serialized worker deletes old vendor document and schedules old BM25/map/graph cleanup. Failure leaves old derived rows filtered and retryable.

#### Packet 7 deletion and ACL actions

1. Trust Phase 3's same-transaction canonical exclusion/source-map ineligibility as immediate authority and recheck it before mutation.
2. Set workspace `updating`; under the single writer call the qualified document delete with privacy cache deletion enabled, persist/retry every vendor recovery phase/result, then verify full-doc/chunk/vector/status/cache/source association removal.
3. Verify shared entities/relations retain only surviving source support and deleted/restricted text cannot survive the application resolver. Do not rely on regenerated vendor prose.
4. Successful targeted delete/ACL removal sets `filtered_dirty`; create/continue tombstone, verify target cleanup within 24 hours, and batch a clean workspace rebuild from only surviving current graph-eligible versions within seven days.
5. Any not-allowed/fail/ambiguous/timeout/connection loss, missing recovery evidence, resolver verification failure, or source residue immediately sets `quarantined`, emits `Deletion cleanup failed`, and disables Combined/inspection while canonical/Storage retention continues.
6. ACL expansion never auto-indexes; owner/admin explicitly approves a new versioned graph job.

#### Packet 7 upgrade and rollback actions

1. Embedding/model/chunker/extraction/entity/mapping change builds a parallel versioned workspace with one homogeneous config and switches only after full verification.
2. LightRAG package/schema upgrade restores a production-sized snapshot into a separate database/schema environment, runs protected bootstrap/migrations, compares schema/data postconditions, then performs complete rebuild/query/delete/rollback qualification. A second workspace in the same schema is insufficient.
3. Snapshot/restore is the vendor schema rollback boundary; workspace pointer rollback covers only application data/config compatible with the current schema.
4. Two consecutive failed upgrade qualifications or survival alerts persisting seven days triggers replacement/disable review through `GraphRetriever`; no silent provider substitution.
5. Disabled/quarantined graph makes automatic routes Hybrid-only and inspection unavailable while preserving repair/admin evidence.

#### Packet 7 acceptance checks

- Pointer crashes expose old or new generation, never mixed/zero current versions; post-flip cleanup is retryable and filtered.
- Deletion/ACL exclusion is immediate at resolver, targeted deletion/cache cleanup verifies within 24 hours, and clean rebuild from surviving sources verifies within seven days.
- Shared-entity and identical-content fixtures prove no deleted/restricted evidence survives canonical resolution/inspection.
- Upgrade qualification uses a restored isolated copy; failed migration/rebuild can restore/disable safely; embedding configs never mix.

#### Packet 7 negative tests

- Crash before/during/after pointer commit, stale generation, concurrent delete, delete result `not_found`/`not_allowed`/`fail`, recovery-phase crash, cache residue, source residue, shared-entity contamination, ACL race, unfunded rebuild, schema warning/drift, incompatible rollback, or automatic ACL expansion all fail safe.

#### Packet 7 stop routes

- Immediate source-map exclusion, privacy deletion/recovery evidence, isolated upgrade environment, snapshot restore, maintenance reserve, or authoritative resolver verification is unavailable.

#### Packet 7 required evidence

- Pointer transaction/lock/generation traces, crash matrix, delete recovery/cache/source/shared-entity results, tombstone/SLA/rebuild rows, ACL blindness tests, upgrade schema/data diff, snapshot restore/rollback, disable triggers, budget/cost, and exact commands.

### Packet 8 — graph evaluation, envelope proof, scaling options, and Phase 6 handoff

#### Packet 8 preconditions

- Packets 1–7 pass; graph configuration/pin/schema/mapping/rules/resolver/workspace generation is frozen.
- Phase 4 development/qualification graph labels are available; immutable launch holdout labels remain inaccessible to Phase 5.
- Launch hardware, graph maintenance reserve owner, supported graph envelope, and Phase 6 interface owner are available.

#### Packet 8 allowed outputs

- Phase 5 development/qualification evaluations, throughput/rebuild/delete/inspection benchmarks, failure/ACL/temporal fixtures, `docs/graph/SCALING_OPTIONS.md`, completed evidence, and stable Phase 6 handoff.
- No final Combined answer-quality claim or query-agent implementation.

#### Packet 8 ordered actions

1. Freeze and record LightRAG artifact/schema, PostgreSQL/pgvector, model/embedding/chunker/tokenizer/prompts/entity rules, mapping/resolver thresholds, workspace generation, source delimiter/limits, adapter bounds, code, and dataset hashes.
2. Evaluate extraction precision/recall, mapping coverage/support, source truncation, and graph survival separately for English, Arabic, and mixed documents plus entity/relation/path type. Every returned relation remains support-mapped.
3. Prove both supplied keyword lists produce zero keyword/query-answer calls; record embedding/rerank/model-call/cost counts. Prove mapping uses one batched scoped Hybrid retrieval/rerank per document and query resolver uses zero per-statement searches.
4. Exercise entity collisions/aliases/do-not-merge, global steering, mapping repair, low survival, partial readiness, current-only historical limitation, authorized ACL blindness versus unauthorized silence, version overlap, deletion/ACL/shared-source cleanup, filtered/quarantined/disabled states, and upgrade rollback.
5. Benchmark graph local/hybrid lead retrieval and inspection under candidate/path/hop/token/depth/row/deadline bounds. Phase 6 later measures Combined answer/stream deadlines.
6. Measure concurrency-one documents/hour through mapping-verified Graph Ready, graph source chunks/hour, queue age, cost/document, resource peaks, clean rebuild duration/cost, targeted deletion time, and snapshot restore on selected hardware.
7. Extrapolate the initial 2,000-current-document/200,000-source-chunk envelope from measured lower/representative/full runs with uncertainty and bottlenecks. Require full clean rebuild and mapping within seven days or reduce the advertised envelope/resize/approve an ADR.
8. Set graph maintenance reserve to at least `max(USD 800, 4 × measured full-rebuild cost)`. If unavailable, canonical deletion continues but graph stays quarantined/disabled until funded cleanup succeeds.
9. Prove targeted deletion/resolver verification within 24 hours and dirty consolidation within seven days. Failures quarantine and block graph launch.
10. Write `SCALING_OPTIONS.md` as options only: domain/security-boundary sharding, dedicated managed LightRAG PostgreSQL behind protocols, qualified incremental compaction/rebuild, and Hybrid-only disablement. Record trigger/decision inputs without implementing them.
11. Export Phase 6 interfaces/fixtures: `GraphRetriever` results, local/hybrid/global steering, precomputed keyword contract, application entity/statement/path IDs, survival/fallback, partial readiness, ACL blindness, temporal limitation, graph state/availability, citations/repair metadata, and labeled relationship/multi-hop development/qualification cases.
12. State explicitly that Phase 5 proves graph infrastructure/mapping/resolver/envelope only. Phase 6 owns Combined fusion, verifier/citations in final answers, final holdout, and the at-least-10-point relationship/multi-hop gain.
13. Run all repository-defined lint/type/test/migration/build/docs/Mermaid/container/integration/security/plan-integrity commands; map every `Done when` clause to evidence and request explicit user acceptance.

#### Packet 8 acceptance checks

- Signed overall/per-language extraction/mapping/survival gates pass on qualification data; no holdout leakage occurs.
- Hidden keyword/query-answer call count and query-time per-statement Hybrid/model count are zero; all expected calls/costs are bounded/accounted.
- Resolver/inspection returns no unauthorized/stale/deleted/superseded/native-prose evidence under every fixture and obeys all bounds.
- Measured throughput/rebuild/cost/SLA proves the signed envelope/reserve or the supported envelope is explicitly reduced before graph launch.
- Phase 6 receives frozen interfaces/fixtures and an explicit no-claim for Combined answer quality; user acceptance precedes status change.

#### Packet 8 negative tests

- Aggregate-only language pass, unmapped returned relation, hidden callback, N-search, unauthorized ACL count, historical path, inspection overrun, subjective throughput extrapolation, unfunded reserve, unexecuted Phase 6 label counted pass, or holdout access fails.

#### Packet 8 stop routes

- Any real boundary/SLA/envelope/gate fails after bounded repair, required reserve/owner is unavailable, or only a fake/skipped/holdout-leaking result could pass.

#### Packet 8 required evidence

- Frozen manifest, per-language/type metrics, callback/search counters, resolver/ACL/temporal/state/upgrade fixtures, full performance/resource/cost/SLA/envelope calculations, reserve approval, scaling options, Phase 6 handoff checklist, complete command log, deviations/rollback, and explicit user acceptance.

## Cross-packet invariants and ownership

- Phase 3 owns graph eligibility, Graph Pending handoff, canonical/BM25 readiness, and immediate deletion/ACL authority; Phase 5 never reclassifies restricted content as graph eligible.
- Phase 4 owns QueryProfile, Hybrid/Reranker mapping dependencies, frozen retrieval config, and labeled data; Phase 5 does not tune from launch holdout.
- Phase 5 owns the LightRAG adapter, vendor bootstrap review, single writer, application maps/IDs, Graph Ready, resolver, inspection backend, entity rules, workspace lifecycle, cleanup/rebuild/upgrade, and graph infrastructure evaluation.
- Phase 6 owns route orchestration/correction, Combined fusion, final answer/verifier/citations, streaming/API, production tracing, final holdout, and answer-quality gain.
- One shared v1 workspace contains only current company-visible versions readable by every active member/viewer. ACL-restricted documents remain authorized Hybrid-only.
- Vendor data is private implementation state. Only application protocols and resolver results cross the core boundary.
- Graph Ready requires terminal vendor processing plus complete accepted application maps and signed per-language gates; insertion alone is never enough.
- All graph/model/provider operations are at least once and reconciliation-driven; no checkpoint, track ID, vendor status, or lock creates exactly-once side effects.
- Active pointer/status/authorization/canonical evidence is application-owned Supabase state. Vendor workspace status or native summaries never override it.
- Updating/quarantined/disabled states are Hybrid-only with inspection unavailable; filtered-dirty reads use the strict resolver only.
- Deletion/ACL exclusion is immediate in application maps; targeted cleanup and clean rebuild are defense in depth with explicit SLAs.
- Numeric limits come only from this plan, signed quality targets, or measured/frozen contract docs.
- Phase 5 remains pending until packet 8 evidence and client/user acceptance are complete.

## Phase sequence requirement

Phase 5 implements GraphRAG: immutable LightRAG qualification, private plain-PostgreSQL storages, single-writer indexing, precomputed profile keywords, internal-chunk/graph-object-to-canonical passage maps, entity curation, atomic version visibility, global steering, deletion/ACL cleanup, bounded inspection, and graph infrastructure tests.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update [`docs/development/phase-05-graphrag-evidence.md`](../../../docs/development/phase-05-graphrag-evidence.md), linked from the repository documentation index, with:

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

## 7. LightRAG GraphRAG in Supabase

Pin and wrap LightRAG behind [`packages/core/src/smart_rag_core/retrieval/graph.py`](../../../packages/core/src/smart_rag_core/retrieval/graph.py). Application and LangGraph nodes depend on the project-owned `GraphRetriever`/`GraphIndexer` protocols, never directly on LightRAG classes. The dated qualification candidate is the immutable `lightrag-hku==1.5.6` artifact identified in the cheap-model protocol because it is the first released candidate with `PGTableGraphStorage`; packet 1 must verify its artifact hash and reject/disable rather than float or silently substitute. Configure the qualified PostgreSQL storage implementations:

- `PGTableGraphStorage` for nodes and edges in ordinary indexed tables; do not use `PGGraphStorage` or require Apache AGE.
- `PGVectorStorage` for LightRAG's graph/entity/relation vectors.
- `PGKVStorage` for graph-focused text chunks, summaries, and internal metadata.
- `PGDocStatusStorage` for idempotent document-processing status.

The pinned-version qualification test must prove the exact structured fields available from `aquery_data()` and qualified storage joins without parsing human-formatted context. Caller-controlled document IDs and qualified internal chunk/source associations may be used inside the adapter. Normalized entity names, relation endpoint pairs, file paths, descriptions, keywords, scores, and query-local reference ordinals are not assumed to be opaque stable application IDs or evidence. It must also accept both non-empty precomputed `hl_keywords`/`ll_keywords` and demonstrably skip keyword extraction and answer generation while accounting for expected query embedding/vector/optional-rerank work. A version that fails structured provenance, independent-source deletion, or callback contracts is rejected; GraphRAG remains disabled rather than weakening source security or silently adding latency/cost.

Use one fixed, versioned active LightRAG workspace for company-visible v1 content, with separate building workspaces for verified rebuild/switchover. Insert normalized document-version text through qualified asynchronous `ainsert`, passing the canonical `document_version_id` as the LightRAG ID and a unique non-secret opaque basename token as `file_path`; the pin may normalize file paths, so canonical identity always comes from the explicit ID and application map. Reject non-company-visible documents and do not use deprecated custom-chunk insertion. Pin the vendor fixed-token chunker/tokenizer/config because `ainsert` chunks independently from canonical ingestion. Treat returned track ID as monitoring only and require terminal status before mapping. Test duplicate IDs/basenames and identical normalized content under distinct canonical IDs; failure to preserve independent attribution/deletion disables GraphRAG pending an approved design. `lightrag_source_map` records document-level identity/readiness, but it is not sufficient evidence mapping.

At `Graph Ready` time, precompute passage support instead of doing N query-time searches:

1. Read each LightRAG internal chunk ID/content/source reference and map it to its canonical document version.
2. Attempt deterministic normalized-text hash/span/overlap matching to canonical chunks first.
3. Define an application `graph_statement_id` from the graph-pipeline version, subject canonical key, object canonical key, and a versioned normalized relation-label key derived from qualified structured relation fields; LightRAG does not provide an assumed opaque relation ID or canonical predicate, and generated relation prose remains a lead only. Batch unresolved internal chunks and relation statements for that document into one scoped Hybrid RPC using chunk text plus entity/relation labels; retrieve only canonical chunks from that version, then apply one bounded support rerank through the same OpenAI-only `Reranker` gateway.
4. Store accepted chunk mappings in `lightrag_chunk_map` with method, score, versions, and provenance. Store every queryable entity, relation/`graph_statement_id`, and path-edge support in `graph_evidence_map` keyed to canonical chunk IDs.
5. Calibrate the support threshold on labeled relation fixtures; start with `support_score >= 0.80`, require every queryable relation/path edge to have support and at least 90% overall mapping coverage, and mark lower-confidence objects unavailable. Pin and monitor LightRAG's source delimiter and per-entity/relation source retention caps; malformed, ambiguous, or truncated source sets are unavailable rather than silently treated as complete.
6. Query-time resolution is a bounded join over at most 12 graph candidates/six paths, not one search per statement. A missing/stale mapping drops the whole candidate, emits a repair job, and never performs an unbudgeted ad hoc sub-search.

Graph extraction/mapping quality is gated per detected document language rather than only in aggregate. The labeled Phase 5 set includes English, Arabic, and mixed Arabic/English entities, aliases, and relations; report extraction precision/recall, mapping coverage, and graph-survival by language. Provisional Arabic/mixed mapping coverage is at least 85% with every returned relation still support-mapped; signed values live in `QUALITY_TARGETS.md`. A document that misses its language gate cannot become `Graph Ready`, even when aggregate English-heavy coverage passes.

Wire every LightRAG embedding/index-time LLM/cache/optional-rerank callback through the shared budget/tracing gateway; no default callback may bypass accounting. Use one bounded retry layer so vendor and SDK retries cannot multiply invisibly, and record provider response/usage before returning callback output. Benchmark and display graph-indexing plus mapping cost per document before bulk approval. For queries, pass the `QueryProfile`'s high-level topics as non-empty `hl_keywords` and concrete entities/codes/relations as non-empty `ll_keywords`, so LightRAG skips duplicate keyword extraction and stays consistent with routing. Contract tests assert zero keyword and answer-generation callbacks while separately accounting for query embedding and any explicitly qualified rerank work.

LightRAG is configured as a structured lead retriever, not the final answer generator. Prefer qualified `aquery_data()` rather than parsing `aquery(... only_need_context=true)` rendered context. Use `local` for entity-centered relationships and graph `hybrid` when both local and cross-entity signals are needed. `global` summaries are never evidence: for broad thematic questions they may yield at most three bounded topic/entity steering expansions, which must go back through canonical Hybrid retrieval. Do not use `naive` or `mix` as substitutes for the application-owned Hybrid pipeline. Calls supply both precomputed keyword lists and bounded vendor token/top-k settings. Outer adapter timeouts, database statement timeouts, and application SQL/resolver expansion enforce maximum 12 candidates, three hops, six paths, stable ties, and cancellation because these are not assumed native `QueryParam` controls. Disable native query reranking unless separately qualified and budgeted. Graph inspection additionally enforces SQL-level depth three, 200 rows, a three-second `statement_timeout`, and the global 10-second inspection deadline.

Entity disambiguation is a managed input, not only an evaluation complaint. `graph_entity_rules` stores approved aliases, canonical display labels/types, and do-not-merge rules such as `PROJECT::ATLAS` versus `PRODUCT::ATLAS`. Owner/admin curation applies rules to the versioned extraction prompt/canonical keys; corrections invalidate affected graph mappings and require a clean workspace rebuild. Suggested rules from feedback stay inactive until approved, and native LightRAG summaries/names are never copied into Hybrid aliases automatically.

At retrieval time, treat graph statements as leads, not self-authenticating evidence:

1. Use qualified LightRAG entity names, relation endpoints, internal chunk IDs, and source associations only for candidate/path discovery; never expose or prompt with merged summary prose.
2. Resolve candidates by joining the active workspace's precomputed `graph_evidence_map`/`lightrag_chunk_map`, then reapply graph eligibility, transactional current-version pointer, deletion, and ACL checks.
3. Discard an entire entity/relation/path candidate when required mappings are missing, below threshold, stale, or no longer point to surviving authorized canonical chunks.
4. Fetch the already-mapped canonical passages/citation coordinates directly and reconstruct displayed relationship descriptions from those passages with explicit source links.
5. Return supported IDs, bounded paths/relationships, canonical chunk IDs, and confidence—not native LightRAG prose or an uncited answer. Combined and browse-only graph inspection use this identical resolver contract.

For every query record `graph_survival_ratio = supported_resolved_graph_candidates / returned_graph_candidates` (null when LightRAG returns none), detected language, and per-language mapping/survival telemetry. If a query resolves below 50%, set `requested_route=Combined`, `effective_route=Hybrid`, and `fallback_reason=graph_survival_below_threshold`; stream/display the degraded route. Alert when the rolling ratio is below 80% across 20 Combined queries or source-map misses spike. Record partial readiness: when relevant Hybrid hits come from company-visible versions not yet `Graph Ready`, increase Hybrid evidence weight and show “N relevant recent documents are not yet represented in the graph.” When the current user is authorized for relevant ACL-restricted Hybrid documents that are intentionally graph-ineligible, show only to that user: “N relevant documents you can access are not represented in the graph; relationship coverage may be incomplete.” Never disclose restricted counts, names, or existence to an unauthorized user.

V1 LightRAG represents current company-visible versions only. Superseded graph records are filtered/deleted after atomic pointer switching, so explicit `as_of` or historical relationship/multi-hop questions must not use graph paths. The adapter emits `temporal_graph_limitation`; Phase 6 routes those questions to Hybrid with a user notice that graph relationships reflect current indexed versions. This is an explicit limitation, not a silent Combined fallback.

Provide controlled rebuild, document deletion, ACL-downgrade reconciliation, and LightRAG-version upgrade commands. An embedding/model/chunker/extraction/entity/mapping change builds a homogeneous new versioned workspace in parallel, reindexes every graph-eligible current document, validates survival/quality/cost, then atomically switches the active workspace; in-place mixed configurations are forbidden. A LightRAG package/schema upgrade qualifies on a restored production-sized database/schema copy because vendor schema migrations are shared across workspaces; snapshot/restore is the schema rollback boundary. A workspace pointer rollback applies only when the vendor schema remains compatible. Two consecutive failed upgrade qualifications or persistent graph-survival alerts for seven days trigger a documented replacement/disable review through the `GraphRetriever` boundary. Phase 6/9 later applies the Combined quality-gain trigger using the completed answer pipeline. If initialization, indexing, mapping, active-workspace status, resolver, cleanup, or retrieval is unhealthy/quarantined/disabled, automatic queries use Hybrid and inspection is unavailable.

Before first bulk onboarding, [`docs/graph/SCALING_OPTIONS.md`](../../../docs/graph/SCALING_OPTIONS.md) sketches the trigger-review candidates without implementing them: workspace sharding by domain/security boundary, dedicated managed LightRAG PostgreSQL behind `GraphRetriever`, and qualified incremental compaction/rebuild approaches supported by the pinned engine. Crossing the seven-day, budget, survival, or database-isolation trigger opens an ADR comparing these options with Hybrid-only disablement.

The LightRAG eligibility rule is non-negotiable in v1: `graph_eligible=true` requires a current, company-visible document version readable by every active member/viewer. Job creation rejects graph indexing for ACL-restricted versions. Restricting a graph-indexed version atomically marks it ineligible and writes a high-priority `graph_acl_remove` job; the canonical resolver rejects that version before the ACL transaction becomes visible. The workspace becomes `filtered_dirty` while targeted cleanup and a batched clean rebuild proceed. If stable source references or resolver verification are unavailable, quarantine the graph and degrade Combined to Hybrid. Security tests prove restricted entity/relation text never appears in Combined or graph inspection. Per-ACL LightRAG workspaces are explicitly deferred.

LightRAG tables are never queried by the browser or user JWT. Define schema-scoped roles: API role for approved application functions/tables, query/checkpointer role for its private checkpoint schema, worker role for jobs/canonical writes plus LightRAG, append-only audit writer with no update/delete grant, and migration/bootstrap role for DDL/Auth administration. Runtime API/worker containers do not receive the Supabase `service_role` key. Browser uploads use the user's JWT plus Storage RLS; the worker uses a dedicated narrow Storage role/token restricted to document buckets/paths. The migration/bootstrap credential is environment-specific, stored only in AWS Secrets Manager for managed environments, never a long-lived GitHub secret, unavailable to runtime containers, and usable only by the protected migration procedure in Sections 13–14.

Pin LightRAG exactly, capture/review its generated schema, and run `initialize_storages()` through a controlled protected bootstrap. The qualified pin can create extensions/tables/indexes, alter/migrate data, use schema-unqualified names, and continue after some warnings; therefore bootstrap records every warning and verifies explicit schema/data postconditions instead of accepting a zero exit code. A DML-only runtime role must use the already-bootstrapped private schema without attempted DDL or drift; if the pin cannot support that least-privilege contract, reject/disable or obtain approval for an upstream/reviewed adapter strategy. Cap the process-wide pool, pin its first vector model/dimension configuration, control `search_path`, and always finalize storage references. Phase 2 creates [`docs/architecture/05-database-connections.md`](../../../docs/architecture/05-database-connections.md) with the selected Supabase tier's hard limit and explicit per-service budgets. API request/RPC traffic may use transaction pooling, but LangGraph checkpointer and LightRAG use Supavisor session mode or direct connections; they are never assumed compatible with transaction mode/prepared statements. Provisional caps are API transaction 10, API/checkpointer session/direct 4, API LightRAG session/direct 4, worker transaction 6, worker LightRAG session/direct 4, and two reserved operations connections. Before implementation, Phase 2 must prove these fit below 70% of the selected tier; otherwise upgrade the tier or reduce process/pool counts. Phase 9 revalidates all paths and HNSW build/query memory under load.

Connection caps are not workload isolation. Phase 2 also creates [`docs/architecture/06-database-workload-isolation.md`](../../../docs/architecture/06-database-workload-isolation.md) and applies role-specific `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`, bounded `work_mem`, pool caps, and query tags. HNSW creation/reindex and clean LightRAG rebuilds run one at a time in approved maintenance windows and pause automatically when user-query p95 breaches its gate or database CPU/IO exceeds 70%. After query/index tuning and vertical sizing, sustained CPU/IO above 70% for three 15-minute windows in a week, cache-hit degradation below the signed target, or three p95 breaches triggers the isolation ladder: first move read-heavy Hybrid candidate generation to a qualified Supabase read replica when reads dominate, monitor asynchronous lag, and revalidate every selected ID/current-version/ACL against the primary before use; if graph rebuild/storage dominates or replica lag cannot meet deletion/ACL semantics, move LightRAG storage behind `GraphRetriever` to dedicated managed Postgres instead. No replica result bypasses primary canonical authorization.

Canonical parsing/Hybrid jobs may execute in parallel across worker slots, but all LightRAG insert/delete jobs for the shared workspace and all rebuilds run with concurrency one under a PostgreSQL advisory lock. Normal insert admission enforces the daily ingestion budget, per-file estimate, and a default maximum of 100 pending jobs. When backlog exceeds 50, pause new graph indexing and prioritize scan/parse/Hybrid readiness; exhausted normal budget leaves inserts visibly queued. Deletion, ACL cleanup, and clean rebuild are compliance-maintenance jobs charged only to the separate reserve and always outrank normal indexing.

The admin status API/UI reports graph-writer rolling documents/hour, backlog age, estimated completion, and estimated remaining extraction cost. Bulk onboarding reserves budget and an approved maintenance window before graph jobs are admitted; Hybrid readiness continues independently.

The parser sandbox still shares the EC2 host kernel in v1. Record this accepted blast radius in [`docs/adr/ADR-parser-isolation.md`](../../../docs/adr/ADR-parser-isolation.md), patch host/kernel/parser images on a defined cadence, and treat any sandbox escape, critical applicable runtime/kernel CVE, regulated external-upload requirement, or expansion beyond the trusted company uploader model as a mandatory review for gVisor/Kata or a separate no-trust parser instance. Parser containers never join the provider/crawl/Valkey networks.

For insertion or the short targeted delete mutation, set the active workspace `updating`; Combined temporarily runs as Hybrid and inspection is unavailable. A successful insert returns it to `active` only after all maps and Graph Ready gates pass. A successful targeted delete/ACL removal returns it to `filtered_dirty`, where Combined/inspection may operate only through the strict resolver while a clean replacement `building` workspace builds separately. Atomic switch after rebuild returns status `active`; old workspaces become `retired`. Any failed/interrupted mutation, lease/advisory-lock loss, or resolver verification failure sets `quarantined` until reconciliation, preventing half-merged or unverifiable graph reads. A deliberate `disabled` state keeps Hybrid available and inspection unavailable.

Do not checkpoint raw files, full OCR output, or large base64 blobs. State carries Storage keys and database IDs. Renaming a title, changing headings, changing extraction/chunking, or changing contextual-embedding inputs enqueues a new version/re-embedding job; old and new indexes coexist until verified switchover.

Document-version replacement uses an explicit order. Build the new canonical vector/term and ParadeDB BM25 projection with `is_current=false`; insert and map its LightRAG data with retrieval eligibility off; verify canonical, BM25, and graph mappings; then one Supabase transaction flips `documents.current_version_id`, old/new Hybrid visibility plus BM25 visibility generation, and old/new graph source-map eligibility. Authoritative Supabase candidate resolution therefore exposes exactly one version even while old/new BM25 and graph rows exist physically. Only after the pointer flip does the serialized worker delete the old LightRAG document and schedule old BM25/graph cleanup. Failure before the flip leaves the old version current; failure after the flip leaves old derived records filtered out and retryable.

Document deletion immediately marks the version excluded from Hybrid/table retrieval, increments BM25 visibility generation/enqueues projection purge, and makes its source-map entries ineligible in the same transaction. BM25 and graph resolvers therefore drop any candidate/path lacking surviving authorized support, and neither BM25 snippets nor native merged LightRAG prose is exposed. Verify BM25 purge through the Phase 3 handler; set the graph workspace `updating`, then invoke the qualified document deletion with privacy LLM-cache deletion enabled under the single-writer lock. Persist/retry vendor recovery phases and verify full document, chunks, vectors, status, cache, graph/source associations, and surviving shared-source support within 24 hours. Successful targeted cleanup sets `filtered_dirty`; consolidate dirty graph deletions into a budgeted clean workspace rebuilt from surviving graph-eligible versions within seven days rather than depending on undocumented per-entity surgery. If deletion returns not-found/not-allowed/fail, is interrupted, lacks recovery evidence, leaves residue, or resolver verification fails, quarantine the graph immediately and degrade Combined/inspection until clean rebuild succeeds. The tombstone stays open and administrators see `Deletion cleanup failed`; canonical/Storage cleanup continues according to retention without re-enabling the deleted source.

Changing a graph-indexed document from company-visible to ACL-restricted uses the same enforcement: atomically apply the ACL plus source-map ineligibility, keep the document Hybrid-searchable only to authorized users, enqueue `graph_acl_remove`, perform targeted delete/verification, and include it in the next batched clean rebuild. ACL expansion does not automatically make a document graph-eligible; an authorized admin must approve a new graph-index job.

## Phase deliver, review, and done gate

### Phase 5 — GraphRAG

- Deliver: immutable-hash storages/adapters, reviewed private bootstrap/schema manifest, runtime least privilege, single-writer insertion/reconciliation, measured documents/hour/backlog ETA/cost API, precomputed `hl/ll` keywords, structured query parser, chunk/graph evidence maps with batched scoped matching, overall/per-language mapping/repair telemetry, Arabic/mixed fixtures, entity rules, local/hybrid plus global steering, temporal-graph and authorized ACL-blindness notice contracts, atomic version pointers, bounded inspection, privacy cleanup/rebuild, scaling-options document, and isolated upgrade/restore tests.
- Review: artifact/schema warnings and drift, workspace/pool/search-path/role isolation, duplicate-ID/basename/content attribution/deletion, callback/retry/cost bounds, structured versus prose fields, overall/English/Arabic/mixed mapping precision/coverage/threshold and cost, no N-per-statement query work, hidden keyword/answer-call absence, source caps, entity collisions/rules, global-steering leads, resolver survival, historical-relationship Hybrid routing contract, authorized-versus-unauthorized ACL blindness messaging, version overlap, partial readiness, isolation, bulk-onboarding duration/reserve, scaling candidates, and the Phase 6 handoff contract.
- Done when: the exact artifact-hashed LightRAG storages/adapters pass generated-schema/postcondition, structured-ID/source/duplicate, workspace/pool/finalization, precomputed-keyword, callback-accounting, status/cancellation/deletion, runtime-least-privilege, and bootstrap contract tests without AGE, prose parsing, ignored warnings, or runtime schema drift; shared-workspace insert/delete/rebuild is concurrency one with a durable lease plus application advisory lock, at-least-once reconciliation, separate budgets, backlog ETA, and safe `building`/`active`/`updating`/`filtered_dirty`/`quarantined`/`disabled`/`retired` states; every `Graph Ready` document meets internal-chunk/relation/path-to-canonical overall and signed per-language mapping thresholds and unmapped/stale/ambiguous/truncated objects are dropped with repair jobs; query resolution uses application-bounded joins with no N-per-statement search or duplicate keyword/answer LLM call and returns only authorized current canonical IDs plus confidence; historical relationship fixtures emit the Hybrid-only temporal limitation and never expose superseded graph paths; authorized users receive the bounded ACL graph-blindness signal while unauthorized users learn no restricted count/existence; entity alias/type/do-not-merge curation and invalidation work; generation-checked pointer flips expose exactly one version; ACL downgrade/deletion immediately suppress graph evidence, privacy cache/source/shared-entity cleanup verifies, failed cleanup quarantines/degrades, and clean rebuild/isolated-upgrade/snapshot-rollback commands work; graph inspection obeys depth/row/timeout limits; measured writer/rebuild throughput/ETA/cost proves or reduces the advertised seven-day graph envelope and funds the maintenance reserve; `SCALING_OPTIONS.md` covers trigger candidates; graph failure and low-survival paths produce the documented Hybrid handoff; and Phase 6 receives frozen fixtures/interfaces for Combined fusion, citation, and quality-gain evaluation without launch-holdout leakage. Phase 5 does not claim final Combined answer-quality success.
