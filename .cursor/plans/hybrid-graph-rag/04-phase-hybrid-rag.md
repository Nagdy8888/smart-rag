---
name: hybrid-graph-rag-phase-04-hybrid-rag
phase: 4
status: pending
depends_on: [1, 2, 3]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 4: Hybrid RAG

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Treat this file as the only implementation scope for Phase 4. Later-phase files may clarify an interface but do not authorize later-phase implementation.
3. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions before editing. This plan describes targets, not proof that a file or API already exists.
4. Load the relevant workspace skill files listed below before implementation.
5. Before every work packet, state the requirement and concrete acceptance checks. Implement the smallest complete packet.
6. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
7. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
8. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Phase 1 must define these commands; later phases must inspect rather than invent them.
9. Update documentation in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
10. Record proof in the exit record. If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR/plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md)

## Relevant workspace skills

- [`.cursor/skills/implement-hybrid-retrieval/SKILL.md`](../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md)
- [`.cursor/skills/implement-structured-table/SKILL.md`](../../../.cursor/skills/implement-structured-table/SKILL.md)
- [`.cursor/skills/implement-observability-evals/SKILL.md`](../../../.cursor/skills/implement-observability-evals/SKILL.md)

## Scope lock

**In scope:** Labeled datasets, multilingual Hybrid retrieval, query profiling, candidate generation, RRF, temporal behavior, OpenAI reranking, context selection, coverage/refusal, structured tables, citations, and evaluation.

**Out of scope:** LightRAG integration, final query LangGraph composition, generalized optional tools, production frontend, and deployment.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [ ] Freeze disjoint development/qualification/holdout datasets and import the private approved glossary, identifiers, acronyms, and aliases.
2. [ ] Implement versioned indexed representations, Arabic normalization parity, private ParadeDB BM25 queries, filtered HNSW iterative scans, and populated trigram terms.
3. [ ] Implement typed query profiling including negation, document scope, media dependence, and historical-relationship signals; independently score every field before attributing misses to retrieval.
4. [ ] Implement bounded parallel channels and query variants, normalized weighted RRF, UTC-anchored temporal policies, whole-document coverage/refusal, and conflict behavior.
5. [ ] Implement the accuracy-first top-20 OpenAI reranker contract, deterministic fallback, skipped-case counterfactuals, MMR, quotas, and parent expansion.
6. [ ] Calibrate coverage/refusal by query class before the immutable holdout and prohibit unsupported advanced methods.
7. [ ] Implement the declarative, sandboxed structured-table path with exact workbook/sheet/range provenance.
8. [ ] Publish ablations, quality, latency, cost, citation, ACL, and fallback evidence; freeze winning versioned profiles.

## Cheap-model execution protocol

The eight checkboxes above are separate work packets. One model run may execute only one packet, in order. Before editing, the model must quote the active packet, state its positive and negative acceptance checks, inspect every target path plus the Phase 1–3 accepted exit records, and prove all prerequisites. This expanded plan does not satisfy any prerequisite or sign-off.

Use [`docs/development/phase-04-hybrid-rag-evidence.md`](../../../docs/development/phase-04-hybrid-rag-evidence.md) as the canonical packet evidence and exit record. Packet 1 creates it and links it from `docs/README.md`. Every packet appends inspected migrations/schema/pins, dated primary-documentation links, exact commands and exit codes, dataset/config hashes, authorization and failure fixtures, measured quality/latency/cost/resources, unresolved assumptions, rollback, and next-packet handoff.

Create [`docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md`](../../../docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md) in packet 2 and update it through packet 8. It is the single source for versioned channel profiles, candidate/scan/deadline bounds, HNSW transaction settings, ParadeDB query/index contract, RRF, temporal factors, rerank pool/schema/model, MMR/quotas, parent/context budget, coverage/refusal thresholds, cache keys/TTLs, and fallback reason enums. Every tunable records unit, source/baseline, allowed range, selected value, dataset/config version, metric evidence, owner, rollback value, and review trigger. Values fixed in this plan remain fixed unless an approved ADR changes them; unspecified values must be measured and frozen rather than invented.

For pgvector, Supabase/PostgREST/connection pooling, ParadeDB/`pg_search`, OpenAI Responses/structured output, LangSmith, DuckDB, and evaluation tooling:

1. inspect the exact repository pin/image/model snapshot, license, configuration, and current primary documentation;
2. run a real contract test against the pinned boundary;
3. record exact versions/digests/model IDs, source URL/date, qualified behavior, and limitations;
4. benchmark operational/tuning values on the approved development/qualification sets and supported hardware; and
5. stop rather than guessing an API, query grammar, tokenizer behavior, authorization context, provider retry/idempotency, score meaning, timeout, or resource limit.

The implementation must preserve these provider caveats:

- pgvector `strict_order` orders the approximate candidates found; it does not make HNSW exact or guarantee enough authorized survivors. `hnsw.max_scan_tuples` is an approximate additional-scan control, not a hard total-work limit, and `hnsw.scan_mem_multiplier` scales `work_mem` rather than creating an independent memory ceiling.
- Data API requests can carry verified JWT context, but direct/pooled SQL does not automatically receive Supabase user identity. A trusted application must verify the token/session, begin one transaction, use only transaction-local role/claims/statement settings, execute the security-invoker RPC in that transaction, and reset through commit/rollback. Passing caller IDs as client parameters is not authorization.
- ParadeDB parameter binding protects SQL structure but does not make unrestricted raw query-language input safe. Use typed structured query constructors and allow-listed fields/operators. Relevance pagination/keyset behavior is not assumed: either qualify a stable relevance-preserving cursor for the exact pin or issue one bounded top-N query.
- OpenAI has no assumed dedicated endpoint for reranking arbitrary Supabase candidates. Use one bounded structured-output Responses operation only after qualification, then enforce application-level candidate-ID set equality, uniqueness, ordering, support-score bounds, completion status, and budget. A schema-valid response can still be semantically invalid, incomplete, or a refusal, and provider idempotency/duplicate-cost protection is not assumed.
- DuckDB `read_only`, `enable_external_access=false`, allow-listed paths, extension locks, and memory settings are defense in depth, not a hostile-code sandbox or general statement timeout. Use an isolated no-network process/container, exact immutable artifact paths, process-level deadline, interrupt, kill grace, and OS resource limits.
- LangSmith split labels can overlap and do not make a dataset immutable. Project validation, manifest hashes, permissions, frozen version tags, and one-way holdout access enforce isolation.

Dataset leakage is a launch-blocking defect. The Phase 2 embedding-qualification slice, Phase 4 development set, Phase 4 qualification set, immutable launch holdout, and post-launch regression set are disjoint by stable case/source-group IDs. Development selects/tunes; qualification confirms one proposed freeze; the launch holdout runs once after freeze and never seeds aliases, prompts, thresholds, or methods. If the holdout fails, record the failed release; repairs use development/qualification data, and a later launch claim requires a newly collected and independently sealed holdout approved by the SME.

The minimum 405 labeled cases in the canonical requirements are the complete initial Phase 4 corpus minimum, not permission to place the same case in several splits. Unless `DATASET_SPEC.md` obtains a different signed allocation before labeling, allocate each query class deterministically as 50% development, 25% qualification, and the remainder holdout, with at least one qualification and one holdout case per class. Group all variants from the same source/question family into one split. Graph/Combined/tool/frontend cases may be labeled now but their runtime execution remains Phase 5/6/8 evidence and cannot make Phase 4 pass.

Do not implement LightRAG, `GraphRetriever`, Combined fusion, final query LangGraph/SSE, generalized tool discovery, production tracing/feedback, answer/verifier/summary prompts, frontend, deployment, HyDE, RAPTOR, SPLADE, ColBERT, learned-to-rank, local rerankers, or map-reduce/recursive summaries. Labels and extension interfaces do not authorize later-phase runtime.

At most two bounded repair attempts may target the same external/integration failure. A skipped real-boundary test, empty term channel, mocked authorization recheck, holdout tuning, non-empty-output assertion without ranked-ID/metric proof, uncited BM25 snippet, silent degraded mode, or uncalibrated confident answer cannot close a packet.

## Work packet implementation contracts

### Packet 1 — frozen datasets and private glossary seed

#### Packet 1 preconditions

- Phases 1–3 are complete, accepted, and linked from `docs/README.md`; signed quality targets, governance, embedding ADR, chunk/projection evidence, and a representative `Hybrid Ready` corpus exist.
- The Phase 2 embedding-qualification manifest is available and immutable.
- The client-appointed Knowledge Owner/SME has committed the planned 12–20 review hours and approved synthetic/private-data handling.

#### Packet 1 allowed outputs

- `docs/evaluation/DATASET_SPEC.md`, query-profile labeling/adjudication docs, redacted/versioned fixture manifests, LangSmith offline dataset/version references where governance allows, and Phase 4 evidence.
- Owner/admin private glossary/identifier/acronym/alias import service and audit tests. Private glossary values remain in authorized storage/database, not Git.
- Dataset validation, split sealing, label schema, import validation, and reproducibility tooling.

#### Packet 1 forbidden outputs

- Retrieval implementation, configuration tuning, holdout-derived aliases/few-shots, duplicated cases across splits, private glossary content in Git/logs/traces, forced gold labels for unresolved disagreement, or a subjective unlabeled “golden set.”
- Executing Phase 5/6 graph/route cases merely because the dataset labels them.

#### Packet 1 ordered actions

