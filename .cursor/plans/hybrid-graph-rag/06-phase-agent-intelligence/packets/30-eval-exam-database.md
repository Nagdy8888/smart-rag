---
phase: 6
packet: 30
status: complete
title: "Add durable exam-run, result, report, and hidden-conversation database contracts."
requirement_ids: [P06-30]
---

# Packet 30 — Add durable exam-run, result, report, and hidden-conversation database contracts.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not implement the Python exam runner or HTTP start/poll routes here.

## Preconditions

- P06-28/P06-29 case tables exist. Inspect conversation functions, query
  admission, run lifecycle, job lease patterns, report immutability triggers,
  and worker grants. P06-10 must be accepted before P06-31; this packet may
  land schema after P06-29.

## Allowed outputs

- One forward migration for `app.eval_exam_runs`,
  `app.eval_exam_case_results`, `app.eval_exam_reports`, and an additive
  conversation purpose discriminator.
- Additive replacements of conversation list/get/messages/title SQL so
  `evaluation` conversations are never returned to browser clients.
- Enqueue/claim/heartbeat/result/finalize/cancel/reclaim/report/retention
  RPCs.
- Database lifecycle tests and migration artifacts.

## Forbidden outputs

- FastAPI exam routes, frontend, or a second spend protocol.
- Valkey or process-memory locks as exam authority.
- Holdout split. `holdout_opened` must CHECK false on reports.
- Questions, answers, excerpts, ranked IDs, or gold UUID lists in result or
  report tables.
- UPDATE/DELETE of successful reports by runtime roles.

## Ordered actions

1. Add exam/result/report tables with 365-day expiry, idempotency,
   dataset_hash, candidate_fingerprint, metric version
   `production_corpus_all_required_gold_at_10_v1`, and
   `cache_mode=cold_bypass`.
2. Partial unique index: one queued/running exam in the singleton workspace.
3. Unique qualification attempt key over dataset/candidate fingerprint.
4. Add server-owned conversation purpose; existing rows default to `chat`.
   Browser create always creates `chat`. Exam RPC may create `evaluation`.
5. Replace conversation list/get/messages/title functions additively so
   evaluation conversations are hidden.
6. Atomic enqueue: approved-case snapshot, dataset hash, one-active,
   qualification-once, hidden conversation, audit.
7. Claim/heartbeat/reclaim with `FOR UPDATE SKIP LOCKED` and bounded leases.
8. Idempotent case-result persistence and progress counters.
9. Immutable successful report insert. Latest-report lookup ignores
   partial/failed/cancelled runs.
10. Bounded retention purge. Refresh hashes and apply/verify hosted.

## Acceptance checks

- Two simultaneous starts create only one active exam.
- Same key/payload reconnects; changed payload rejects.
- Qualification key cannot be consumed twice after any persisted result or
  provider call.
- Terminal report cannot update. Partial exams never become latest official.
- Ordinary conversation list/get regression still hides nothing that was
  previously visible and never returns evaluation conversations.

## Negative tests

- Holdout and unknown split rejected.
- Stale dataset hash, stale gold, unapproved or zero-gold case rejected at
  enqueue.
- Expired lease is reclaimable; live lease is not.
- Duplicate case result cannot double-increment progress.
- Browser conversation RPCs never return purpose=`evaluation`.

## Stop routes

- Stop if conversation hide requires changing browser request schemas.
- Do not grant `app_worker` SELECT on chat conversations to “fix” exams.

## Required evidence

- Append migration, conversation-regression tests, hosted verify without
  secrets, and P06-31 handoff.
