---
title: Quality, capacity, cost, and launch targets
owner: product-owner / engineering-lead
status: accepted
last-reviewed: 2026-08-12
audience: client-approver, engineering
provenance: .cursor/plans/hybrid-graph-rag/00-global-contracts.md (provisional measurable targets)
approval_status: accepted
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-12"
decision_text: "approved"
---

# Quality, capacity, cost, and launch targets

This document is the Phase 1 canonical record of provisional launch gates copied from the [global contracts](../.cursor/plans/hybrid-graph-rag/00-global-contracts.md) without changing values or meaning. On 2026-08-12 the user approved all provisional defaults with the exact message `approved` (no replacements). Rows below are `accepted` for Phase 1 sign-off; measurement and later-phase verification remain required where noted.

## How to read a row

| Column | Meaning |
| --- | --- |
| ID | Stable target identifier |
| Target | Exact provisional value |
| Unit | Measurement unit |
| Provenance | Source contract location |
| Approval | `proposed` until sign-off; then `accepted` with approver/date |
| Measure in | Owning measurement phase |
| On failure | Required response |

## 1. Capacity envelope

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-CAP-001 | 10,000 Hybrid document versions | document versions | global contracts §Provisional measurable targets | accepted | user (Cursor chat) | 2026-08-12 | Phase 9 load | Reduce documented envelope or resize infra before staging |
| QT-CAP-002 | 1,000,000 canonical chunks | chunks | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 9 load | Reduce envelope or resize before staging |
| QT-CAP-003 | 25 concurrently active users | users | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 9 load | Open multi-host/isolation review when triggers fire |
| QT-CAP-004 | 5 simultaneous query runs | concurrent runs | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 9 load | Same as QT-CAP-003 |
| QT-CAP-005 | 2,000 current document versions (initial graph-eligible) | document versions | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 graph onboarding | Raise only if clean-workspace rebuild meets 7-day SLO and maintenance budget |
| QT-CAP-006 | 200,000 graph source chunks (initial) | chunks | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Same as QT-CAP-005 |

## 2. Embedding qualification (Phase 2 gate)

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-EMB-001 | Frozen embedding-qualification slice ≥20 Arabic/mixed cases plus representative English semantic, exact-identifier, and vocabulary-mismatch cases; disjoint from launch holdout | cases / split hygiene | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 2 before bulk embed | Block bulk embedding until slice exists |
| QT-EMB-002 | Bake-off: `text-embedding-3-small` @1536 vs `text-embedding-3-large` @1536 and ≥1 lower dimension via OpenAI `dimensions`; pin winner model/snapshot or approved alias, dimension, `vector` vs `halfvec`, distance operator, index version from per-language Recall@10/MRR/nDCG, cost, latency, storage | ADR decision | global contracts; [ADR-embedding-model-dimension.md](./adr/ADR-embedding-model-dimension.md) (experiment plan) | accepted | user (Cursor chat) | 2026-08-12 | Phase 2 | Do not proceed with bulk embed on reputation alone |
| QT-EMB-003 | At full envelope, approved combined steady-state vector working set ≤60% of selected database RAM with documented maintenance headroom (includes LightRAG vectors); extrapolate via `pg_relation_size` on seeded index | % of DB RAM | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 2 | Reduce dimensions/envelope, qualify `halfvec`/quantization without unacceptable per-language recall loss, or resize |

## 3. Route latency, deadlines, model calls, and tools

### 3.1 Latency (p95)

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-LAT-001 | Hybrid: first evidence/status ≤2 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Tune or reduce envelope; do not silently raise gate |
| QT-LAT-002 | Hybrid: first answer token ≤5 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-LAT-003 | Hybrid: completion ≤20 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-LAT-004 | Combined: first answer token ≤10 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/6/9 | Same; qualification forbids duplicate LightRAG keyword-extraction call |
| QT-LAT-005 | Combined: completion ≤35 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/6/9 | Same |
| QT-LAT-006 | Structured-table: deterministic result ≤5 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-LAT-007 | Structured-table: first answer token ≤8 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-LAT-008 | Structured-table: completion ≤20 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-LAT-009 | Graph inspection: bounded view ≤5 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Same |
| QT-LAT-010 | Composite: first answer token ≤12 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-LAT-011 | Composite: completion ≤40 | seconds p95 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |

### 3.2 Hard query deadlines and recursion

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-DL-001 | Hybrid hard deadline 25 | seconds | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Return verified partial or insufficient evidence |
| QT-DL-002 | Combined hard deadline 45 | seconds | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-DL-003 | StructuredTable hard deadline 30 | seconds | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-DL-004 | Composite hard deadline 50 | seconds | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-DL-005 | Graph inspection hard deadline 10 | seconds | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/6/9 | Same |
| QT-DL-006 | At most 1 routing/retrieval correction | corrections | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6 | Exhaustion → verified partial/refusal |
| QT-DL-007 | At most 3 subquestions | subquestions | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6 | Same |
| QT-DL-008 | LangGraph `recursion_limit` 24 | supersteps | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6 | Same |

### 3.3 Model-call and tool ceilings

Count every gateway model invocation (query prep/routing/rewriting, LightRAG callbacks, rerank, answer, summary, verifier).

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-MC-001 | Hybrid max 7 model calls (target ≤6; 7th only for same-route correction second rerank or due summary that cannot be deferred) | calls/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Verified partial/refusal |
| QT-MC-002 | Combined max 8 model calls | calls/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-MC-003 | StructuredTable max 6 model calls | calls/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-MC-004 | Composite max 9 model calls | calls/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-MC-005 | Inspection max 3 model calls | calls/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-MC-006 | Query prep combines rewrite/profile into one structured call when both needed | calls | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6 | N/A (design rule) |
| QT-TL-001 | At most 4 tool executions (5 for Composite) | tools/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Verified partial/refusal |
| QT-TL-002 | At most 1 optional discovery/selection model round | rounds/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6 | Same |
| QT-TL-003 | At most 1 side-effecting tool | tools/query | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6 | Same |

## 4. BM25 qualification

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-BM25-001 | Pinned ParadeDB/`pg_search` version + image digest indexes full authorized text projection with Unicode tokenization, versioned Arabic normalization, field boosts, phrase/boolean queries, metadata/ACL prefilters, stable canonical IDs | qualification pass/fail | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 2/4 | `Hybrid Ready` blocked without verified BM25 projection |
| QT-BM25-002 | At 1,000,000-chunk envelope: measure index size/RAM, p95 top-75 latency, write throughput, outbox lag, clean rebuild duration | measured suite | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Record assumptions until measured; reduce envelope or resize |
| QT-BM25-003 | Normal ingestion p95 BM25 projection lag &lt;5 | minutes | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3/9 | Investigate outbox; ACL safety remains immediate via Supabase recheck |
| QT-BM25-004 | Deletion/ACL safety immediate through mandatory Supabase recheck even while async purge catches up | boolean | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3/4/9 | Treat as security defect; never rely on BM25 alone |

## 5. Ingestion and graph throughput

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-ING-001 | ≥500 text-based pages/hour through Hybrid readiness on selected launch hardware | pages/hour | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3/9 | Resize or reduce advertised throughput |
| QT-ING-002 | ≥100 OCR pages/hour through Hybrid readiness | pages/hour | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3/9 | Same |
| QT-ING-003 | LightRAG throughput/cost reported separately (extraction-model limited) | report | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Do not fold into Hybrid page/hour claim |
| QT-GR-001 | Graph throughput: current document versions/hour through mapping-verified `Graph Ready` under concurrency-one writer, plus cost/version; admin UI shows backlog + rolling ETA | versions/hour + cost | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Owner-approved maintenance for bulk onboarding |
| QT-GR-002 | If 2,000-document envelope cannot become Graph Ready within 7 days at measured throughput: reduce advertised graph envelope or fund/approve different graph-ingestion design before onboarding | days | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Block graph onboarding until remediated |
| QT-GR-003 | Graph deletion/ACL enforcement immediate at canonical resolver | boolean | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Security defect |
| QT-GR-004 | Targeted LightRAG cleanup verifies within 24 hours | hours | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Quarantine graph service as required |
| QT-GR-005 | Dirty changes consolidated into clean-workspace rebuild within 7 days | days | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Reduce envelope or fund rebuild |
| QT-GR-006 | Monthly maintenance reserve ≥ `max(USD 800, 4 × measured full-rebuild cost)` before graph launch; reduce envelope if one rebuild cannot finish in 7 days | USD / month formula | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off; numeric eval after Phase 5 measure | Formula unevaluable until measured rebuild exists |
| QT-GR-007 | Cleanup/rebuild bypasses normal ingestion limits; if reserve unavailable, canonical deletion still succeeds but graph stays quarantined until funded cleanup completes | policy | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/9 | Quarantine, do not fake Graph Ready |