1. Inspect signed `QUALITY_TARGETS.md`, governance, Phase 2 embedding manifest, Phase 3 indexed fixture/version manifests, docs index, and repository verification commands.
2. Define immutable case IDs, source-family IDs, dataset schema/version, split enum, provenance, label status, adjudicators, disagreement, and redaction rules before sampling.
3. Label query, acceptable answer variants, canonical source/passage/table ground truth, atomic evidence links, expected refusal/limitation/route, expected query-profile values/confidences/provenance, language/configuration, temporal fields, codes/entities/aliases, filters, ACL actor/snapshot, chunk/parent truth, and failure stage.
4. Populate at least the 405-case class matrix in the canonical requirements. Apply the signed/default split allocation by source family and prove pairwise disjointness from the Phase 2 slice and every other split.
5. Freeze development, qualification, and holdout manifests with ordered case IDs, source-version hashes, schema hash, label revision, and SME approval. Protect holdout access from tuning scripts/users.
6. Implement SME adjudication: ambiguous labels retain alternatives and disagreement; no developer/model silently chooses a gold answer.
7. Implement owner/admin glossary import with source/version/effective scope/language/type, alias conflict/cycle/duplicate detection, canonical target existence, approval, rollback, and append-only audit.
8. Sample the real corpus under governance to version deterministic identifier regex/checksum rules. Reject unsafe/high-collision rules.
9. Seed glossary/codes/acronyms/aliases before retrieval evaluation and create term-channel coverage fixtures without exposing private values.
10. Append class/split counts, manifest hashes, import audit, SME decisions, commands, and blockers.

#### Packet 1 acceptance checks

- The full labeled corpus meets every minimum class count; split manifests are pairwise disjoint by case and source family; the embedding slice is disjoint.
- Every case has ACL actor, canonical source/evidence or explicit no-evidence/refusal truth, complete expected profile fields, and adjudication status.
- Tuning tooling cannot read the holdout by default; any authorized final access is auditable and version-pinned.
- Glossary import is owner/admin-only, rejects cycles/conflicts/duplicates/cross-scope aliases, records source/version/approval, and populates term fixtures.

#### Packet 1 negative tests

- Duplicate/source-family leakage, missing actor/evidence/profile label, malformed class, unapproved glossary row, alias cycle, identifier collision, private-value trace/log, or holdout access from calibration code fails.

#### Packet 1 stop routes

- Prerequisite exits/sign-offs/corpus are absent, SME cannot adjudicate, governance blocks required data handling, or the sealed split cannot meet class/statistical requirements.

#### Packet 1 required evidence

- Dataset specification, complete count/split/disagreement report, manifest hashes and access controls, Phase 2 disjointness proof, glossary import authorization/audit results, identifier-rule review, SME sign-off, and exact validation commands.

### Packet 2 — versioned dense, BM25, term, normalization, and authorization foundations

#### Packet 2 preconditions

- Packet 1 passes; Phase 2 proves pgvector 0.8+ and the selected vector type/operator/dimension, Arabic normalizer parity, private ParadeDB pin/contracts, identity propagation, and connection budgets.
- Phase 3 proves contextual embeddings, canonical/raw passages, populated search-term sources, BM25 projection/index versions, current-version/deletion/ACL generations, and `Hybrid Ready`.
- Real local Supabase and private ParadeDB run with least-privilege retrieval credentials.

#### Packet 2 allowed outputs

- Additive retrieval indexes/RPCs/migrations under `supabase/migrations/`, core `Bm25Retriever` and dense/term adapters under the approved package boundary, retrieval contract/docs, and real integration/plan tests.
- Retrieval-specific HNSW/trigram/metadata indexes and typed query constructors; no competing canonical projection or normalizer.

#### Packet 2 forbidden outputs

- Installing `pg_search` in managed Supabase, using `ts_rank_cd` while claiming BM25, a second Arabic normalizer, English/Arabic stemming without ablation, raw query parser input, BM25 snippets as evidence, RLS-bypass user retrieval roles, or client-selected caller identity.
- Treating `strict_order` as exact recall, a planner estimate as a hard work cap, or ParadeDB score as cross-channel/calibrated confidence.

#### Packet 2 ordered actions

1. Verify and record Postgres/pgvector/ParadeDB/image/client pins, extension/index versions, index DDL, tokenizers/filters/key field, vector operator class, role grants, connection mode, and Phase 2/3 contract outputs.
2. Create/validate HNSW cosine or ADR-selected index over contextual embeddings while citations resolve only raw canonical passages. Add required trigram, date/status/language/tag/authority/ACL predicate indexes after `EXPLAIN` evidence.
3. Implement one authorization protocol. Data API uses verified JWT/RLS; direct pooled SQL uses trusted token/session verification, non-owner/non-`BYPASSRLS` role, one transaction, transaction-local claims/role/GUCs/statement timeout, security-invoker RPC, and guaranteed commit/rollback cleanup.
4. Put typed authorization and metadata predicates inside dense/term RPC SQL so filtering occurs before ranking/limit. Chaining an outer filter after the RPC is forbidden.
5. Set `hnsw.iterative_scan`, `ef_search`, scan controls, `work_mem`, and timeout with `SET LOCAL` in the same retrieval transaction. Prove settings do not leak across pooled reuse, rollback, cancellation, or error.
6. Benchmark allow-listed low/medium/high selectivity profiles against exact authorized-vector oracles. Record Recall@K, survivors, latency, tuples, memory, plans, and underfill.
7. Permit exact fallback only after an authorization-equivalent bounded admission check and with enforceable statement/work/row limits. The 10,000 authorized-row plan ceiling is necessary but planner estimates alone are insufficient; if hard bounded execution cannot be proven, return weak-evidence diagnostics.
8. Implement typed ParadeDB structured queries over allow-listed indexed fields/operators: title/identifier above heading/approved alias above body; phrase/boolean intent only from validated profile; stable `(score desc, canonical_id asc)` order; server/client deadline; read-only role.
9. Qualify Unicode/ICU/token/filter behavior for Arabic/English/mixed text. Default to no stemming claim. Prove byte-identical active-version forms across Supabase projection, core query normalization, and ParadeDB indexed/query text while citations remain raw.
10. Populate and test trigram/exact terms from filenames/titles/headings, deterministic identifiers, approved glossary, and aliases. Empty/cold terms block alias/code claims.
11. Implement BM25 candidate ID output only plus batch authoritative Supabase recheck interface. Unauthorized/stale/deleted/current-version-mismatch IDs and scores never reach fusion, model prompts, caches, or exported traces.
12. Add version mismatch, timeout/cancel, query-syntax injection, selective filters, normalization drift, role/context reuse, and exact-fallback bound tests.
13. Append migration/pin/plan/query/normalization/authorization evidence.

#### Packet 2 acceptance checks

- Data API/direct protocol fixtures return identical authorized IDs and zero rows for missing, forged, expired, disabled, revoked, cross-scope, stale-snapshot, service-role, and table-owner misuse.
- Filtered HNSW meets signed candidate recall/sufficiency by selectivity slice against exact oracle; settings are transaction-local and exact fallback cannot exceed its hard bound.
- ParadeDB typed queries return stable canonical IDs only; raw query injection cannot alter fields/operators; Arabic/mixed parity is byte-identical.
- The populated term channel meets development exact-code/alias candidate gates and raw citation text is unchanged.

#### Packet 2 negative tests

- Outer post-RPC filtering, caller-ID-only authorization, pooled GUC leakage, unauthorized BM25 survivor, strict-order exactness claim, unbounded exact scan, raw `pdb.parse`, version mismatch, tokenizer drift, or cold term channel fails.

#### Packet 2 stop routes

- Phase 2/3 compatibility evidence is absent, required pins/APIs cannot be verified, direct pooled identity reset cannot be proven, selective recall misses without safe profile/fallback, or migration changes canonical data semantics.

#### Packet 2 required evidence

- Exact migration/index/role/function definitions, extension/image/client pins, primary-doc links, `EXPLAIN ANALYZE` and pooled-context traces, exact-vs-ANN metrics, Arabic parity hashes, ParadeDB query/timeout/version tests, term population/recall, and rollback.

### Packet 3 — typed query profiling and first-stage attribution

#### Packet 3 preconditions

- Packets 1–2 pass; signed governance allows the bounded profile call; approved aliases/normalizer/date parser are available.
- Labeled expected profile fields exist on development/qualification data and the model/prompt/schema gateway can be pinned and budgeted.

#### Packet 3 allowed outputs

- Typed profile models/normalizers in core, profile prompt/changelog only under `apps/agents/src/smart_rag_agents/prompts/`, offline evaluation runner, and query-profile evaluation docs.
- Deterministic rules may run without a model; one structured model operation may fill genuinely inferred fields.

#### Packet 3 forbidden outputs

- Final answer/verifier/summary/tool prompts, query LangGraph, hidden second keyword/variant call, arbitrary LLM-generated weights/depths, hard low-confidence filters, silent negation inversion, more than three subquestions/variants, or holdout examples as few-shots.

#### Packet 3 profile schema

Every inferred/normalized field carries typed value, confidence in `[0,1]`, and provenance exactly `deterministic`, `approved_alias`, `model_inferred`, or `user_supplied`, plus source span/rule/alias ID where applicable:

- profile/prompt/model/normalizer/date-parser versions and original query;
- language plus mixed-locale/configuration;
- query type: exact identifier, factual, semantic/conceptual, multi-part, relationship/multi-hop, broad summary, or structured tabular aggregation;
- exact terms, quoted phrases, codes, numbers, dates, entities, and approved aliases;
- requested document/source and allow-listed metadata filters;
- temporal intent `latest`, `current`, `recent`, `as_of`, or none; target date/timezone and authoritative date field;
- negation scope `none`, `entity_exclusion`, `policy_exclusion`, or `set_complement`;
- document/section/page/sheet/range scope;
- media dependence and historical-relationship signal;
- relationship and table intent plus allow-listed table operation hints;
- rewrite justification, at most three decomposition subquestions, and at most three focused variants;
- precomputed `hl_keywords` and `ll_keywords` from this same profile; and
- allow-listed retrieval-profile ID, never free-form channel weights/depths.

