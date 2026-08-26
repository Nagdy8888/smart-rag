---
title: ADR — Verified-answer paced reveal and custom node/tool progress
adr_id: ADR-verified-answer-paced-reveal
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-26
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-26"
audience: frontend, backend, security, reviewers
---

# ADR: Verified-answer paced reveal and custom node/tool progress

## Status

`accepted` — 2026-08-26. The user first selected **progress-only before
verification**, then approved a **paced verified-answer reveal after
verification** so verified text does not appear as one bulk block. This ADR
supersedes the P08-09 / P08-15 / Phase 8 shared-contract presentation rule that
required inserting verified final text **without artificial delay**. It does
not authorize pre-verification draft prose.

## Context

P08-09 repaired the production executor so draft `answer_text` stays private
until deterministic verification, then emits persisted `token_delta`
compatibility events. P08-15 inserted those verified chunks immediately and
forbade typewriter animation. Live P08-22 evidence still lacked truthful
`Verifying` progress, and users waited without a route-aware timeline.

The prior “no artificial delay” rule mixed two concerns:

1. **Authoritative ingestion** of verified text into reducer, persistence,
   settlement, citations, and the resume cursor.
2. **Visual presentation** of that already-verified text.

Delaying (1) would change durability, cost, and reconnect semantics. Delaying
only (2) is a presentation policy.

LangGraph 1.2.11 supports `stream_mode=["updates", "custom"]` with `version="v2"`.
Custom writer payloads can carry safe node/tool start signals without exposing
drafts. This is a Phase 6/Phase 8 co-owned streaming amendment. Implementation
is additive packets `P06-16` and `P08-24` through `P08-87`. Do not uncheck
historical packets or renumber `P08-22` / `P08-23`.

## Decision (accepted)

1. **No pre-verification prose.** `generate_answer`, `general_scope`, and
   `mixed_scope` drafts stay private. Persisted `token_delta` events carry only
   verified, refused, or partial prose. The frontend reducer rejects earlier
   tokens.
2. **Immediate authoritative ingestion.** Every accepted verified chunk appends
   to in-memory `answerText` and durable event order immediately. Protocol
   terminal, persistence, usage settlement, resume cursor, citation
   availability, cancel, and a new send do not wait for presentation.
3. **Bounded presentation reveal.** For a run created in the current mounted
   session, a client presentation buffer reveals already-verified text over
   animation frames. Hard ceiling is 2.5 seconds from first non-empty verified
   availability. Reveal-owned React publications are at most 90 per answer.
   Answers longer than 80 grapheme clusters must paint a strict intermediate
   prefix, then complete. Segmentation uses `Intl.Segmenter` graphemes; if
   unavailable, show the full string. No UTF-16 home-grown slicer.
4. **Skip and reduced motion.** `Show full answer` completes immediately.
   `prefers-reduced-motion: reduce`, historical/reloaded messages, conversation
   switch, a new send, copy/selection intent, and unmount bypass remaining
   pacing. No presentation offset is persisted or included in the SSE cursor.
5. **Truthful progress, not timers.** The UI shows only server-originated node
   and authorized tool start/completion/failure. Skipped topology nodes emit
   nothing and must not appear. No client-invented elapsed time, percentage,
   or predicted next node. `Verifying` comes from the real `verify_answer`
   node. Custom payloads contain only safe keys (`kind`, `stage`, `tool_key`,
   `phase`) — never prompts, queries, arguments, results, passages, snippets,
   source text, exceptions, traces, or secrets.
6. **Production stream modes.** After the pinned 1.2.11 v2 contract test and
   mapper work, the production executor may use
   `stream_mode=["updates", "custom"]` and `version="v2"`. `updates` remains
   completion proof. This supersedes the P08-09 “keep `stream_mode="updates"`
   only” executor wording without weakening verified-final hold.
7. **God-file rule.** Progress and reveal behavior land in extracted owners.
   `chat-app.tsx`, `api.ts`, `types.ts`, `graph.py`, `executors.py`,
   `query_sse_mapping.py`, and the other named stream-path files must meet the
   physical-line budgets in the P08-24 suite.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Pre-verification typewriter of draft tokens | User rejected; exposes unverified prose and reopens P08-09 |
| Keep bulk insert of verified text | User asked for a paced reveal so answers do not appear as one block |
| Fake `Verifying` with a client timer | Lies about work; P08-22 must prove the real node |
| Shrink backend `token_delta` chunks to fake animation | Multiplies durable writes and replay cost without changing wait latency |
| Persist a presentation cursor | Would stall resume/settlement and duplicate protocol state |
| `stream_mode="messages"` for live tokens | Exposes drafts and redesigns the verifier gateway |

## Consequences

- Chat UX still measures **verified answer availability**, not provider
  time-to-first-token.
- Screen readers get one polite “Verified answer ready” announcement, not
  per-slice chatter.
- The UI label during reveal is `Verified — displaying answer`, never
  “still generating.”
- A future pre-verification reversal requires a new ADR and user approval.
- Rollback is `git revert` of the additive packet commits. Historical
  `status` rows without `phase` remain valid.

## Rollback

Do not force-push `main`. Revert the feature-branch commits that implement
custom progress and the reveal hook. Leave persisted `phase` optional so old
rows replay. Do not edit applied migrations to remove additive SSE fields;
use expand/contract if a field must later be retired.
