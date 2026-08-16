---
title: Risk register (Phases 1–5)
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering, client-approver
---

# Risk register (Phases 1–5)

Living register for launch-blocking and delivery risks after Phases 1–5
engineering close. BM25 full-envelope resource/rebuild values and graph
rebuild cost remain **unmeasured**. Real company content remains
**prohibited**. Continue-to-v1 is recorded; production v1 labeling is still
forbidden.

| ID | Risk | Owner | Probability | Impact | Mitigation | Trigger | Review date | Evidence link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Client does not sign provisional quality/cost/capacity targets; Phase 1 blocked | product-owner | Low (closed) | High | Signed 2026-08-12 via `approved` | Closed for Packet 1 | 2026-08-12 | [QUALITY_TARGETS.md](../QUALITY_TARGETS.md); [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md) |
| R-02 | BM25 full-envelope index size/RAM/rebuild duration still unknown. Hybrid engineering-close used live open-split retrieve on the compact synthetic sidecar; that does not measure envelope BM25 resources | engineering-lead | High | High | Qualify pinned ParadeDB digest; measure at envelope in Phase 9; keep Supabase recheck authoritative. Do not treat Packet 9 Recall@K as QT-BM25-* | BM25 qualification fails QT-BM25-* | 2026-08-16 | [QUALITY_TARGETS.md](../QUALITY_TARGETS.md) QT-BM25-*; [BM25_PROJECTION_CONTRACT.md](../retrieval/BM25_PROJECTION_CONTRACT.md); [PHASE4_RANKED_IDS.md](../evaluation/PHASE4_RANKED_IDS.md) |
| R-03 | Graph rebuild duration/cost still unmeasured. Advertised envelope **reduced to 15** labeled `graph_mapping` documents; source-chunk capacity unverified; bulk onboarding blocked. Reserve remains USD 800 floor (`4× measured` unevaluable) | engineering-lead | Medium (envelope reduced) | High | Keep 15-doc advertised cap; measure rebuild before any raise; reserve ≥ max(800, 4× cost); quarantine unfunded rebuilds | Attempt to bulk-onboard or raise toward 2,000 / 200,000 without a measured rebuild | 2026-08-16 | [PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md); [SCALING_OPTIONS.md](../graph/SCALING_OPTIONS.md); QT-GR-*; QT-COST-003 |
| R-04 | Local Windows/Docker Desktop resources below 16 GB / 4 cores / 40 GB free; foundation startup fails | engineering-lead | Low (this host ran Phases 1–5) | Medium | Documented minimums; prefer WSL2 ext4; stop with exact prerequisite rather than fake services. Envelope RAM still unverified | Other host startup failure or envelope RAM miss | 2026-08-16 | Phase 1 packet 3/6 evidence; Phases 1–5 local stack on this developer host |
| R-05 | Org provider settings still unverified; real company content remains prohibited (deny-by-default). Phase 6 answering must not ingest client files | product-owner | Medium | High | Keep `real_company_content_external_processing=prohibited` until provider matrix rows are `verified` | Attempt to process real corpus before provider verification | 2026-08-16 | [OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md); [phase-03-ingestion-evidence.md](./phase-03-ingestion-evidence.md); [PHASE6_HANDOFF.md](../graph/PHASE6_HANDOFF.md) |
| R-06 | Continue-to-v1 or reduced GraphRAG silently treated as production v1 or as a Hybrid Pilot | product-owner | Medium | High | Vote recorded 2026-08-16: continue toward production v1 with reduced GraphRAG. Production-label prohibition remains. Hybrid Pilot still needs Phase 6 thin chat + Phase 8 UI | Marketing, contract, or UI copy uses production v1 or Hybrid Pilot without those phases | 2026-08-16 | [ADR-hybrid-pilot-release-cut.md](../adr/ADR-hybrid-pilot-release-cut.md) |
| R-07 | Single-host capacity exceeded without multi-host review | engineering-lead | Medium | High | Exact trigger document with 10-business-day ADR SLA | Any availability trigger | Continuous | [AVAILABILITY_AND_ISOLATION_TRIGGERS.md](../architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md) |
| R-08 | Compressed calendar (Phases 1–5 landed in days vs plan 13–19 engineer-weeks) left types/ledger leftovers; pressure to skip Phase 6 gates | engineering-lead | High | High | One-packet-per-run; restore Phase 1 types bar on touched trees; do not skip Combined/holdout/citation gates. Continue-to-v1 is not an escape hatch | Phase 6 packet claims without evidence, or types tier left red | 2026-08-16 | [ADR-hybrid-pilot-release-cut.md](../adr/ADR-hybrid-pilot-release-cut.md); [2026-08-16 review](../reviews/2026-08-16-phases-01-05-implementation-review.md); [close-out](../reviews/2026-08-16-phases-01-05-closeout.md) |
| R-09 | Same-host ParadeDB/Valkey TLS omission accepted without ADR | engineering-lead | Low (closed for Packet 3) | Medium | Packet 3 ADRs accepted before local TLS omission; staging/production revisit remains | Closed locally; reopen if Compose ships without the accepted TLS ADR | 2026-08-16 | [ADR-private-service-tls.md](../adr/ADR-private-service-tls.md) |
| R-10 | Figures/charts-only answers invent visual content | engineering-lead | Medium | High | Signed media limitation + UI notice; vision ADR trigger only if funded | Eval finds invented figure claims | Phase 6/8/9 | QT-MEDIA-*; [ADR-vision-captioning.md](../adr/ADR-vision-captioning.md) (proposed) |

## Assumption log (not yet measured or approved)

| Assumption | Status | Becomes evidence when |
| --- | --- | --- |
| Provisional numeric targets match client needs | Accepted 2026-08-12 (`approved`) | User signed QUALITY_TARGETS |
| BM25 envelope resource/rebuild numbers | **Unmeasured** (Packet 9 live retrieve is not envelope qualification) | Phase 9 BM25 envelope suite (QT-BM25-*) |
| Graph full-rebuild cost and monthly reserve dollar amount | Envelope reduced to 15 docs on 2026-08-16; cost still **unmeasured**; reserve USD 800 floor | First measured clean-workspace rebuild |
| Developer workstation meets documented minimums | This host ran Phases 1–5; envelope RAM still unverified | Envelope RAM/rebuild measurement |
| Provider DPA/retention/governance acceptable | Unsigned; real company content **prohibited** | Provider matrix rows `verified` |
| Continue-versus-pilot | Recorded 2026-08-16: continue toward production v1 with reduced GraphRAG | Production v1 still requires remaining phase gates; Hybrid Pilot was not chosen |

## Links

- [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- [ADR-hybrid-pilot-release-cut.md](../adr/ADR-hybrid-pilot-release-cut.md)
- [AVAILABILITY_AND_ISOLATION_TRIGGERS.md](../architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md)
- [PHASE4_RANKED_IDS.md](../evaluation/PHASE4_RANKED_IDS.md)
- [PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md)
- [PHASE6_HANDOFF.md](../graph/PHASE6_HANDOFF.md)
- [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md)
- [phase-04-hybrid-rag-evidence.md](./phase-04-hybrid-rag-evidence.md)
- [phase-05-graphrag-evidence.md](./phase-05-graphrag-evidence.md)