#### Packet 3 ordered actions

1. Define strict input/output schemas, enum/length/count bounds, version fields, confidence/provenance rules, and safe diagnostics before prompting.
2. Extract deterministic quotes/codes/numbers/source scopes and apply the Phase 2 normalizer, approved aliases, and deterministic date parser without changing original query.
3. Make one bounded structured profile operation only when needed. No tools/retrieval and no duplicate LightRAG keyword call.
4. Validate model output against deterministic extractions. Unknown aliases/filters/profile IDs, changed numbers/entities/negation/dates/scope, malformed dates, and over-decomposition fail or fall back safely.
5. Low-confidence inferred filters remain soft diagnostics or trigger clarification; they never become hard predicates. Low-confidence negation cannot invert a set. User-supplied hard scope still requires authorization.
6. Generate focused variants only when justified. Preserve original entities, numbers, quotation, negation, dates, requested source, and scope; duplicate variants collapse.
7. Derive `hl_keywords`/`ll_keywords` and table/relationship signals in the same profile response/output; Phase 4 only persists/exposes them.
8. Select retrieval behavior by allow-listed versioned profile ID. LLM output never controls numeric candidates, scan memory, timeouts, SQL, or model settings.
9. Score every field independently on development then qualification data and store first-failing stage. Do not blame retrieval when an applicable profile field is wrong.
10. Allow confirmed redacted profile failures to become versioned few-shots only after SME approval and disjointness checks.
11. Append schema/prompt/model, budget, field metrics, variant fidelity, and attribution evidence.

#### Packet 3 acceptance checks

- Signed provisional gates pass separately: language/configuration accuracy at least 95%; temporal macro-F1 at least 90%; exact code/date extraction F1 at least 98%; entity/approved-alias macro-F1 at least 90%; metadata-filter precision and recall at least 95%; query-type/relationship/table/decomposition macro-F1 at least 90%.
- Negation, document scope, media dependence, historical relationship, source/date field, and variant fidelity are separately reported with signed field-appropriate metrics.
- Every value has valid confidence/provenance; deterministic contradictions and unknown hard fields cannot pass.
- No profile fixture requires a second hidden model/keyword operation.

#### Packet 3 negative tests

- Query/schema injection, unknown filter/alias/profile, changed code/number/date/negation/scope in rewrite, low-confidence hard filter/inversion, >3 variants/subquestions, malformed output, timeout/refusal/budget denial, and holdout few-shot access all take typed safe routes.

#### Packet 3 stop routes

- Labels/governance/model snapshot/schema contract are unavailable, signed field gates cannot be met, or safe deterministic fallback/clarification cannot preserve user intent.

#### Packet 3 required evidence

- Profile schema/prompt/model hashes, per-field development/qualification confusion metrics, provenance/confidence calibration, variant-fidelity corpus, one-call accounting, first-failure samples, approved few-shot manifest, and exact commands.

### Packet 4 — bounded channels, authoritative recheck, RRF, temporal, conflict, and coverage signals

#### Packet 4 preconditions

- Packets 1–3 pass; real dense/BM25/term adapters, authorization recheck, signed Hybrid deadline, visibility generations, and frozen candidate profiles exist.
- Benchmark/circuit-breaker clocks and cancellation propagate through all channel clients.

#### Packet 4 allowed outputs

- Framework-independent parallel retrieval/fusion/temporal/conflict/coverage services, cache contracts/adapters, diagnostics, and real integration tests.
- Hybrid retrieval result objects only; Phase 6 owns final orchestration/answer streaming.

#### Packet 4 forbidden outputs

- Per-variant multiplication of caps, raw-score cross-channel arithmetic, sum-across-variant credit, unauthorized IDs in fusion/traces/cache, silent BM25 failure, client-selected limits, unbounded pagination, arbitrary metadata bonuses, query answer generation, or Combined escalation execution.

#### Packet 4 ordered actions

1. Derive absolute channel/deadline budgets from the remaining 25-second Hybrid deadline. Start channels in bounded parallel work, cancel/close on deadline, and record timeout/cancellation separately from zero results.
2. Enforce server-side post-variant-dedup maxima: 100 dense, 75 authorized BM25, 30 term, and 205 unique pre-fusion IDs.
3. For BM25, scan at most 300 IDs over at most three bounded retrieval rounds across all variants. Use a relevance-preserving cursor only after a pinned-version contract test proves no duplicate/omission; otherwise use one top-300 stable ordered query. Recheck each bounded batch/page through Supabase before accumulation.
4. Reject missing/forged/stale authorization context. Every candidate resolved for fusion/context is current, undeleted, ACL-authorized, scope-matching canonical Supabase data; BM25 text/snippets are discarded.
5. For each passage/channel, use the best reciprocal-rank contribution across variants exactly once, invariant to variant order/duplicates. Then sum weighted vector/BM25/term contributions with initial `rrf_k=60` and allow-listed query-profile weights.
6. Keep raw scores only for within-channel order. Apply only evaluated multiplicative authority/title/heading/explicit-temporal factors whose product is clamped `[1.0, 1.15]`; current version/ACL are hard filters.
7. Implement temporal rules exactly: `latest`, `current`, `recent`, `as_of`, and none under UTC or the one signed company timezone. Unknown dates cannot win strict claims; no-authoritative-date, mixed locale, expiry/supersession, and Hijri limitations are explicit.
8. Equally authoritative current contradictions return conflict evidence with all relevant dates/citations. Stable final ties use authority, effective date, published date, then canonical ID.
9. Compute whole-document section coverage from the authorized current heading inventory; if bounded context cannot cover every major section, return scoped uncovered-heading/page diagnostics rather than a full-summary claim.
10. Negation/exclusion requires precise scope or deterministic closed-set evidence; media-only required evidence returns the signed limitation. Phase 4 emits coverage/refusal/relationship signals but does not spend the Phase 6 correction/escalation budget.
11. ParadeDB unavailable/version-mismatched/over-deadline/open-circuit degrades visibly to dense+term with `bm25_unavailable`; never label it full three-channel Hybrid.
12. If implementing cache in this phase, key it by principal/ACL-scope hash, profile/index/normalization versions, and document-visibility generation; store IDs/ranks only; use signed/global TTLs; always recheck authoritative Supabase before evidence. Otherwise expose the versioned cache-key/recheck interface for Phase 6.
13. Append candidate/recheck/RRF/temporal/conflict/degradation/deadline evidence.

#### Packet 4 acceptance checks

- Caps hold across all variants; BM25 scanning never exceeds 300/three qualified rounds; zero unauthorized/stale/deleted/wrong-current IDs reach fusion, cache, prompt, or trace.
- RRF is invariant to variant order/duplicate variants and max-not-sum; metadata product never exceeds 1.15.
- Selective filters retain signed candidate recall/sufficiency; BM25 kill/version/timeout produces bounded visible dense+term degradation.
- UTC/company-timezone temporal, conflict, whole-document, negation, historical, and media limitation fixtures take deterministic supported/refusal routes.
- Channel work and authoritative recheck fit allocated deadlines or return explicit bounded weak/degraded results.

#### Packet 4 negative tests

- Client limit override, unqualified relevance cursor, score mixing, sum-across-variants, stale cache, forged actor, unauthorized BM25 ID, unknown date winning `latest`, top-k complement inference, map-reduce summary, or silent outage fails.

#### Packet 4 stop routes

- Authorization recheck cannot exercise real Supabase/RLS, pagination cannot be bounded, selective recall misses without safe diagnostics, cancellation leaks work/connections, or deadline allocation cannot meet signed targets.

#### Packet 4 required evidence

- Per-channel/variant ranked-ID traces, scan/recheck counts, authorization negatives, cursor/single-query contract, RRF property tests, exact-oracle recall slices, temporal/conflict/coverage fixtures, outage/circuit/deadline traces, cache recheck proof, and exact commands.

### Packet 5 — accuracy-first reranking, deterministic fallback, diversity, and parent context

#### Packet 5 preconditions

- Packet 4 fused authorized candidates pass; signed governance permits bounded candidate text; durable budget gateway/model usage ledger and pinned OpenAI model/SDK/Responses schema are qualified.
- Development/qualification rerank ground truth and always-rerank baseline protocol exist; holdout stays inaccessible.

#### Packet 5 allowed outputs

- Core `Reranker` interface, one OpenAI structured-output implementation, deterministic RRF fallback, rerank evaluation prompt/schema, query-class MMR/quotas, parent/adjacent expansion, and tests/reports.
- Phase 4 rerank prompt/changelog only; no answer/verifier prompt.

#### Packet 5 forbidden outputs

- Local cross-encoder/model/runtime, OpenAI-hosted vector store search as arbitrary-candidate reranker, tools/external retrieval in the call, hidden SDK/gateway retries that exceed one operation, raw confidence as probability, score-gap skip policy, prose-only result, production shadow calls, or reranking unauthorized/BM25 snippets.

#### Packet 5 ordered actions

