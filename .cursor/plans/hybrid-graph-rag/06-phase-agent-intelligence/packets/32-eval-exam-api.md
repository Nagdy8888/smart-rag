---
phase: 6
packet: 32
status: complete
title: "Expose exam start, poll, cancel, latest report, and missed-case APIs."
requirement_ids: [P06-32]
---

# Packet 32 — Expose exam start, poll, cancel, latest report, and missed-case APIs.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not build UI in this packet.

## Preconditions

- P06-30 RPCs and P06-31 runner exist. Inspect pdf-eval router, rate-limit
  kinds, readiness, and error mapping.

## Allowed outputs

- Exam/report Pydantic schemas (`extra="forbid"`).
- `POST /admin/pdf-eval/exams`, `GET /exams/{id}`,
  `POST /exams/{id}/cancel`, `GET /reports/latest`,
  `GET /reports/{id}/cases`.
- Rate-limit/readiness/error mapping, OpenAPI, contract tests/docs.

## Forbidden outputs

- Running all cases inside the HTTP request.
- Frontend scoreboard.
- Private field names or canary values in JSON.
- Holdout in body enums without SQL defense as well.

## Ordered actions

1. Implement the exam/report paths and responses from the hosted-evaluation
   HTTP contract.
2. Owner/admin on every route. Members 403. Inaccessible IDs 404.
3. `COST_MUTATION` on start/cancel; existing safe read limiting on polls.
4. Derive caller and candidate identity server-side.
5. Return 202 immediately. Poll/status survives frontend refresh and API
   process restart.
6. Partial exams never replace the latest complete report.
7. Recursively exclude private field names from every JSON response.

## Acceptance checks

- 202 start, idempotent reconnect, collision, one-active 409.
- Poll states queued/running/terminal. Cancel is idempotent.
- Latest report is split-isolated.
- Staging/production/disabled path remains 404.

## Negative tests

- Member/viewer 403.
- Holdout rejected by body enum and SQL defense.
- No eligible cases is 422 with counts only.
- Qualification already consumed is 409.
- Budget/rate/readiness reuse existing 402/429/503 classes.

## Stop routes

- Stop rather than execute the exam inline to avoid 202.
- Do not log questions or answers on error paths.

## Required evidence

- Append `tests/contract/test_pdf_eval_exam_api.py` results, OpenAPI, and
  P06-33 handoff.
