---
title: Query budget engineering defaults
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering
phase_packet: Phase 6 Packet 1
---

# Query budget engineering defaults

There is no signed per-call USD table. Values below are Phase 6 engineering
defaults derived from `QT-COST-001` (USD 200/month) and the signed call
ceilings in [QUALITY_TARGETS.md](../QUALITY_TARGETS.md). They do not replace
those signed rows. SQL `app.query_route_envelope` must match
`smart_rag_core.query_admission.ceilings`.

`no_retrieval` and `scoped_refusal` have no sixth signed deadline. Packet 1
uses the Hybrid 25-second envelope for both.

## Per-call caps by usage kind

| Kind | USD cap | Max prompt tokens | Max completion tokens |
| --- | --- | --- | --- |
| profile | 0.08 | 4000 | 1500 |
| rewrite | 0.08 | 4000 | 1500 |
| embedding | 0.02 | 8000 | 0 |
| lightrag | 0.25 | 8000 | 2000 |
| rerank | 0.20 | 12000 | 2000 |
| answer | 0.40 | 8000 | 2000 |
| summary | 0.25 | 6000 | 1500 |
| verifier | 0.20 | 4000 | 1000 |

Timeout-after-send records the kind cap. The attempt is never under-counted.

## Route envelopes

Envelope USD = `model_call_ceiling × family per-call USD cap`. The family
per-call cap is the conservative maximum kind used on that route (answer
0.40 except inspection 0.25).

| Family | Deadline s | Model calls | Tools | Envelope USD | Prompt tokens | Completion tokens |
| --- | --- | --- | --- | --- | --- | --- |
| hybrid | 25 | 7 | 4 | 2.80 | 56000 | 14000 |
| combined | 45 | 8 | 4 | 3.20 | 64000 | 16000 |
| structured_table | 30 | 6 | 4 | 2.40 | 48000 | 12000 |
| composite | 50 | 9 | 5 | 3.60 | 72000 | 18000 |
| graph_inspection | 10 | 3 | 4 | 0.75 | 12000 | 4500 |
| no_retrieval | 25 | 7 | 4 | 2.80 | 56000 | 14000 |
| scoped_refusal | 25 | 7 | 4 | 2.80 | 56000 | 14000 |

Shared ceilings: `recursion_limit=24`, 1 correction, 3 subquestions, 1
discovery round, 3 optional manifests, 1 side-effecting tool. Hybrid call 7
is only for a correction rerank or a non-deferrable summary (later packets
enforce that policy; this packet stores the numeric ceiling).

Monthly query spend uses
`COALESCE(profile.monthly_llm_budget_usd, company.monthly_llm_budget_usd, 200)`.
`graph_maintenance` (QT-COST-003) is not consumable by query.

## Related

- [QUERY_ADMISSION.md](./QUERY_ADMISSION.md)
- [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- [ADMINISTRATION.md](../frontend/ADMINISTRATION.md)