1. Collapse exact/near-duplicate and variant clusters while retaining all canonical provenance/citation records. Build one top-20 fused pool with at most five passages per document.
2. Rerank every non-trivial knowledge query with at least two authorized candidates. Skip only a fully supported trivial exact code/quoted phrase with complete terms/filters and at least two independent applicable channel signals; numeric score gaps never qualify.
3. Reserve worst-case cost once and clamp candidate excerpts/input/output/model timeout to remaining deadline. Make one Responses operation with no tools and strict schema whose candidate ID enum is request-specific.
4. Require every supplied ID exactly once, no unknown/extra/duplicate/missing ID, deterministic rank order, bounded support value, complete response status, matching request/input hash, and no prose. Treat support as a ranking feature, not calibrated probability.
5. Disable or explicitly account for automatic SDK retries so the one-operation and model-call budget is true. Timeout-after-provider-success may duplicate cost; ledger, request ID, usage, and fallback remain observable.
6. Refusal, incomplete output, schema/semantic failure, timeout, cancellation, budget denial, model/version mismatch, or unknown usage falls back to deterministic pre-rerank RRF order with typed reason. Never retry through a local model.
7. Run accuracy-reference `always rerank top 20` on development/qualification sets. For every conditionally skipped case, run one offline counterfactual and record top-1/top-5, nDCG, evidence/term/subquestion coverage, citation support, latency, and cost deltas.
8. Apply query-class-calibrated MMR after rerank with pinned similarity source/normalization/metric/lambda/candidate depth, per-document/section quotas, and stable ID tie-breaks.
9. Search small passages, then load only strongest authorized current parents/adjacent passages needed for coherence. Recheck after expansion and enforce final approximately 8–12 evidence units/token budget.
10. Return canonical IDs, component/fused/rerank ranks, support feature, decision/fallback, MMR/quota/parent decisions, source metadata, and exact canonical locators; no synthetic prefix/BM25 snippet becomes citation.
11. Append schema/model/budget/counterfactual/diversity/context/fallback evidence.

#### Packet 5 acceptance checks

- Strict schema plus application set-equality rejects every unknown/duplicate/missing/extra/malformed result; fallback preserves deterministic authorized RRF evidence.
- All non-trivial eligible cases rerank; every development/qualification skip has counterfactual evidence before trigger tightening.
- MMR/quotas improve duplicate/source diversity without violating signed relevance/citation gates; parent expansion stays authorized/current and inside token/evidence limits.
- Repository dependency scan proves no local rerank model/runtime.

#### Packet 5 negative tests

- Prompt/schema injection, unknown/duplicate/missing IDs, refusal/incomplete response, support out of bounds, timeout-after-success, 429/retry, budget/cancel/version mismatch, single-document crowding, stale parent, and over-budget context all take deterministic safe routes.

#### Packet 5 stop routes

- No qualified dated/approved model or schema API, governance/budget gateway fails, one-operation accounting is false, or conditional policy cannot approach the always-rerank reference within signed tolerances.

#### Packet 5 required evidence

- Model/SDK/prompt/schema/input hashes, live contract-call outputs and request/usage ledger, malformed/fallback matrix, always-versus-conditional/counterfactual report, MMR/quotas/parent ablations, cost/latency, dependency scan, and exact commands.

### Packet 6 — coverage/refusal calibration and frozen retrieval profiles

#### Packet 6 preconditions

- Packets 1–5 pass on development data; qualification and holdout permissions/manifests remain sealed.
- Objective stage metrics and signed cost/latency/false-support tolerances exist.

#### Packet 6 allowed outputs

- Development tuning, one proposed qualification freeze, versioned `HYBRID_RETRIEVAL_CONTRACT.md`/tuning reports, immutable config artifacts, and explicit v1 method prohibition register.
- Changes only to allow-listed Phase 4 tunables; no new retrieval family.

#### Packet 6 forbidden outputs

- Holdout access, repeated qualification fishing without versioned failed candidates, threshold tuning from anecdotes, unsupported confident answer favored over refusal, or any prohibited advanced method/runtime.

#### Packet 6 ordered actions

1. Compute deterministic `HybridCoverage` from required term/entity coverage, subquestion coverage, distinct evidence/profile minimum, and bounded support feature. Simple uses subquestion coverage 1/profile minimum 1; relationship needs two units; broad synthesis needs three sections/documents; multi-part needs one supported unit per subquestion.
2. Start with weak coverage `<0.65`, but treat it as a development baseline. By query class, calibrate supported-answer precision, answer rate/recall, false-supported rate, unnecessary-refusal rate, contradiction handling, and ACL-filtered refusal; false confident support carries greater loss.
3. Tune only named allow-listed profiles: BM25 query forms/boosts/tokenizer option, HNSW selectivity profile, channel depths, `rrf_k`, weights, variant policy, metadata/temporal multipliers, rerank trigger/pool, MMR/quotas, parent/context, and coverage/refusal thresholds.
4. Measure each stage separately and attribute first failure: profile, channel candidate recall, authoritative recheck, fusion, rerank, context/parent, coverage/refusal, or table.
5. Run paired development ablations and confidence intervals/statistical tests where appropriate. Reject nominal gains that violate ACL, citation, latency, cost, answer-rate, or refusal gates.
6. Freeze one candidate configuration with dataset/prompt/model/index/normalizer/code hashes, then run qualification once. Record pass/fail without tuning on qualification cases. A failed candidate becomes evidence; subsequent candidate requires a versioned rationale and remains holdout-blind.
7. Freeze the winning profiles before holdout and make runtime configuration select only immutable profile IDs. Record rollback profile.
8. Document prohibited v1 methods and extension interfaces; do not install or partially implement them.
9. Append calibration/qualification/freeze and leakage-control evidence.

#### Packet 6 acceptance checks

- Per-query-class answer/refusal curves support frozen thresholds; every tightened candidate depth/rerank skip has recall/counterfactual evidence.
- Qualification confirms signed profile and retrieval gates without holdout access; config is immutable/version-addressed with rollback.
- First-failing-stage reports prevent ranking claims when profiling/candidate/authorization/context failed.
- Repository search/dependency lock proves prohibited methods/models are absent.

#### Packet 6 negative tests

- Tuning script holdout read, config mutation after freeze, unknown runtime profile, hardcoded untethered threshold, unsupported method import, or failed qualification relabeled pass fails.

#### Packet 6 stop routes

- Signed gates cannot be met, qualification shows material recall/refusal/ACL/cost/latency regression, holdout isolation is compromised, or a new method is required without ADR/user approval.

#### Packet 6 required evidence

- All development/qualification curves and paired tests, first-failure matrix, rejected candidate profiles, frozen config/hash/rollback, leakage/access logs, prohibited-method dependency scan, and exact commands.

### Packet 7 — declarative structured-table retrieval and calculation

#### Packet 7 preconditions

- Packets 1–6 pass; Phase 3 private Parquet/table manifests preserve explicit schemas, formulas/cache authority, units, hidden sheets, duplicate headers, dates/timezones, and exact source ranges.
- Packet 3 table intent/operation hints and the Phase 2/3 table authorization/current-version resolver are available.
- Pin DuckDB/Arrow/client/runtime and select OS/process, memory/thread/temp/bytes/rows/output/deadline/kill bounds from adversarial qualification.

#### Packet 7 allowed outputs

- Deterministically bound internal `structured_table_query`, strict `TableQueryPlan`, server-side manifest/artifact resolver, isolated DuckDB executor, typed result/provenance, and tests/docs.
- Ordinary spreadsheet cell/text lookup remains Hybrid; calculation uses this path.

#### Packet 7 forbidden outputs

- User/model SQL, paths/globs/URIs, extensions/pragmas/functions, client-selected table authority, catalog-discovery model call, prose-derived arithmetic, answer-model recalculation, arbitrary local/network access, or DuckDB settings presented as the sole sandbox.

#### Packet 7 ordered actions

1. Define `TableQueryPlan` with authorized table/version IDs, allow-listed columns by stable internal ID, typed predicates/operators/values, aggregations, grouping, ordering, comparison, units, and bounded row/output limit. Reject unknown/additional fields.
2. Bind the tool deterministically for filter/sort/group/sum/count/average/min/max/comparison over CSV/XLSX cells. Ambiguous ordinary lookup stays Hybrid or asks clarification.
3. Resolve IDs server-side to authorized current undeleted manifests and exact immutable Parquet paths/hashes. Recheck ACL before open and after result assembly; client/model paths never participate.
4. Translate the validated plan through an application-owned query builder. Do not accept executable SQL or interpolate identifiers/values.
5. Launch a no-network, no-secret, non-root isolated process/container with only exact read-only artifacts. Preload only qualified bundled requirements; disable external access, autoinstall/autoload, unsigned/community extensions, arbitrary filesystems, `ATTACH`, `COPY`, secrets, and configuration changes; then lock configuration.
6. Set session timezone UTC, explicit decimal precision/scale and rounding policy, thread/memory/temp/scan/row/output limits. Treat DuckDB memory settings as partial; enforce OS resource limits too.
7. Enforce the three-second statement deadline at process level, call interrupt, then kill after bounded grace. Clean/discard the process after timeout/cancellation/escape attempt.
8. Reject missing/stale formula caches, unsupported formula/type, ambiguous/duplicate header reference, mixed units/currencies without explicit conversion, non-finite result, precision/timezone loss, hidden-sheet policy conflict, missing provenance, or over-limit plan.
9. Return deterministic value plus table/version/artifact/schema IDs, workbook/sheet, exact source ranges/cells, operation/predicates/grouping, units/currency, input/output row counts, null handling, rounding, and diagnostics. The answer model may quote/explain but never recalculate.
10. Test Arrow→Parquet→DuckDB cross-reader behavior and all authorization/escape/resource/data fixtures.
11. Append schema/sandbox/limits/calculation/provenance evidence.

#### Packet 7 acceptance checks

- Sum/count/average/min/max/group/filter/sort/comparison fixtures match exact decimal/date/null expected values and source ranges.
- IDOR/revoked/deleted/wrong-current table access returns no artifact/result.
- HTTP/S3/local escape, traversal/symlink/junction, `ATTACH`, `COPY`, extension install/load, config mutation, timeout, memory/temp/row/output abuse all fail closed while the exact allowed artifact still works.
- Formula/cache, duplicate header, hidden sheet, mixed units/currency, timezone/epoch, Arabic/Unicode, and non-finite cases clarify/refuse rather than invent.

#### Packet 7 negative tests

- SQL/path/pragma/function injection, model-selected artifact, stale cache used as value, decimal truncation, answer-model changed total, missing cell provenance, uninterruptible query, or sandbox process reuse after violation fails.

