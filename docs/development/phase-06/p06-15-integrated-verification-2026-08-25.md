# P06-15 — Integrated verification (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: run the repository deterministic gates, prove the
strict-split scenario matrix from existing tests, inspect LangSmith or
mark it blocked, prove live Studio or mark it blocked, and update the
named runbooks. Do not claim live success from mocks.

Process overrides used for Python quality commands (local `.env` enables
live-model and tracing flags that break mock-default constructors):
`APP_ENV=local`, `MOCK_MODEL_MODE=true`, `ALLOW_TEST_IDENTITY=false`,
`LANGSMITH_TRACING=false`. Values from `.env` were not printed.

## Deterministic gates

| Command | Exit | Notes |
| --- | --- | --- |
| `uv run python scripts/check.py --tier unit` | 0 | 1105 passed, 3 skipped; Phase 6 eval registry 0 |
| `uv run python scripts/check.py --tier contract` | 1 | 416 passed, 21 skipped, 11 failed; see blockers |
| `uv run python scripts/check.py --tier types` | 1 | Ratchet 379 vs baseline 0; pre-existing across 69 files |
| `uv run ruff check .` | 0 | After excluding leftover `_tmp_*.py` scratch and sorting `__all__` / imports |
| `uv run pyright` (full repo) | 1 | Same 379-error report as the ratchet |
| `uv run pyright` on packet-owned files listed below | 0 | knowledge_scope, openai_general_chat, query_run_trace, studio_live, test_langsmith_tracing |
| `pnpm --filter smart-rag-frontend test` | 0 | 298 passed |
| `pnpm --filter smart-rag-frontend lint` | 0 | |
| `pnpm --filter smart-rag-frontend typecheck` | 0 | |
| `pnpm --filter smart-rag-frontend build` | 0 | Next.js 16.3.0 |

Packet-owned Pyright set:
`knowledge_scope.py`, `openai_general_chat.py`, `query_run_trace.py`,
`studio_live.py`, `test_langsmith_tracing.py`.

Bounded repair in this packet:

- Allow-list `openai_general_chat.py` in
  `test_production_openai_calls_use_traced_helpers`. The adapter already
  constructs the client with `traced_openai_client`.
- Treat `_tmp*` the same as `.tmp*` in the authored-file scanner and
  Ruff exclude so leftover P08-22 scratch does not fail
  `test_process_environment_reads_are_centralized` or `ruff check .`.
- Sort `smart_rag_core.security.__all__` and the
  `test_query_routing_matrix.py` import block.

## Scenario matrix (deterministic proof)

| # | Scenario | Proof | Result |
| --- | --- | --- | --- |
| 1 | `Hi` → general-chat model, no retrieval | `test_knowledge_scope.test_full_greeting_is_general_knowledge`, `test_general_chat_generate` | Passed |
| 2 | `How can you help me?` → general, one `answer` call, no citations | `test_general_chat_generate` | Passed |
| 3 | Capital of France → general, no retrieval | `test_knowledge_scope`, `test_general_chat_generate` | Passed |
| 4 | `Rewrite this paragraph: …` → user-text, one call | `test_knowledge_scope.test_rewrite_with_supplied_text_is_user_text` | Passed |
| 5 | `What is our refund period?` → company; cited or refusal, never general fallback | `test_knowledge_scope`, `test_general_chat_generate` | Passed |
| 6 | Current relationship → Combined unchanged | `test_query_routing_matrix` (`INV-SR-1001 related to procurement` → Combined Hybrid+graph local) | Passed |
| 7 | Table request → StructuredTable unchanged | `test_query_routing_matrix` (`sum the Q1 sheet totals`) | Passed |
| 8 | Mixed general+company → clarification, zero retrieval/model | `test_knowledge_scope.test_mixed_general_and_company_is_ambiguous` | Passed |
| 9 | Follow-up after cited company answer stays company | `test_knowledge_scope.test_company_followup_memory_keeps_document_scope` | Passed |
| 10 | Prompt injection cannot flip scope | `test_knowledge_scope.test_company_guard_overrides_malicious_general_model`, `test_general_chat_generate.test_prompt_injection_cannot_claim_document_access` | Passed |
| 11 | Duplicate / reconnect is one paid run | `test_query_sse_executor` settlement once; Studio `test_same_human_message_reuses_idempotency_key` | Passed (unit) |
| 12 | General call is `usage_kind=answer` on the reserved envelope | `test_general_chat_generate` / `QUERY_BUDGETS.md` | Passed (unit). Live reservation row **blocked** |
| 13 | ACL downgrade/deletion hides evidence | `tests/contract/test_citation_acl_recheck.py` exists; not re-run live here | **Blocked** (needs durable Supabase ACL fixture) |
| 14 | Expired/revoked Studio JWT rejects before model/retrieval | `test_query_studio_live` expired/revoked cases | Passed (unit). Live JWT **blocked** |

