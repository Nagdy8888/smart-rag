---
phase: 6
packet: 33
status: complete
title: "Add owner/admin Save to quiz beside existing thumbs feedback."
requirement_ids: [P06-33]
---

# Packet 33 — Add owner/admin Save to quiz beside existing thumbs feedback.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md).

Do not modify Admin Evaluation in this packet.

## Preconditions

- P06-29 create/list/detail/compare APIs exist.
- Inspect `FeedbackPopover`, `chat-stage.tsx`, `chat-app.tsx`, feedback
  tests, and `/api/meta.pdf_eval_workspace`.

## Allowed outputs

- New owner/admin quiz popover/component and hooks beside existing feedback.
- Create/list/detail/compare API clients and types.
- Role/capability gating.
- Preserved feedback tests plus quiz tests/docs/action inventory.

## Forbidden outputs

- Replacing or removing thumbs/tag/comment for eligible users.
- Sending expected-answer text to Ask or to a model.
- Scoring a newly saved draft against the run that created it as a quality
  score.
- Calling citation overlap Recall@10.
- Admin Evaluation scoreboard work.

## Ordered actions

1. Keep `FeedbackPopover` and `submitFeedback` for all currently eligible
   users.
2. Add a separate **Save to quiz** control for owner/admin when
   `/api/meta.pdf_eval_workspace` is true.
3. Pass the current completed run ID, question, and ACL-rechecked citations
   from `ChatApp`/`ChatStage`. Create sends the run ID; the server loads the
   question.
4. Permit zero to three citation suggestions. Block a fourth accessibly.
5. Display the curated-record retention disclosure (chat deletion does not
   delete the saved case).
6. Submit an idempotent development draft. Never approve.
7. Add a paginated saved-case selector that fetches detail only after
   selection. **Ask this question** fills only the question.
8. Enable **Score this answer** only for a pre-existing approved case whose
   normalized question matches. Label it **not Recall@10**.
9. Invalidate session-scoped query keys after save. Render server/model
   text with existing safe text components.

## Acceptance checks

- Member/viewer: Give feedback present, Save to quiz absent.
- Owner/admin capability on: both controls present.
- Capability off: ordinary feedback only.
- Zero-gold draft save works.
- XSS strings remain text. Keyboard, focus return, labels, pending,
  success, retry, and error states exist.

## Negative tests

- Newly saved draft cannot score its creating run as quality.
- Expected answer is not sent to Ask or compare.
- Forged member POST still 403s.

## Stop routes

- Stop rather than rewrite Give feedback into the quiz form.
- Do not start Admin Evaluation work here.

## Required evidence

- Append frontend test/type/lint/build commands, action-inventory updates,
  and P06-34 handoff.