#### Packet 7 stop routes

- Phase 3 artifacts/provenance or authoritative resolver is missing, hostile-access isolation cannot be proven, deadline/kill leaks resources, or cross-reader values are lossy.

#### Packet 7 required evidence

- Plan/result schemas, version/pin/OS isolation configuration, exact limits, authorization/escape/resource matrix, aggregation golden outputs, Parquet cross-reader report, provenance payloads, process cleanup proof, and exact commands.

### Packet 8 — final ablations, immutable holdout, reports, and Phase 5 decision

#### Packet 8 preconditions

- Packets 1–7 pass; frozen configuration and rollback hash exist; holdout manifest has never been opened by tuning/evaluation jobs.
- Representative corpus/index/projection is healthy; signed target, governance, latency/cost, and client decision owners are available.

#### Packet 8 allowed outputs

- Development/qualification ablations, one immutable holdout execution, Phase 4 evaluation/retrieval reports, completed evidence, revised delivery estimate, and Hybrid Pilot continue/pilot decision.
- Corrections to documentation/evidence only after holdout begins; changing runtime config consumes/fails that holdout.

#### Packet 8 forbidden outputs

- Tuning after viewing holdout, repeated holdout runs with changed configuration, cherry-picked slices, graph/Combined/tool/frontend runtime success claims, invented metrics, or setting phase complete before user acceptance.

#### Packet 8 ordered actions

1. Freeze and record code/config/prompt/model/SDK/vector/ParadeDB/index/normalizer/glossary/dataset/fixture hashes, authorization roles, service health, and warm/cold benchmark procedure.
2. On development/qualification data, publish required ablations: embedding decision reference, structure-aware versus fixed chunks, dense-only, BM25-only, populated term-only, dense+term outage, max versus summed variants, static/query-aware RRF, metadata/temporal factors, always/conditional rerank with counterfactuals, MMR/quotas, parents/context, rewrites, Arabic/ta-marbuta/tokenizer/stemmer choices, selective ANN/exact oracle, and structured tables.
3. Publish stage and slice metrics: Recall@K/MRR/nDCG, exact-code/alias, profile fields, authorized candidate recall, temporal/table/refusal/whole-document/media, citation correctness/completeness, zero ACL leaks, p50/p95/deadline, answer/refusal rate, tokens/cost, BM25 index/RAM/latency/projection lag/rebuild/outage, and resource peaks.
4. Re-confirm representative Phase 3 chunk/projection/version/deletion gates and authoritative citation resolution. BM25 snippets never count as evidence.
5. Open the exact sealed holdout once and run the frozen end-to-end retrieval/table qualification. Record all cases, failures, environment, and immutable run ID. No configuration changes or rerun can turn that holdout into a pass.
6. Compare signed gates: zero ACL leaks; citation correctness at least 98%; completeness at least 90%; Hybrid Recall@10 at least 85%; exact-code Recall@5 at least 98%; approved-alias Recall@10 at least 95%; profile gates; signed temporal/refusal/table/latency/cost limits; and degraded-mode correctness.
7. If holdout fails, record no-go. Repair only against development/qualification and require a newly collected, independently sealed SME-approved holdout for a future launch claim.
8. Mark graph/Combined/route/tool/injection/frontend cases as deferred to their owning phases; do not count unexecuted labels as Phase 4 passes.
9. Complete every `Done when` evidence link, managed-environment gaps, deviations/ADR/rollback, Phase 5 inputs, and open blockers.
10. Re-estimate Phase 5/remaining delivery and obtain the client-approved continue-to-Phase-5 versus `0.x Hybrid Pilot` decision. Request explicit user acceptance; do not start Phase 5 in this run.

#### Packet 8 acceptance checks

- The full simpler-baseline/ablation matrix and one frozen holdout run are reproducible from hashes/commands; no split leakage occurred.
- All signed Hybrid/profile/citation/ACL/latency/cost/refusal/table/fallback gates pass, or Phase 4 remains pending with no-go evidence.
- ParadeDB killed/incompatible/late, stale BM25 IDs, Valkey loss/bypass, reranker failure, table refusal, and weak evidence degrade only along documented routes with canonical citations.
- Every final citation opens an authorized current Supabase passage or exact table range, never BM25 text or synthetic embedding context.
- Client decision and revised estimate are recorded before Phase 5; user acceptance precedes status change.

#### Packet 8 negative tests

- Holdout access before freeze, config change/rerun after results, missing baseline/slice, skipped ACL/degradation test, unexecuted Phase 5/6 label counted pass, or subjective unsupported “improvement” fails.

#### Packet 8 stop routes

- Any required real boundary/SME/client decision is unavailable, a launch gate fails after bounded repair, dataset isolation is compromised, or only a fake/skipped result could pass.

#### Packet 8 required evidence

- Frozen manifest/config/run hashes, complete ablation and holdout reports, all stage/slice metrics and confidence intervals, service/resource/cost traces, ACL/citation/fallback fixtures, Phase 3 reconfirmation, no-go/new-holdout record if needed, revised estimate/client decision, exact commands, and explicit user acceptance.

## Cross-packet invariants and ownership

- Supabase current authorized canonical passages and deterministic table values are the only evidence. ParadeDB returns ranks/IDs only; every ID is rechecked before fusion and again before context/citation assembly.
- Profile errors are measured before candidate/ranking blame. Candidate recall is measured before fusion/rerank blame. Coverage/refusal is not a substitute for missing authorization or provenance.
- All variants share one channel cap/deadline; a passage contributes at most once per channel using its best variant rank.
- Every numeric weight/depth/threshold/resource limit comes from this plan or a frozen measured profile with dataset/version evidence.
- Cache can improve latency only. Keys include principal scope and visibility/config versions, cached values are IDs/ranks, and authoritative recheck is mandatory.
- Phase 3 owns chunks, embeddings, typed Parquet, BM25 projection writes, and `Hybrid Ready`; Phase 4 consumes and re-confirms them.
- Phase 4 owns Hybrid candidate queries, typed profile/retrieval/rerank/table contracts, offline qualification prompts/evaluations, frozen profiles, citations, and refusal signals.
- Phase 5 owns LightRAG, graph maps, graph retrieval, and graph evaluation execution.
- Phase 6 owns final query LangGraph, route/correction/escalation budgets, Combined/Composite composition, answer/verifier/summary prompts, SSE/API, production tracing/redaction, feedback, and online evaluators.
- Phase 8 owns the complete frontend/tool UX and client-side rendering tests.
- A label for later-phase behavior is not implementation or passing evidence in Phase 4.
- Phase 4 remains pending until packet 8 evidence and client/user acceptance are complete.

## Phase sequence requirement

Phase 4 implements Hybrid RAG: immutable held-out data; seeded SME glossary/codes/aliases; lightweight contextual vectors; normalized Arabic/mixed Unicode-tokenized ParadeDB BM25 with 75 authorized candidates; filtered-HNSW iterative scans with 100 dense candidates; 30 exact/trigram candidates; max-normalized query variants; bounded temporal multipliers; accuracy-first top-20 OpenAI reranking/counterfactuals; per-field profile and per-query-class tuning; calibrated coverage/refusal; structured tables; benchmarks; and canonical citations.

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

## 6. Hybrid retrieval over canonical Supabase evidence and private BM25

> **Phase 4 ownership note:** Phase 2 owns and has already verified pgvector 0.8+/iterative scans, the exact private ParadeDB/`pg_search` image/extension contract, and the single versioned Arabic-normalization SQL/cross-runtime fixture. Phase 3 owns the durable BM25 projection writer and `Hybrid Ready` verification. Phase 4 consumes those canonical artifacts, implements `Bm25Retriever` candidate queries plus Supabase vector/term RPCs and frozen search profiles, and proves multilingual/selective-filter behavior. Do not install `pg_search` in managed Supabase, create a competing normalizer, or defer a Phase 2/3 compatibility failure.

Use a multi-stage hybrid pipeline. The initial release deliberately combines a few complementary, measurable methods instead of enabling every advanced retriever at once.

### 6.1 Indexed representation

In [`supabase/migrations/`](../../../supabase/migrations/), require pgvector 0.8+ and enable `pg_trgm`; use the separately versioned private ParadeDB schema under [`infra/paradedb/`](../../../infra/paradedb/). Add:

- An HNSW cosine index over embeddings generated from `document title + heading path + passage`. This is lightweight hierarchical metadata context, not LLM-generated Anthropic-style contextual retrieval; claim no published contextual-retrieval gain unless this implementation earns it on the held-out dataset.
- A private ParadeDB `pg_search` index over a derived `bm25_chunks` table keyed by canonical chunk ID. Project separate normalized fields for title/identifiers, heading/approved aliases, and passage body plus document/version ID, language, dates, tags, authority, visibility generation, company-visible flag, and opaque authorized-user scope IDs. The index uses the pinned version's verified Unicode tokenizer, not an English stemmer for Arabic.
- BM25 query construction is application-owned, typed, parameterized, and allow-listed; raw user text never becomes executable SQL or unrestricted ParadeDB query syntax. Apply evaluated field boosts that start with title/identifier above heading/aliases above body, phrase/boolean intent from `QueryProfile`, and only allow-listed metadata/authorization prefilters. Rank with the pinned `pdb.score(key_field)` contract, but use raw BM25 scores only to order the BM25 list before RRF; never mix them numerically with vector/trigram scores.
- Arabic search-only text applies Unicode compatibility normalization, strips tatweel and Arabic combining marks/diacritics, normalizes alef/hamza variants, ya/alef-maqsura variants, and Arabic-Indic/Persian digits before ParadeDB Unicode tokenization. Ta-marbuta equivalence is benchmarked separately and, if promoted, contributes an alternate term rather than destructively changing the sole form. Raw citation text/offsets remain untouched. English/mixed text uses evaluated normalized fields and no claimed stemming gain without evidence.
- Trigram indexes over populated `document_search_terms` and `search_aliases`: filenames, titles/headings, deterministic identifiers/codes, and manually approved aliases. Do not describe this as a general entity channel until a curated canonical entity source exists.
- Metadata/ACL indexes for role, document/version status, source type, language, date, tags, and authority.
- Separate raw passage text and contextual embedding text. Citations always display the original passage, never the synthetic context prefix.
- Embedding, parser, cleaning, Arabic-normalization, chunking, deduplication, and index-version fields so a new strategy can be built alongside the old one and switched only after evaluation.