## Live / LangSmith / Studio blockers

| Gate | Status | Why |
| --- | --- | --- |
| LangSmith UI: completed runs no longer show `GeneratorExit` as success | **Blocked** | No browser LangSmith session in this run. Unit/contract lifecycle proof remains P06-11. Do not treat mocked spans as UI proof |
| Live FastAPI Ask matrix (3 chats, cancel, gateway failure) | **Blocked** | Hosted JWT/API chat not exercised in this packet |
| `query_studio` greeting/topology | **Blocked** | Unit passed (`test_query_studio`). Interactive Studio UI remains blocked |
| `query_studio_live` general / authorized / unauthorized / new-turn / retry / expired | **Blocked** | Unit passed. Live execution blocked: `LANGGRAPH_STUDIO_LIVE_ENABLED` unset and no live token was loaded into the process |
| Playwright Ask journey | **Skipped** | Config targets local GoTrue `:54321` and API `:8000`; those are not the hosted operator path |
| Full contract tier | **Blocked** | 11 failures are local-fixture/live-stack, not this feature: ParadeDB `:54329` connect timeout; leftover `concurrency_cap` on `:54322`; role inventory 6 vs 5; thin-UI live JWT 401 / `query_ready` mismatch |

## Documentation

Updated: `QUERY_ROUTING.md`, `QUERY_BUDGETS.md`, `SSE.md`,
`LANGSMITH_TRACING.md`, `LANGGRAPH_STUDIO.md`, `CONFIGURATION.md`,
`.env.example`, `docs/README.md`.

Covered: strict split, `answer_origin`, no company→world-knowledge
fallback, Studio live token setup/rotation/removal without printing it,
`query_studio` vs `query_studio_live`, `GeneratorExit` interpretation,
rollback, troubleshooting.

## Rollback

1. Keep unbound `query_studio`. Remove `query_studio_live` from
   `langgraph.json` and set `LANGGRAPH_STUDIO_LIVE_ENABLED=false`.
2. Delete `LANGGRAPH_STUDIO_ACCESS_TOKEN` from gitignored env.
3. Set `LANGSMITH_TRACING=false`.
4. Revert Ask origin chrome if the UI amendment must be withdrawn.

## User acceptance

P06-15 deterministic unit/frontend/ruff/packet-owned Pyright are proven.
Full types tier, full contract tier, live LangSmith UI, live Studio, live
Ask, and Playwright remain **blocked**. Phase 6 wrapper items stay
unchecked until you accept this evidence and the remaining live blockers
are cleared or waived.

## 2026-09-13 close-out (resume after P06-36)

P06-12 supersedes Packet 15 scenario 1: “Hi” is `general_knowledge` with
one profile call plus one answer call, not a zero-call deterministic
greeting. Scenario-matrix unit tests follow that amendment.

Bounded repairs in this close-out:

- Reinstalled a corrupt empty `regex` wheel so tiktoken `regex.escape`
  worked (`regex==2026.7.19`).
- Pyright 0: PyMuPDF/pypdf unknown-member suppressions in bake-off OCR
  modules, typed OCR redaction, OCR test payload typing.
- Extracted Hybrid cache lookup into
  `packages/core/src/smart_rag_core/retrieval/hybrid_run/cache_lookup.py`
  so `retriever.py` stays under the 600-line hard cap.
- Added missing test docstrings on pdf-eval HTTP doubles.

2026-09-13 deterministic gates
(`MOCK_MODEL_MODE=true`, `LANGSMITH_TRACING=false`,
`SUPABASE_URL=http://127.0.0.1:54321`, `APP_ENV` unset):

| Command | Exit | Notes |
| --- | --- | --- |
| `uv run python scripts/check.py --tier unit` | 0 | 1324 passed, 4 skipped |
| `uv run python scripts/check.py --tier contract` | 0 | 264 passed, 233 skipped (live-stack skips, not mocked pass) |
| `uv run python scripts/check.py --tier types` | 0 | Pyright ratchet 0 / baseline 0 |
| `uv run ruff check .` | 0 | |
| `uv run pyright` | 0 | |
| `pnpm --filter smart-rag-frontend test` | 0 | 555 passed / 79 files |
| `pnpm --filter smart-rag-frontend lint` | 0 | |
| `pnpm --filter smart-rag-frontend typecheck` | 0 | |
| `pnpm --filter smart-rag-frontend build` | 0 | Next.js 16.3.3 |

Live LangSmith UI, live Ask SSE, live `query_studio_live`, and Playwright
Ask remain **blocked**. Do not treat unit traces as UI proof.

Handoff to P06-16: documentation/custom-progress contract already landed;
producer proof remains BEP-02.
