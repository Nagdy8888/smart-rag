---
phase: 6
packet: 20
status: complete
title: "Implement the local private-file evaluation store and source-bound draft generation."
requirement_ids: [P06-20]
---

# Packet 20 — Implement the local private-file evaluation store and source-bound draft generation.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).
Do not load frontend or FastAPI router skills.

## Preconditions

- Packet 19 is recorded. Packet 9 is accepted.
- Existing `packages/core/src/smart_rag_core/evaluation/private_pdf/` schemas,
  loaders, seal, and `build_draft_rows` are inspectable.

## Allowed outputs

- `packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_store.py`
- `packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_models.py`
- Additive edits to `draft.py`, `loader.py`, `schema.py`, and `__init__.py`
- `tests/unit/test_pdf_eval_workspace_store.py` and additive
  `tests/unit/test_private_pdf_eval.py` cases
- Docs for store bounds in `docs/evaluation/PDF_EVAL_WORKSPACE.md` if the
  file is created here; otherwise Packet 21 owns the HTTP doc.

## Forbidden outputs

- FastAPI routers, frontend files, migrations, Compose mounts, or OpenAI
  draft-generation calls.
- Operator/service-role DSN usage.
- Self-approving generated rows.
- Holdout path reads.
- Changing frozen Hybrid profile bytes.

## Ordered actions

1. Add a workspace store rooted at a server-owned path. HTTP callers never
   supply a filesystem path.
2. Reject traversal, symlinks that escape the root, and any path containing
   `holdout` case-insensitively.
3. Bound datasets to 60 cases, questions to 2,000 characters, answers to
   8,000, at most 16 facts of 1,000 characters, and at most 3 gold chunks.
4. Return SHA-256 revisions. Mutations require the expected revision and use
   compare-and-swap plus atomic replace under a process lock.
5. Invalidate `human_approved` and reviewer when question, answer, facts, or
   locators change.
6. Improve `build_draft_rows` so required terms appear in the gold locator,
   answers are extractive, duplicates are rejected, and generated rows stay
   `generated_only=true`.
7. Never log questions, answers, facts, excerpts, JWTs, or absolute roots.

## Acceptance checks

- Unit tests prove traversal/holdout rejection, stale revision conflict,
  failed-write durability, approval reset on edit, no self-approve, v1 draft
  load, and log redaction.
- Existing seal/load invariants still pass.

## Negative tests

- `../` and holdout components fail closed.
- Stale revision does not overwrite.
- Unsupported glossary aliases are not cycled onto unrelated passages.

## Stop routes

- Stop if current draft JSON cannot load without a breaking schema change.
- Do not invent a database label store.

## Required evidence

- Append unit command/exit, files changed, and Packet 21 handoff.