Filtered HNSW retrieval uses pgvector iterative scans (`hnsw.iterative_scan` with strict ordering by default) inside the same authorization transaction as the security-invoker RPC. Strict ordering orders the approximate candidates found; it does not provide exact recall. Choose `hnsw.ef_search`, `hnsw.max_scan_tuples`, `hnsw.scan_mem_multiplier`, transaction-local `work_mem`, and statement timeout from allow-listed measured selectivity profiles, and continue iterative scanning until the requested candidate floor or bounded scan ends. If too few candidates survive, use exact vector fallback only when the authorized subset is admitted at or below 10,000 rows and the exact query enforces the same ACL/filter/distance expression plus hard statement/work/row bounds; planner statistics are an admission hint, not the safety boundary. Otherwise return weak-evidence diagnostics instead of an unbounded scan. Phase 4 fixtures compare selective ANN with an exact authorized oracle and prove measured recall/candidate sufficiency rather than testing only non-empty unfiltered ANN.

The Phase 2 compatibility evidence must show that local and managed-target Supabase expose pgvector 0.8+ and the required iterative-scan setting, and that the private pinned ParadeDB image exposes the qualified `pg_search`/Unicode/BM25/filter/key-field contracts. Phase 4 fails closed if either prerequisite is missing; it does not rediscover, postpone, or replace the gate.

Consume the Phase 2 Arabic-normalization migration and its conformance fixture of raw→search-form pairs covering diacritics, tatweel, alef/hamza, ya/alef-maqsura, digits, mixed Arabic/English/codes, punctuation, and already-normalized idempotence. Phase 4 tests prove Supabase projection text, core query normalization, and ParadeDB-indexed/query forms are byte-identical for the active normalization/index version; raw text, offsets, and citation display never use the search-only form.

Avoid a cold search-term channel. Before Phase 4 benchmarking, the Knowledge Owner/SME supplies a private seed glossary of product codes, project names, approved acronyms, canonical terms, aliases, language, type, and effective scope through an admin import—not Git. Validate conflicts/cycles/duplicate aliases, require owner/admin approval, and record source/version. Sample the real corpus to version identifier regex/checksum rules. The exact-code and alias subsets must meet Section 1 gates before Hybrid is considered ready; monthly curation is maintenance, not the first population event.

### 6.2 Query analysis

Before retrieval, a small structured query-analysis step returns each value with confidence and provenance (`deterministic`, `approved_alias`, `model_inferred`, or `user_supplied`):

- Query type: exact identifier, factual, semantic/conceptual, multi-part, relationship/multi-hop, broad summary, or structured tabular aggregation.
- Detected query language/configuration; exact terms, quoted phrases, codes, dates, likely entities/approved aliases, requested sources, and metadata filters.
- Temporal intent (`latest`, `current`, `recent`, `as_of`, or none), target date, and which source dates are authoritative (`effective_at`, `published_at`, or document metadata).
- Negation/exclusion scope (`none`, `entity_exclusion`, `policy_exclusion`, or `set_complement`), single-document/section/page scope, media-dependent intent when required evidence exists only in a figure/chart/diagram, and `historical_relationship=true` when relationship/multi-hop intent is anchored to an explicit past date.
- Precomputed LightRAG `hl_keywords` for themes/topics and `ll_keywords` for concrete entities/codes/relations, derived from the same profile used by routing.
- Whether query rewriting/decomposition is justified. Simple questions remain single-query to save tokens; ambiguous or multi-part questions may produce at most three focused variants.
- Retrieval channel weights and candidate limits selected from allow-listed profiles, not arbitrary LLM-generated numbers.

Normalization expands known aliases/acronyms, canonicalizes dates/identifiers, applies the same versioned Arabic search normalizer used by the canonical BM25 projection, and preserves the original query. Future feedback can add approved aliases without changing prompts. Low-confidence inferred filters are not silently applied as hard constraints: the system either retrieves without them, asks a clarification, or records them as soft diagnostics. Low-confidence negation never silently inverts a result set; it asks a scoped clarification or refuses an exhaustive exclusion claim.

Evaluate query analysis independently from routing and ranking. The labeled profile set scores language/configuration, query type, temporal intent/date field, exact codes/numbers, entities/aliases, metadata filters, relationship signal, table intent, negation scope, document/section scope, media dependence, historical-relationship signal, and decomposition count with exact match plus field-appropriate precision/recall/F1. Persist field-level errors and attribute downstream misses to profiling, candidate generation, fusion, reranking, or coverage separately. Confirmed profile failures may become versioned, redacted few-shot examples in the profiling prompt only after SME approval and remain disjoint from the immutable launch holdout.

### 6.3 Candidate generation

The security-invoker Supabase RPC always constrains dense/term results and final candidate resolution by verified Phase 2 identity/session context, ACL/current-version/deletion, authorization snapshot, and typed metadata predicates; the shared API database role or client-supplied caller ID alone is never treated as end-user authorization. Data API execution uses verified JWT/RLS context. Direct/transaction-pooled SQL verifies the token/session in trusted application code, begins one transaction, sets only transaction-local role/claims/GUCs/timeouts, invokes the RPC in that transaction, and clears state by commit/rollback; its login is not a table owner and has neither `BYPASSRLS` nor service-role behavior. Missing, forged, expired, disabled, revoked, cross-scope, stale, leaked-pool, or untrusted context returns zero rows. `Bm25Retriever` receives only server-derived company-visible/opaque user-scope plus allow-listed metadata filters and uses the private read-only role. Because its projection can lag, every returned BM25 ID is batch-rechecked through the authoritative Supabase RPC before fusion/evidence. Retrieve in parallel:

- Dense semantic candidates through pgvector; permissive accuracy-first Phase 4 default maximum 100 after variant deduplication.
- ParadeDB BM25 candidates for lexical relevance, phrases, and approved field boosts; initial maximum 75 authorized survivors after variant deduplication and Supabase recheck.
- Trigram/search-term candidates for misspellings across populated filenames, headings, deterministic identifiers/codes, and approved aliases; initial maximum 30 after variant deduplication.

For multiple query variants, each variant produces bounded candidates and participates in the same fusion process, but the per-channel maxima above apply to the deduplicated accumulator across all variants rather than multiplying by variant count. “Near 100” refers to the dense-channel default; BM25 and term channels remain separately capped, and the pre-fusion union is capped at 205 unique passage IDs. To replenish stale/unauthorized BM25 hits, scan at most 300 BM25 IDs in at most three bounded retrieval rounds per query across variants. Use a relevance-preserving cursor only when the pinned ParadeDB version has a real contract test proving stable order without duplicates/omissions; an ID-only cursor is not assumed to preserve BM25 relevance. Otherwise issue one bounded top-300 query ordered by score then canonical ID. Every bounded page/batch is rechecked through Supabase and unauthorized IDs/scores never reach fusion, prompts, caches, or exported traces. Server-side limits override all client values. Phase 4 may reduce these depths per query class only after recall/latency/cost curves show no material loss; recall discarded before fusion/reranking cannot be recovered. If ParadeDB is unavailable, incompatible, over deadline, or open-circuit, skip the BM25 contribution, record `bm25_unavailable`, and continue visibly with dense plus exact/trigram term retrieval; do not silently relabel that degraded run as full three-channel Hybrid.

### 6.4 Query-aware fusion

Use weighted reciprocal-rank fusion because vector, BM25, and trigram raw scores are not directly comparable:

```text
fused_score =
    vector_weight  / (rrf_k + vector_rank)
  + bm25_weight    / (rrf_k + bm25_rank)
  + term_weight    / (rrf_k + term_rank)
```

Start with `rrf_k=60`, but treat it and channel weights as evaluated configuration. Exact-code/phrase queries emphasize BM25/search-term ranks; conceptual queries emphasize vector rank. For multiple query variants, compute each passage's contribution within a channel as the **maximum** across variants, not the sum, so generic passages cannot accumulate credit merely by weakly matching every rewrite. Then sum the three channel contributions.

Do not add raw constants to RRF magnitudes. Apply only evaluated multiplicative metadata factors to the fused score, with the product clamped to `[1.0, 1.15]`; title/heading alignment, approved authority, and explicit temporal intent may contribute, while current-version status remains a hard filter rather than a boost. Cross-channel/variant agreement is telemetry and a rerank-confidence signal, not an unbounded additive bonus.

Temporal defaults across distinct documents are explicit:

- `latest`: after minimum topical relevance, choose the greatest authoritative `effective_at`, then `published_at`; unknown-dated documents cannot win “latest.”
- `current`: require `effective_at <= now` and `expires_at` absent/future where available, then prefer authority and greatest effective date.
- `recent`: use no hard cutoff unless supplied; apply an evaluated time-decay factor inside the total `1.15` metadata cap.
- `as_of`: hard-filter to records effective/published on or before the target and not expired/superseded by that date; unknown temporal metadata is excluded from strict claims.
- No temporal intent: apply no freshness factor.

All `now` and target-date comparisons use UTC unless `QUALITY_TARGETS.md` signs one company timezone; stored authoritative dates use `timestamptz`. Versioned deterministic date parsers cover mixed Arabic/English Gregorian formats and ambiguous locale fixtures. Hijri dates do not populate authoritative `effective_at` in v1 without a separately approved parser and labeled conformance set.

