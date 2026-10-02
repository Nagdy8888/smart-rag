---
title: App review 2026-10-02 — index and verdict
owner: engineering-lead
status: draft
last-reviewed: 2026-10-02
audience: eng, reviewers, client-approver
---

# App review 2026-10-02

Full-product review of security, system design, the agent "brain" (query
reasoning), smartness improvements, and the frontend. Every finding was verified
against current code (paths + line references in each document). Nothing in
this folder was implemented during the review — these are findings and
recommendations only.

## Documents

| # | Document | Question it answers |
| --- | --- | --- |
| 01 | [Security review](./01-security-review.md) | Is the app safe to run with real company data? |
| 02 | [System design review](./02-system-design-review.md) | Is the architecture sound, durable, and scalable? |
| 03 | [Agent brain review](./03-agent-brain-review.md) | How does the query agent actually think, and where is it brittle? |
| 04 | [Smarter-agent roadmap](./04-smarter-agent-roadmap.md) | What should we change to make the app measurably smarter? |
| 05 | [Frontend review](./05-frontend-review.md) | Is the console UX solid, fast, accessible, and safe? |

## Executive verdict

| Area | Grade | One-line verdict |
| --- | --- | --- |
| Security | **A−** | Fail-closed, server-authoritative, RLS-disciplined; no Critical/High findings. Residuals: MFA policy decision, mandatory rate-limit backend, minor hardening. |
| System design | **A−** | Canonical-vs-derived separation is exemplary; durable queues and frozen profiles everywhere. Fix the `run_events` CHECK drift and plan multi-API execution before scaling. |
| Agent brain | **B** | Excellent safety spine (typed refusals, bounded budgets, layered verification). Intelligence is constrained by eval-set scaffolding and regex-first intent detection. |
| Smartness roadmap | — | Ten prioritized changes; S1 (general extractive answering), S2 (bounded multi-hop), S3 (trust the model profile) are the highest leverage. |
| Frontend | **B+** | Best-in-class SSE client and XSS discipline. Missing route boundaries and chat re-render hygiene hold it back. |

## Top findings across all reviews

**Must fix (High):**

1. **`run_events` CHECK constraint drift** — Python SSE catalog allows
   `tool_progress`/`answer_origin`; the Postgres CHECK does not. Any append of
   those types fails at the DB layer. [SYS-1, 02]
2. **Live query runs are process-local** — the in-memory `QueryRunRegistry`
   blocks horizontal API scaling without sticky sessions or a lease pattern.
   [SYS-2, 02]

**High-value improvements:**

3. **Replace eval-set scaffolding with a general extractive-answer mode** —
   question-specific salvages/promotions/prompt rules exist in four layers;
   they inflate the benchmark and do not generalize. [W1, 03; S1, 04]
4. **Wire optional tools into the answer** — tools execute but their results
   never reach `generate_answer`. [W4b, 03]
5. **Collapse the duplicate chat data hook and isolate the streaming subtree** —
   the Ask page polls duplicate queries and re-renders the full stage per token
   batch. [FE-3/4, 05]
6. **Add App Router `error`/`loading`/`not-found` boundaries** — none exist.
   [FE-1, 05]

**Decisions needed:**

7. **MFA/AAL policy** — assurance level is captured but not enforced. [SEC-1, 01]
8. **Multi-API execution pattern** — sticky sessions vs lease-based claim.
   [SYS-2, 02]

## Method

Four parallel deep-dive explorations (security, system design, agent brain,
frontend) plus direct verification reads of the routing, verification,
correction, memory, answer, and SSE-CORS code paths. Findings were
cross-checked by a second read before being written down; unverified claims were
discarded. Severity vocabulary: Critical / High / Medium / Low per document.

## What this review did not cover

- Live hosted-environment behavior (EC2 staging, real Supabase load, Valkey
  failover drills) — code and compose/infra definitions only.
- The `prev_review/` weakness reports and plan-packet acceptance status — out of
  scope for this code-level review.
- Performance numbers (latency/cost baselines) — these need the online eval loop
  proposed in S9 of the roadmap.