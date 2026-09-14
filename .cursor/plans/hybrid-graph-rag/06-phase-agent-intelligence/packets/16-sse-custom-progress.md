---
phase: 6
packet: 16
status: complete
title: "Add LangGraph custom SSE progress and paced verified-answer presentation contract."
requirement_ids: [P06-16]
---

# Packet 16 — Add LangGraph custom SSE progress and paced verified-answer presentation contract.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This is a Phase 6/Phase 8 co-owned additive streaming amendment. Also read:

- [`../../08-phase-frontend-integration/00-shared-contracts.md`](../../08-phase-frontend-integration/00-shared-contracts.md)
- [`../../08-phase-frontend-integration/00-visual-contract.md`](../../08-phase-frontend-integration/00-visual-contract.md)
- [`docs/adr/ADR-verified-answer-paced-reveal.md`](../../../../../docs/adr/ADR-verified-answer-paced-reveal.md)

Named skills: [`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md)
and [`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

Do not uncheck historical completed Phase 6 or Phase 8 packets. Do not renumber
P08-22 or P08-23.

## Preconditions

- P08-09 verified-final hold and one-terminal settlement remain in force.
- Pinned agents LangGraph is 1.2.11.
- P08-24 has recorded the ADR and integrity amendment. Coding packets BEP-01
  through BEP-07 and FEP-01 through FEP-05 implement this contract; this packet
  authorizes the co-owned stream/presentation rules.

## Allowed outputs

- Additive shared-contract wording for `updates` plus `custom` v2 streaming.
- A pinned LangGraph 1.2.11 contract test requirement (implemented in BEP-02).
- Additive public SSE fields `status.phase` and event `tool_progress`.
- Phase 6 plus Phase 8 evidence notes linking the ADR.

## Forbidden outputs

- Pre-verification draft `token_delta` or `stream_mode="messages"`.
- Custom payloads containing prompts, queries, arguments, results, passages,
  snippets, source text, exceptions, traces, or secrets.
- Client-invented node/tool/timer progress.
- Renumbering P08-22/P08-23 or unchecking completed packets.
- Application producers in this documentation packet.

## Ordered actions

1. Record that production `compiled.astream` may use
   `stream_mode=["updates", "custom"]`, `version="v2"`, after a real compiled
   contract test observes the installed 1.2.11 v2 `StreamPart` shape.
2. Restrict custom writer payloads to
   `{kind: "node_start", stage}` and
   `{kind: "tool_progress", tool_key, phase}`.
3. Keep `updates` as completion proof. Hold draft answer text until
   `verify_answer` completes, then emit catalog-valid `token_delta` chunks at
   the existing 4096-character bound.
4. Require persisted sequenced events so reconnect/replay reconstructs the
   same timeline. `status.phase` is optional for legacy rows.
5. State that presentation pacing is frontend-only and must not delay
   terminal, settlement, citations, or the resume cursor.
6. Link Phase 8 packets P08-48 through P08-59 (BEP/FEP) as the implementation
   owners. BEP-01+ stay blocked until P08-24 integrity passes.

## Acceptance checks

- Shared contracts and this packet explicitly supersede “updates-only” and
  “no artificial delay” presentation wording.
- Custom progress is limited to safe keys.
- Verified-final hold, first terminal, and reservation settlement remain
  mandatory.
- No sibling Phase 6 coding packet is activated by this file alone.

## Negative tests

- A custom payload with `query`, `result`, `error`, or source text must be
  dropped by the mapper (proven in BEP-05).
- Early `token_delta` before `verify_answer` completion fails closed (BEP-07 /
  FEP-01).

## Stop routes

- Stop if the pinned LangGraph version is not 1.2.11 or the observed v2 shape
  differs from the documented adapter. Update the contract from observed data
  before producers change.
- Stop if a change would emit draft prose or weaken authorization/RLS.

## Required evidence

Append `P06-16` proof to
[`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
and
[`phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
contract links, ADR path, integrity command results, and the BEP-02 contract
test handoff. This packet may close as documentation once P08-24 integrity
passes; producer proof remains on BEP-02/BEP-06.
