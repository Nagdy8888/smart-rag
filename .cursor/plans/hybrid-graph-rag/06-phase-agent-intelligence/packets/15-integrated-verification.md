---
phase: 6
packet: 15
status: complete
title: "Run all deterministic and live gates, inspect LangSmith traces, and update evidence and runbooks."
requirement_ids: [P06-15]
---

# Packet 15 — Run all deterministic and live gates, inspect LangSmith traces, and update evidence and runbooks.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md),
and
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- Packets 10–14 implementation and packet-local tests exist.
- Live credentials/services are used only when present. Unavailable live
  gates are marked blocked; they are never replaced with mocked
  cloud-success claims.

## Allowed outputs

- Deterministic gate command output, scenario-matrix evidence, LangSmith
  trace proof or an explicit blocked marker, live Studio proof or an
  explicit blocked marker, and documentation updates listed in Ordered
  actions.
- Phase 6 and Phase 8 evidence appendices.

## Forbidden outputs

- New product behavior beyond documentation and evidence.
- Fake live success, skipped integration marked as passed, or hiding a
  remaining `GeneratorExit` on a successful completed run.
- Marking the feature complete before the user accepts this packet's
  evidence.

## Ordered actions

1. Run deterministic gates using repository-defined commands:

   ```powershell
   uv run python scripts/check.py --tier unit
   uv run python scripts/check.py --tier contract
   uv run python scripts/check.py --tier types
   uv run ruff check .
   uv run pyright
   pnpm --filter smart-rag-frontend test
   pnpm --filter smart-rag-frontend lint
   pnpm --filter smart-rag-frontend typecheck
   pnpm --filter smart-rag-frontend build
   ```

   Use repository-defined frontend/Playwright commands rather than inventing
   a new runner.
2. Prove the required scenario matrix:
   1. “Hi” → short assistant reply, deterministic origin, zero
      model/retrieval.
   2. “How can you help me?” → general response describing both
      capabilities, one counted answer call, no citations.
   3. “What is the capital of France?” → general origin, one call, no
      retrieval.
   4. “Rewrite this paragraph: …” → user-text origin, one call.
   5. “What is our refund period?” → company route; cited evidence or
      explicit insufficient-evidence refusal, never general fallback.
   6. Current relationship → Combined rules unchanged.
   7. Table request → StructuredTable rules unchanged.
   8. Mixed general+company prompt → clarification, zero retrieval/model.
   9. Follow-up after a cited company answer remains company scope unless
      the user clearly switches.
   10. Prompt injection cannot force company/document claims on the general
       path or force world-knowledge fallback on the company path.
   11. Duplicate submission/reconnect produces one paid run.
   12. General call consumes one durable reservation and immutable usage
       row.
   13. ACL downgrade/deletion prevents document evidence immediately.
   14. Expired/revoked Studio JWT rejects before model/retrieval.
3. With tracing governance enabled and redaction verified, run at least
   three successful chats, one explicit cancellation, and one genuine
   controlled gateway failure. Inspect traces and correlate with persisted
   SSE terminals. If LangSmith access/credentials are unavailable, mark this
   gate blocked.
4. With a real developer JWT and services: keep `query_studio` selected
   first and prove deterministic greeting/topology without network; then
   prove `query_studio_live` general, authorized-document, unauthorized-
   absent, new-turn, retry-idempotent, and expired-token cases. If
   credentials/services are unavailable, mark live Studio blocked.
5. Update `QUERY_ROUTING.md`, `QUERY_BUDGETS.md`, `SSE.md`,
   `LANGSMITH_TRACING.md`, `LANGGRAPH_STUDIO.md`, `CONFIGURATION.md`,
   `.env.example`, and Phase 6/Phase 8 evidence. Docs must explain the
   strict split, `answer_origin`, no general fallback, Studio live token
   setup/rotation/removal without printing it, `query_studio` versus
   `query_studio_live`, `GeneratorExit` interpretation, rollback, and
   troubleshooting.

## Acceptance checks

- All deterministic gates pass.
- Successful traces no longer show `GeneratorExit`, or the LangSmith
  inspection gate is explicitly blocked by unavailable credentials.
- Live app and live Studio checks pass or are explicitly blocked by
  unavailable credentials/services.
- No plan/security/cost deviation remains undocumented.
- The user accepts P06-15 evidence.

## Negative tests

- A mocked LangSmith success, a company no-evidence general fallback, a
  remaining successful-run `GeneratorExit` presented as harmless without
  the P06-11 lifecycle proof, or a live JWT printed in evidence fails the
  packet.

## Stop routes

- Stop if a deterministic gate fails after bounded repair.
- Stop if live credentials/services are unavailable and only fake success
  could pass; record the blocker instead.

## Required evidence

- Append the complete command table, scenario matrix, trace/live proof or
  blockers, documentation diffs, rollback, and user-acceptance request to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and the relevant Phase 8 evidence section.