## 6. Cost ceilings (distinct commitments)

Normal-operation OpenAI spend and the graph compliance/maintenance reserve are **separate commitments**. Normal budgets must not consume the reserve. The reserve may be materially larger than normal operation.

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-COST-001 | Normal operation ceiling: USD 200 / month | USD/month | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off; enforce Phase 6 | Reject/pause normal spend when durable budget exhausted |
| QT-COST-002 | Normal ingestion ceiling: USD 20 / ingestion day | USD/day | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off; enforce Phase 3/6 | Same |
| QT-COST-003 | Graph compliance/maintenance reserve: `max(USD 800, 4 × measured full-rebuild cost)` / month; visible in usage dashboard; not consumable by ordinary chat/ingestion | USD/month formula | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off of formula; Phase 5+ for measured term | Quarantine graph until funded; do not merge with QT-COST-001/002 |
| QT-COST-004 | Before first bulk onboarding, document scale-trigger candidates: domain/workspace sharding, dedicated managed LightRAG PostgreSQL behind `GraphRetriever`, evaluated incremental compaction/rebuild | decision packet | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5 before bulk | Do not start 7-day/rebuild trigger review from zero |

## 7. Chunking gate

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-CHK-001 | Versioned structure fixtures preserve heading ancestry, list items, table headers/rows/cells, page/sheet/slide/URL spans, reading order; zero orphaned or unmarked/unreconstructable mid-row/mid-item splits | fixture pass | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3 | Fail chunking gate |
| QT-CHK-002 | ≥90% of ordinary prose passages in 200–400 embedding-token target | % passages | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3 | Retune chunker |
| QT-CHK-003 | No normal passage exceeds 600 embedding tokens | tokens | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3 | Fail or record governed exception with provenance |
| QT-CHK-004 | Every exception/duplicate suppression has recorded provenance | boolean | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3 | Fail gate |
| QT-CHK-005 | Fuzzy duplicate suppression on labeled fixtures: ≥99% precision and ≥85% recall; if precision misses, use exact-only until retuned | precision/recall | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 3 | Fall back to exact-only |

## 8. Evaluation and query-profile gates

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-EVAL-001 | Zero ACL leaks | count | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 9 (and earlier security suites) | Block release |
| QT-EVAL-002 | Citation correctness ≥98% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6/9 | Fail quality gate |
| QT-EVAL-003 | Citation completeness ≥90% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6/9 | Same |
| QT-EVAL-004 | Answer faithfulness ≥90% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6/9 | Same |
| QT-EVAL-005 | Routing accuracy ≥90% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/9 | Same |
| QT-EVAL-006 | Hybrid Recall@10 ≥85% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-EVAL-007 | Exact-identifier/code Recall@5 ≥98% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-EVAL-008 | Approved-alias Recall@10 ≥95% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/9 | Same |
| QT-EVAL-009 | Combined improves relationship/multi-hop success by ≥10 percentage points over Hybrid alone without violating latency/cost ceilings | percentage points | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 5/6/9 | Do not launch Combined as default if unmet |
| QT-QP-001 | Language/configuration accuracy ≥95% | % | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6 | Score profile fields before blaming ranking |
| QT-QP-002 | Temporal-intent macro-F1 ≥90% | macro-F1 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6 | Same |
| QT-QP-003 | Exact-code/date extraction F1 ≥98% | F1 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6 | Same |
| QT-QP-004 | Entity/approved-alias extraction macro-F1 ≥90% | macro-F1 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6 | Same |
| QT-QP-005 | Metadata-filter precision and recall ≥95% | precision/recall | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6 | Same |
| QT-QP-006 | Query-type/relationship/table/decomposition macro-F1 ≥90% | macro-F1 | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4/6 | Same |

## 9. Temporal policy

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-TZ-001 | UTC for storage and for `now`, `latest`, `current`, `recent`, `as_of` comparisons unless owner signs one alternate company timezone here | timezone | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off; enforce Phase 4 | Do not invent local TZ |
| QT-TZ-002 | Source date parsing deterministic and versioned; mixed Arabic/English Gregorian formats require fixtures | fixture contract | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 4 | Fail temporal fixtures |
| QT-TZ-003 | Hijri dates are **not** authoritative `effective_at` values in v1 unless a separately signed parser/fixture contract is approved | policy | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1/4 | Reject Hijri as authoritative without signed contract |