If equally authoritative distinct documents remain concurrently current or contradict each other, return the conflict with both dates/citations rather than silently selecting one. Deterministic final ties use authority, effective date, published date, then document ID.

### 6.5 Accuracy-first bounded reranking and context selection

After RRF:

1. Collapse exact/near-duplicate clusters and query-variant duplicates while retaining every source/citation provenance record on the representative.
2. Form one top-20 rerank pool from fused passages before final MMR, with a liberal maximum of five passages per document so duplicates cannot crowd out the corpus while the reranker still sees enough same-document alternatives.
3. Start Phase 4 accuracy-first: rerank every non-trivial knowledge query with at least two authorized fused candidates. Multi-part/comparison, temporal, semantic/conceptual, broad synthesis, channel-disagreement, single-channel-winner, and exact-versus-semantic-conflict cases rerank by default. Skip only a trivial exact identifier/quoted-phrase lookup whose required terms/filters are complete and whose winner is independently top-ranked by at least two applicable BM25/term/cross-channel signals. Never decide from numeric BM25 or RRF-score gaps.
4. Make exactly one bounded structured-output Responses operation to the configured pinned OpenAI model through the shared budget/tracing gateway; do not assume a dedicated arbitrary-candidate rerank endpoint. Send the query plus authorized candidate IDs, bounded canonical passage text, and only required metadata, with no tools or external retrieval; the data-governance policy applies exactly as it does to answer generation.
5. Require a strict schema result whose request-specific ID enum contains every supplied candidate exactly once in ranked order with bounded support features. Application validation enforces set equality, uniqueness, response completion, output/input hash, and support bounds. Reject unknown/duplicate/missing/extra IDs, malformed values, refusal/incomplete status, prose-only output, or an over-budget response. Model support is a ranking feature, not a calibrated probability.
6. If the OpenAI reranker is unavailable, invalid, over budget, cancelled, incomplete, version-mismatched, or times out, fall back to deterministic RRF rather than failing retrieval. Record the fallback reason. Disable or explicitly account for SDK/gateway automatic retries so the one-operation/model-call budget is truthful; timeout-after-provider-success and duplicate cost remain observable. Never retry with a local model.
7. Apply per-document/section quotas and query-class-calibrated MMR after reranking so one source cannot fill final context while complementary evidence remains.
8. Search using small passages, then load only the strongest parent sections and adjacent passages required for coherence.
9. Return approximately 8–12 final evidence units, bounded by a token budget, with raw component ranks, fused/rerank scores, decision/fallback reason, source metadata, and citation coordinates.

The v1 `Reranker` implementation is OpenAI-only; do not install, download, or run a local cross-encoder/reranking model. Keep the interface for testing and future provider changes, but changing provider or adding a local model requires user approval, an ADR, data/cost/latency evaluation, and updated release gates.

Phase 4 evaluates `always rerank top 20` as the accuracy reference against the conditional policy. For every skipped case in the development/qualification sets, run the counterfactual once and record whether reranking changes top-1/top-5, nDCG, evidence coverage, final citation support, latency, and cost. Tighten triggers or reduce the pool only when per-query-class curves show no material quality loss under the signed tolerance; never infer safety merely because the pre-rerank winner looked confident. Production records the decision/features, but does not make unbudgeted shadow calls.

### 6.6 Confidence and advanced-method policy

Compute a deterministic `HybridCoverage`:

```text
coverage_score = min(
  required_term_entity_coverage,
  subquestion_coverage,
  min(1, distinct_evidence_count / profile_minimum),
  support_confidence
)
```

Simple queries use `subquestion_coverage=1` and `profile_minimum=1`; relationship candidates require at least two distinct evidence units; broad synthesis requires three sections/documents; multi-part requires one supported unit per subquestion. `support_confidence` is a bounded reranker support feature when run, otherwise `1.0` for an exact phrase/code match or a top passage present in at least two channels, and `0.60` for a single-channel-only winner. It is not asserted to be a calibrated probability. Start with `coverage_score < 0.65` as a development baseline. Calibrate allow-listed thresholds per query class on the development set against supported-answer precision, answer rate/recall, false-supported-answer rate, and unnecessary-refusal rate; confirm one frozen candidate on qualification, then freeze before one final holdout run. Refusal calibration includes insufficient-evidence, contradictory-authority, missing-subquestion, and ACL-filtered cases and weights an unsupported confident answer more heavily than an honest refusal.

For a requested whole-document summary, first resolve exactly one authorized current document version and compute `section_coverage_ratio = covered_major_sections / total_major_sections` from its deterministic heading inventory. Claim a full-document summary only when the bounded 8–12 evidence-unit/token budget contains at least one adequate passage for every major section and `section_coverage_ratio=1.0`; otherwise return a scoped refusal listing uncovered headings/page ranges and suggest section/range questions. No map-reduce, recursive summary tree, or RAPTOR summary path is allowed in v1.

Negation/exclusion queries do not infer a complete complement from ordinary top-k retrieval. They either obtain a precise user scope, use deterministic table/enumeration evidence that proves the closed set, or return a clarification/scoped refusal. Media-dependent questions whose required evidence is only inside a figure/chart/diagram return the signed v1 limitation notice; adjacent captions/OCR may answer only the text they actually contain.

All retrieval rewriting and route escalation share the single global correction budget from Section 1. Weak evidence without relationship/multi-hop signals may use one same-route rewrite/retrieval correction. Weak Hybrid **with** any retained relationship/multi-hop signal may instead spend that correction to escalate to Combined. No path receives both corrections; after the budget is spent, return verified partial/insufficient evidence rather than forcing an answer.

Do not add HyDE, RAPTOR, SPLADE, ColBERT, or learned-to-rank in v1. Preserve extension points and evaluate them only when the golden dataset identifies a concrete failure:

- HyDE or multi-query RAG-Fusion for vocabulary mismatch that normal rewriting does not fix.
- RAPTOR or summary vectors for broad cross-document synthesis failures.
- SPLADE or ColBERT for lexical/token interaction failures that ParadeDB BM25 plus dense retrieval cannot solve.
- Learned-to-rank only after enough trustworthy feedback labels exist.

Tune on development/qualification data and use the final holdout once after freezing configuration. By query class, benchmark the versioned Arabic normalizer and optional ta-marbuta expansion, ParadeDB Unicode tokenization/BM25 field boosts/phrase behavior for English/Arabic/mixed text, highly selective BM25 metadata/ACL prefilter plus Supabase recheck and filtered-HNSW iterative scans/`ef_search` profiles, exact-fallback caps, dense/BM25/term candidate depths, populated glossary/identifier coverage, max-versus-summed query-variant contributions, `rrf_k`, channel weights, bounded metadata/temporal multipliers, permissive-versus-tight rerank triggers and pool size, MMR lambda/quotas, parent/context size, and coverage/refusal thresholds. Publish quality, p50/p95, token/cost, BM25 index size/rebuild/sync lag, answer-rate, and counterfactual curves per query class. Do not assume the pinned version exposes configurable BM25 `k1`/`b`; verify APIs from primary docs before treating any parameter as tunable. No method is promoted because it sounds advanced; it must beat the simpler pipeline on unseen evaluation data without weakening refusal/ACL behavior.

### 6.7 Structured table retrieval and calculation

Implement `structured_table_query` as a registry-backed internal tool that is deterministically bound when the typed profile requires filter, sort, group, sum, count, average, min/max, or comparison over CSV/XLSX cells; it does not incur catalog discovery. Ordinary spreadsheet lookups still use Hybrid passages.

The model emits a validated declarative `TableQueryPlan` containing authorized table/version IDs, stable allow-listed columns, typed predicates, allow-listed aggregations, grouping, ordering, comparison, units, and row/output limit. It never emits SQL, paths, globs, URIs, extensions, pragmas, or functions. The server resolves IDs to exact authorized current immutable Parquet artifacts and rechecks ACL/current/deletion before open and result assembly. Run DuckDB in a no-network/no-secret OS-isolated process/container; read-only/allow-listed paths, disabled external access/autoload/autoinstall/unsigned extensions/filesystems, and locked configuration are defense in depth. Enforce bounded threads/memory/temp/scanned bytes/rows/output and the three-second statement deadline with a process timer, interrupt, and bounded kill grace because DuckDB has no assumed general SQL statement-timeout guarantee. Results include table/version/artifact/schema IDs, workbook/sheet, exact source ranges/cells, operation/predicates/grouping, units/currency, input/output rows, rounding/null policy, and deterministic values so the final answer can cite both calculation and source cells. Missing/stale formula caches, unsupported formulas/types, ambiguous/duplicate headers, mixed units/currencies, non-finite values, precision/timezone loss, hidden-sheet conflict, or insufficient provenance produce clarification/refusal rather than an invented calculation.

## 11. LangSmith, prompts, cost, and evaluation

> **Phase 4 ownership note:** Implement the dataset specification, split isolation, retrieval/query-profile/chunk/table evaluations, ablations, quality/cost reports, and frozen Hybrid configuration. The signed data-governance gate is a Phase 3 prerequisite. Phase 6 owns final query-agent prompt orchestration, run tracing, online feedback wiring, and agent/API evaluation while consuming the frozen Phase 4 retrieval artifacts.

Store only the Phase 4 query-profile and rerank prompt definitions under [`apps/agents/src/smart_rag_agents/prompts/`](../../../apps/agents/src/smart_rag_agents/prompts/) with version IDs and changelogs. Phase 6 owns final answer/verifier/summary/tool prompts and environment promotion.

Trace Phase 4 qualification/evaluation runs with dataset split, query/profile IDs, model/prompt/index versions, candidate/channel counts, rerank/fallback decision, latency, tokens, and cost. Do not wire the production query graph or raw private payload tracing here; Phase 6 owns production run tracing/redaction.

