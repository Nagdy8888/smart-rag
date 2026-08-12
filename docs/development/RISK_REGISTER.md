---
title: Phase 1 risk register
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering, client-approver
---

# Risk register (Phase 1 foundation)

Living register for launch-blocking and delivery risks visible at Phase 1. BM25 full-envelope resource/rebuild values, graph rebuild cost, local hardware sufficiency, provider governance, and user sign-off remain **assumptions** until measured or approved.

| ID | Risk | Owner | Probability | Impact | Mitigation | Trigger | Review date | Evidence link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Client does not sign provisional quality/cost/capacity targets; Phase 1 blocked | product-owner | Low (mitigated) | High | Signed 2026-08-12 via `approved` | Closed for Packet 1 | 2026-08-12 | [QUALITY_TARGETS.md](../QUALITY_TARGETS.md); [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md) |
| R-02 | BM25 full-envelope index size/RAM/rebuild duration unknown; Hybrid Ready assumptions wrong | engineering-lead | High | High | Qualify pinned ParadeDB digest; measure at envelope in Phase 4/9; keep Supabase recheck authoritative | BM25 qualification fails QT-BM25-* | 2026-11-07 | [QUALITY_TARGETS.md](../QUALITY_TARGETS.md) QT-BM25-*; BM25 contract (Phase 1 packet 5) |
| R-03 | Graph full-rebuild cost unknown; reserve formula unevaluable; envelope too large for 7-day rebuild | engineering-lead | High | High | Measure rebuild before bulk onboarding; reserve ≥ max(800, 4× cost); reduce envelope or quarantine | QT-GR-002/005/006 miss | After first measured rebuild | [QUALITY_TARGETS.md](../QUALITY_TARGETS.md) QT-GR-*; QT-COST-003 |
| R-04 | Local Windows/Docker Desktop resources below 16 GB / 4 cores / 40 GB free; foundation startup fails | engineering-lead | Medium | Medium | Document minimums; prefer WSL2 ext4; stop with exact prerequisite rather than fake services | Packet 3/6 startup failure | 2026-08-22 | Phase 1 packet 3/6 evidence |
| R-05 | OpenAI/subprocessor governance unsigned; real corpus processing blocked | product-owner | Medium | High | Draft governance packets in Packet 5; require signature before live data | Attempt to process real corpus without signed packet | Before Phase 3 real corpus | OPENAI/SUBPROCESSOR governance (Packet 5) |
| R-06 | Hybrid Pilot silently treated as production v1 | product-owner | Medium | High | Dated ADR with production-label prohibition and Phase 4 re-decision | End Phase 4 without recorded decision | 2026-11-07 | [ADR-hybrid-pilot-release-cut.md](../adr/ADR-hybrid-pilot-release-cut.md) |
| R-07 | Single-host capacity exceeded without multi-host review | engineering-lead | Medium | High | Exact trigger document with 10-business-day ADR SLA | Any availability trigger | Continuous | [AVAILABILITY_AND_ISOLATION_TRIGGERS.md](../architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md) |
| R-08 | Schedule (23–35 weeks) slips; pressure to skip gates | engineering-lead | High | High | One-packet-per-run discipline; Hybrid Pilot cut is only approved escape with honest label | Checkpoint criteria miss | 2026-08-22 and 2026-11-07 | ADR-hybrid-pilot; plan effort section |
| R-09 | Same-host ParadeDB/Valkey TLS omission accepted without ADR | engineering-lead | Medium | Medium | Packet 3 ADRs before omission; staging revisit trigger | Compose without accepted TLS ADR | Packet 3 | ADR-private-service-tls (Packet 3) |
| R-10 | Figures/charts-only answers invent visual content | engineering-lead | Medium | High | Signed media limitation + UI notice; vision ADR trigger only if funded | Eval finds invented figure claims | Phase 6/8/9 | QT-MEDIA-*; ADR-vision-captioning (planned) |

## Assumption log (not yet measured or approved)

| Assumption | Status | Becomes evidence when |
| --- | --- | --- |
| Provisional numeric targets match client needs | Accepted 2026-08-12 (`approved`) | User signed QUALITY_TARGETS |
| BM25 envelope resource/rebuild numbers | Unmeasured | Phase 4/9 qualification suite |
| Graph full-rebuild cost and monthly reserve dollar amount | Unmeasured (formula only) | First measured clean-workspace rebuild |
| Developer workstation meets documented minimums | Unverified | Packet 3/6 startup proof |
| Provider DPA/retention/governance acceptable | Unsigned | Signed governance packets |

## Links

- [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- [ADR-hybrid-pilot-release-cut.md](../adr/ADR-hybrid-pilot-release-cut.md)
- [AVAILABILITY_AND_ISOLATION_TRIGGERS.md](../architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md)
- [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md)