## 10. Availability (single-host v1)

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-AVL-001 | Best-effort service | class | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off | Document expectation |
| QT-AVL-002 | RTO ≤4 hours | hours | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 9/10 drills | Incident miss opens multi-host ADR path |
| QT-AVL-003 | RPO ≤24 hours | hours | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 9/10 drills | Same |
| QT-AVL-004 | Brief health-gated deployment interruption accepted | policy | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 10/11 | N/A |

Availability and workload-isolation **triggers** (exact copy) live in [AVAILABILITY_AND_ISOLATION_TRIGGERS.md](./architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md). Crossing a trigger opens a multi-host availability ADR within ten business days.

## 11. Schema and API compatibility

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-COMPAT-001 | Schema and independently deployed API/frontend contracts evolve additively; expand → deploy compatible code/backfill → contract across separate releases; destructive DDL never shares a release with its expansion | policy | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 2+; ADR in Phase 1 packet 5 | Block incompatible release |
| QT-COMPAT-002 | OpenAPI and SSE fields/events backward-compatible within a major version; staging proves old-slot/new-schema plus Vercel/API version-skew before production | policy | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 10 | Block production promotion |

## 12. V1 media limitation (signed non-goal)

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-MEDIA-001 | V1 indexes text, OCR output, typed tables, and adjacent captions only | scope | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 1 sign-off; UX Phase 8 | Do not invent figure interpretations |
| QT-MEDIA-002 | Answers whose material evidence exists only inside a figure, chart, diagram, or non-OCR image return an explicit limitation notice | UX behavior | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Phase 6/8 | Limitation notice required; no hallucinated visual read |
| QT-MEDIA-003 | Vision captioning is out of v1; promotion trigger recorded in [ADR-vision-captioning.md](./adr/ADR-vision-captioning.md) (planned Phase 1 packet 5 draft) | ADR | global contracts | accepted | user (Cursor chat) | 2026-08-12 | Client-funded later | Do not enable without signed ADR |

## 13. Sign-off checklist (Packet 1)

The following require explicit user approval before Packet 1 and Phase 1 can advance:

1. All numeric targets above (or recorded replacements with IDs updated).
2. Distinct normal ceilings (QT-COST-001/002) vs graph reserve formula (QT-COST-003).
3. V1 media limitation (QT-MEDIA-*).
4. UTC temporal policy and non-authoritative Hijri (QT-TZ-*).
5. RTO/RPO and availability/isolation triggers.
6. Dated Hybrid Pilot decision criteria in [ADR-hybrid-pilot-release-cut.md](./adr/ADR-hybrid-pilot-release-cut.md).

## 13. Retention defaults (Phase 2 Packet 5)

| ID | Target | Unit | Provenance | Approval | Approver | Approval date | Measure in | On failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QT-RET-001 | Undeleted corpus retention default 365 days (`company_settings.retention_days`) | days | Phase 2 Packet 5 / global contracts | accepted as Phase 1 default | engineering-lead | 2026-08-13 | Phase 2 schema; purge later | Do not invent alternate without client sign-off |
| QT-RET-002 | Never-finalized quarantine TTL default 24 hours (`quarantine_ttl_hours`) | hours | Phase 2 Packet 5 | accepted as Phase 1 default | engineering-lead | 2026-08-13 | Packet 5 cleanup | Raise only via company_settings |
| QT-RET-003 | Company legal hold flag default false (`legal_hold_enabled`); holds table is Phase 2 structure only | policy | Phase 2 Packet 5 | accepted | engineering-lead | 2026-08-13 | Later purge/offboarding | Purge must honor holds when implemented |

## Decision record

| Field | Value |
| --- | --- |
| Decision | Approve defaults — exact user message: `approved` |
| Approver name | user (Cursor chat; no legal name provided) |
| Approval date | 2026-08-12 |
| Replacements (if any) | none |
| Evidence link | [phase-01-foundation-evidence.md](./development/phase-01-foundation-evidence.md) |

## Related documents

- [Hybrid Pilot ADR](./adr/ADR-hybrid-pilot-release-cut.md)
- [Risk register](./development/RISK_REGISTER.md)
- [Availability and isolation triggers](./architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md)
- [Phase 1 foundation evidence](./development/phase-01-foundation-evidence.md)