Phase 3 must already have created and obtained owner/client sign-off for [`docs/security/OPENAI_DATA_GOVERNANCE.md`](../../../docs/security/OPENAI_DATA_GOVERNANCE.md) and [`docs/security/SUBPROCESSOR_GOVERNANCE.md`](../../../docs/security/SUBPROCESSOR_GOVERNANCE.md). Phase 4 consumes and enforces the approved provider scope, OpenAI API retention/training terms, region/project controls, allowed/prohibited/review categories, PII handling, and `external_processing_allowed` decision before embeddings or reranking. Missing, prohibited, unknown, or contradictory decisions remain quarantined; Phase 4 must not recreate the packet or claim provider terms beyond the signed settings.

The evaluation dataset is a Phase 4 blocker, not an afterthought. The client-appointed Knowledge Owner/SME owns labels and commits 12–20 review hours; the developer owns tooling, sampling, and reproducibility. Phase 2 first freezes the smaller embedding-qualification slice from Section 1; it is tuning/selection data and cannot appear in the final launch holdout. [`docs/evaluation/DATASET_SPEC.md`](../../../docs/evaluation/DATASET_SPEC.md) defines answer/source ground truth, acceptable variants, atomic links, expected refusal/route, expected query-profile fields/confidences/provenance, language, temporal intent, codes/entities/aliases, filters, ACL actor/snapshot, source-family ID, chunk/parent ground truth where relevant, and adjudication/disagreement. Minimum complete initial corpus: 25 exact-code/value, 20 alias, 15 typo, 35 semantic factual, 20 Arabic/mixed-language, 15 highly selective metadata-filter, 15 latest/as-of, 20 multi-part/comparison, 30 relationship, 30 multi-hop, 15 broad synthesis, 20 tabular aggregation, 20 insufficient-evidence/contradictory-authority refusal, 20 graph-mapping/entity-collision/version-switchover, 20 ACL-negative, 20 rewrite/profile-fidelity, 10 negation/exclusion, 10 single-document summary (five complete-coverage and five scoped-refusal), 10 mixed-locale temporal, five media-dependent limitation, and 30 prompt/graph-injection cases: 405 total. Before labeling, assign source-family-disjoint development/qualification/holdout counts in the signed dataset spec; use the cheap-model protocol's 50/25/remainder default when no alternate allocation is approved. LangSmith split metadata is validated against immutable project manifests because split labels can overlap. No tuning, embedding selection, threshold calibration, glossary seeding, or few-shot example may appear in the immutable launch holdout. The holdout is opened once after freeze; a failed run is not tuned and rerun.

Create datasets and CI/nightly evaluations for:

- Chunking/cleaning contracts: retained-content coverage after declared boilerplate removal, heading/reading-order accuracy, intact table/list units, prose token distribution, overlap, parent reconstruction, citation-coordinate fidelity, exact/fuzzy duplicate precision/recall, and retrieval ablation against naive fixed-size chunks.
- Query-profile per-field exact match/precision/recall/F1 for language/configuration, query type, temporal intent/date/timezone, codes/numbers, entities/approved aliases, filters, relationship/table signals, negation scope, document/section scope, media dependence, historical-relationship signal, and decomposition; report retrieval failures by the first failing stage.
- Per-channel/fused Recall@K and MRR/nDCG; raw versus normalized Arabic BM25 quality and ta-marbuta ablation; English/mixed BM25 quality; exact-code/seeded-alias/typo accuracy; selective-filter BM25/HNSW recall and candidate sufficiency; BM25 projection lag/rebuild/failure behavior; temporal accuracy; ACL correctness; graph entity/path recall; and complete route-matrix accuracy.
- Ablations for small-versus-large/reduced-dimension embeddings on the Phase 2 qualification slice, dense-only, BM25-only, populated trigram-only, dense+term degradation without BM25, summed-versus-max variant RRF, static/query-aware RRF, bounded metadata/freshness multipliers, always-rerank versus conditional decisions/pool sizes with skipped-case counterfactuals, parent expansion, query-class MMR, query rewrites, global steering, naive Combined union, and resolved-path Combined fusion.
- Accuracy, citation quality, p50/p95/deadline behavior, graph-survival/partial-readiness behavior, OpenAI tokens/cost including LightRAG internal/indexing calls, and fallback for each profile; promote a more complex method only when its measured gain justifies cost.
- Answer faithfulness, atomic-link and composed-inference support, deterministic/table-value correctness, citation correctness/completeness, refusal on insufficient evidence, role enforcement, and run ownership.
- Original-to-rewrite fidelity, Hybrid-to-Combined correction precision/recall, profile-keyword pass-through with zero hidden LightRAG keyword calls, statement/chunk-to-passage mapping precision/coverage, entity do-not-merge rules, atomic version switchover, graph-eligibility isolation, deleted-source suppression, and query idempotency/reconnect.
- Prompt injection fixtures covering direct instructions in PDF/HTML/OCR, citation forgery, tool-call inducement, adversarial entity/relation names, graph-extraction poisoning, and frontend XSS payloads.
- Tool discovery precision, tool-call success, unnecessary tool disclosure, and token reduction.
- Malware/quarantine, parser-sandbox escape/resource fixtures, SSRF redirect/DNS-rebinding cases, OCR/parser fixtures, and re-ingestion/deletion idempotency.

Phase 4 builds the shared labels/specifications for the complete evaluation program but executes only Phase 4-owned chunk/retrieval/profile/rerank/refusal/table/citation/ACL/fallback evaluations. Graph mapping/entity/path, Combined fusion/global steering, complete route matrix, production query idempotency/reconnect, tool discovery, final answer/verifier, frontend XSS, and other later-phase runtime evaluations remain explicitly `deferred_owner` evidence for Phases 5, 6, and 8. Unexecuted later-phase cases do not count as Phase 4 passes.

Define the feedback taxonomy and curation contract for “chunk/cleaning loss,” “profile field wrong,” “candidate miss,” “wrong rerank,” “bad refusal/overconfident answer,” “missed relationship,” “wrong route,” “wrong calculation,” “bad citation,” and “insufficient graph.” Phase 6 wires feedback into LangSmith/Supabase and bounded online evaluators. Approved aliases and confirmed failures become a versioned post-launch regression set without contaminating the immutable holdout; any profile/normalizer/chunking/threshold change requires versioned evaluation before release.

## Phase deliver, review, and done gate

### Phase 4 — Hybrid RAG

- Deliver: immutable held-out dataset plus labeled query profiles/refusals; private SME glossary/code/acronym seed and import; versioned Arabic normalizer/cross-runtime conformance fixture; private pinned ParadeDB `Bm25Retriever` with typed queries, field boosts, Unicode tokenization, authorization prefilter plus Supabase recheck, projection/rebuild telemetry, and outage fallback; lightweight contextual HNSW with filtered iterative scans and bounded 100/75/30 dense/BM25/term depths; UTC/company-timezone temporal metadata; negation/document-scope/media/historical profile fields; whole-document section-coverage proof and scoped refusal; max-normalized variant RRF; accuracy-first top-20 OpenAI reranking with schema validation/RRF fallback and skipped-case counterfactual report; query-class MMR/parent expansion; profile/tunable/coverage calibration report; tables; diagnostics/citations; and a Phase 4 delivery re-estimate/Hybrid-Pilot decision record.
- Review: chunking baseline impact, small/large embedding decision, Arabic normalization/ta-marbuta and multilingual BM25 expectations, ParadeDB field boosts/tokenizer/query safety/pin, selective-filter/candidate-depth/recheck recall, projection lag/index size/rebuild/outage, glossary/identifier/alias coverage, per-field profile errors, negation and whole-document-summary refusal behavior, media limitations, mixed-locale temporal accuracy, variant bias, `rrf_k`/weights/multipliers, permissive rerank value and safe skip conditions, MMR/context, coverage answer/refusal curves, table results, ACL, cost, latency, and the proceed-to-Phase-5 versus 0.x-pilot decision.
- Done when: all Section 1 Hybrid/code/alias/BM25 gates pass and Phase 3 chunk/projection gates are re-confirmed on representative indexed fixtures; the 405-case corpus has approved source-family-disjoint development/qualification/one-use holdout manifests and no leakage; profile fields including negation/document/media/historical signals meet signed thresholds with first-failure attribution; Data API/direct pooled identity protocols, transaction-local HNSW settings, private typed BM25 queries, and Supabase batched recheck return zero unauthorized/stale/deleted/wrong-current evidence, retain signed recall under selective filters against an exact oracle, and obey 100/75/30, 205-union, 300-scan/three-qualified-round, exact-fallback, and deadline bounds; normalized Arabic/mixed BM25 and UTC-anchored temporal cases beat declared baselines; projection lag/rebuild/index resources fit signed targets; killed/incompatible/late ParadeDB produces observable dense+term degradation without uncited evidence; full-document summary fixtures require section coverage `1.0` or scoped guidance; negation fixtures clarify/prove/refuse without confident inversion; media-dependent fixtures return the signed limitation; one-operation strict-set-equality OpenAI reranking plus deterministic fallback, MMR/quotas, and authorized parent expansion beat simpler methods within signed cost/latency; every tightened trigger/depth is justified by counterfactual curves; coverage/refusal thresholds are frozen before the single immutable holdout; the OS-isolated declarative table path produces exact typed values/ranges or fails closed; citations open authorized current Supabase passages/ranges rather than BM25 snippets/context prefixes; no local reranker, advanced prohibited method, ungrounded map-reduce, or later-phase runtime exists; all signed ACL/citation/recall/profile/latency/cost/refusal/table/fallback gates pass on the frozen holdout or the phase records no-go; and the revised estimate plus client-approved continue/pilot decision and explicit user acceptance are recorded before Phase 5.
